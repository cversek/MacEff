"""Answer "where am I running, and is it healthy?" without archaeology.

Every fact here was derivable before this module existed, and every one of them
was derived by hand — repeatedly, in a single evening, while actively working on
the harness — from ``$TMUX``, ps ancestry walks, tmux introspection and greps of
the supervisor registry. Two of those hand derivations were wrong.

That is the argument for the module. An agent coming out of compaction has to
establish where it is running before it can trust anything else it observes, and
a derivation subtle enough to catch out the person who just wrote the harness is
not one to leave to each caller.

The design rule, inherited from the defect that motivated it: **a negative must
name what was checked, and a default must be labelled a default.** ``harness
status`` once printed ``ABSENT`` for a name it had guessed, and it read as
"there is no harness here" — nothing in the output was false, and it was still
misleading, because a reader cannot discount a guess they cannot see.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, Optional

# The host that makes a session first-party. Not a preference: the client
# compares the base URL's host against this exact string to decide whether the
# long-context grant applies.
FIRST_PARTY_HOST = "api.anthropic.com"

# Set alongside a non-first-party base URL, this restores the long-context
# window. Underscore-prefixed and undocumented, so it can change or vanish in
# any release — which is why this module reports the SYMPTOM (the two settings
# disagreeing) rather than asserting the flag works.
FIRST_PARTY_FLAG = "_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL"


def _tmux(*args: str) -> Optional[str]:
    """Run a tmux query, or None if tmux is absent or has no server."""
    try:
        r = subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def live_supervisors() -> list:
    """Every registry entry that describes a supervisor actually running now.

    Uses the supervisor's own liveness predicate rather than repeating it, so
    "is it running" cannot come to mean two different things in two places.
    """
    from ..supervisor import REGISTRY_DIR, is_live_supervisor
    import json

    out = []
    if not REGISTRY_DIR.exists():
        return out
    for f in sorted(REGISTRY_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if is_live_supervisor(data):
            out.append(data)
    return out


def context_window_integrity() -> Dict[str, Any]:
    """Is this session's context window what it appears to be?

    The highest-value check here, because the failure it detects is invisible:
    when ``ANTHROPIC_BASE_URL`` names a host other than ``api.anthropic.com``,
    the client stops extending the long-context window and falls back to a fifth
    of it — silently, with every surface still displaying the full window, no
    log line and no warning. The only symptom is compacting early.

    It cost months of intermittent debugging, and it recurred the same evening
    it was fixed, from a shell that still held a pre-fix function. This check
    would have shown it at a glance, which is the whole point of putting it
    somewhere an agent already looks.
    """
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    flag = os.environ.get(FIRST_PARTY_FLAG, "")
    if not base:
        return {"base_url": None, "first_party_flag": bool(flag), "status": "direct",
                "detail": f"no ANTHROPIC_BASE_URL — first-party by default"}
    try:
        from urllib.parse import urlparse
        host = urlparse(base).netloc
    except ValueError:
        host = base
    # The host comparison includes the port, deliberately: a first-party host on
    # a non-default port does NOT pass the client's own check.
    if host == FIRST_PARTY_HOST:
        return {"base_url": base, "first_party_flag": bool(flag), "status": "first-party",
                "detail": f"base URL host is {FIRST_PARTY_HOST}"}
    if flag:
        return {"base_url": base, "first_party_flag": True, "status": "proxied-ok",
                "detail": f"host {host} is not {FIRST_PARTY_HOST}, but {FIRST_PARTY_FLAG} is set"}
    return {
        "base_url": base, "first_party_flag": False, "status": "DEGRADED",
        "detail": (f"host {host} is not {FIRST_PARTY_HOST} and {FIRST_PARTY_FLAG} is "
                   f"NOT set — the long-context window is silently reduced while "
                   f"every surface still reports the full size"),
    }


def diagnose(agent: Optional[str] = None) -> Dict[str, Any]:
    """Full supervision picture: who supervises me, in what session, how healthy."""
    from .harness import default_params, installed_agents, resolve_agent
    from .identity import calling_card_from_identifier

    resolved, source = resolve_agent(agent)
    ambiguous = source == "ambiguous"
    expected = None if ambiguous else resolved

    # --- supervision --------------------------------------------------------
    sups = live_supervisors()
    mine = [s for s in sups if s.get("name") == expected] if expected else []
    others = [s for s in sups if s.get("name") != expected]

    # --- this process's own session ----------------------------------------
    in_tmux = bool(os.environ.get("TMUX"))
    socket = os.environ.get("TMUX", "").split(",")[0] or None
    # display-message answers about the CURRENT client, which is what "am I in
    # it" means. list-sessions would answer about the server.
    current = _tmux("display-message", "-p", "#{session_name}") if in_tmux else None
    clients = None
    if current:
        listed = _tmux("list-clients", "-t", f"={current}", "-F", "#{client_tty}")
        clients = len([l for l in (listed or "").splitlines() if l.strip()])

    # --- artifacts ----------------------------------------------------------
    drift = None
    if not ambiguous:
        try:
            p = default_params(agent=expected)
            drift = []
            for path in (p.start, p.child_path, p.functions):
                if not path.exists():
                    drift.append(f"{path.name}: ABSENT")
        except Exception:
            drift = None

    return {
        "agent": {
            "identifier": None if ambiguous else expected,
            "calling_card": None if ambiguous else calling_card_from_identifier(expected),
            "resolved_from": source,
            "is_default": source == "default",
            "candidates": resolved if ambiguous else None,
            "installed": installed_agents(),
        },
        "supervision": {
            "supervised": bool(mine),
            "supervisors": [
                {"pid": s.get("supervisor_pid"), "name": s.get("name"),
                 "restarts": s.get("restart_count"), "session": s.get("tmux_session")}
                for s in mine
            ],
            # The precondition for two clients writing one task store. Named
            # rather than counted, because "another agent is also supervised
            # here" and "a second supervisor claims MY name" are different
            # facts and only the second one is a hazard.
            "other_live_supervisors": [
                {"pid": s.get("supervisor_pid"), "name": s.get("name")} for s in others
            ],
            "name_collision": bool(expected) and sum(
                1 for s in sups if s.get("name") == expected) > 1,
        },
        "session": {
            "in_tmux": in_tmux,
            "socket": socket,
            "name": current,
            "clients_attached": clients,
            # A client attached to a session that is not the harness's is the
            # state in which every status surface looks right and none of them
            # is describing the supervised session.
            "matches_expected": (current == expected) if (current and expected) else None,
        },
        "context_window": context_window_integrity(),
        "artifacts": {"missing": drift},
    }


def format_diagnosis(d: Dict[str, Any]) -> str:
    """Render for a human, saying what was checked on every negative."""
    lines = []
    a, s, sess, cw = d["agent"], d["supervision"], d["session"], d["context_window"]

    if a["candidates"]:
        lines.append(f"  Agent:        AMBIGUOUS — {', '.join(a['candidates'])}")
    elif a["is_default"]:
        lines.append(f"  Agent:        {a['identifier']}  (DEFAULT — not resolved "
                     f"from environment, config or any installed unit)")
    else:
        lines.append(f"  Agent:        {a['identifier']}  ({a['calling_card']}, via {a['resolved_from']})")

    if s["supervised"]:
        for sup in s["supervisors"]:
            lines.append(f"  Supervisor:   pid {sup['pid']} — {sup['restarts']} restart(s), "
                         f"session {sup['session']}")
    else:
        lines.append(f"  Supervisor:   NONE running for {a['identifier'] or 'any resolved agent'} "
                     f"(this session is not supervised — a crash will not restart it)")

    if s["name_collision"]:
        lines.append("  ⚠️  COLLISION:  more than one live supervisor claims this agent name — "
                     "two clients can write one task store")
    if s["other_live_supervisors"]:
        names = ", ".join(f"{o['name']}({o['pid']})" for o in s["other_live_supervisors"])
        lines.append(f"  Other agents: {names}")

    if sess["in_tmux"]:
        match = ""
        if sess["matches_expected"] is False:
            match = "  ⚠️ NOT the harness session"
        lines.append(f"  Session:      {sess['name']} — {sess['clients_attached']} client(s){match}")
        if (sess["clients_attached"] or 0) > 1:
            lines.append("  ⚠️  CLIENTS:    more than one client attached — mismatched geometry "
                         "causes fragmented redraws; detach the others")
    else:
        lines.append("  Session:      not running under tmux (no detach/reattach, "
                     "and nothing survives this terminal closing)")

    if cw["status"] == "DEGRADED":
        lines.append(f"  ⚠️  CONTEXT:    {cw['detail']}")
    else:
        lines.append(f"  Context:      {cw['status']} — {cw['detail']}")

    if d["artifacts"]["missing"]:
        lines.append(f"  ⚠️  ARTIFACTS:  {'; '.join(d['artifacts']['missing'])}")

    return "\n".join(lines)
