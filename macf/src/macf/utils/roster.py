"""Who this endpoint can attach to, and which of them a name means.

``harness attach`` used to take one exact tmux name, so the operator had to carry
each seat's session name, account and socket directory in his head (persistent_layer
4). The roster answers "who is here" from what each agent publishes, and the matcher
turns a short name (``lumen``, ``Lumen2``, ``3f9a1c``) into one of those agents, or
says plainly that it names several, or none.

**Where a card comes from.** From the agent's own home or its own daemon, never from
an environment variable (MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)): a shell
that exports ``MACEFF_AGENT_NAME`` for the host's resident agent would otherwise name
every seat after that one agent. The sources, in the order they are believed:

- a daemon record in this account's runtime directory, ``<id>.json``, whose name is the
  card through ``session_identifier``;
- a home's published units summary (``agent/public/pd/units.json``, ``agent`` = card),
  which peers already read (persistent_layer 8);
- ``agent_card(home)`` for a home that has a card and no summary;
- an installed legacy harness unit, ``cc-harness-<id>.service``.

**What one seat may know of another's** (persistent_layer 8): its public summary and
its card. Not its state: a peer's state lives with the peer's daemon, which answers only
its own account. So a peer's ``state`` is ``unknown``, with that reason, rather than a
guess made from a file that outlives its writer.

**Unknown is never empty.** A home that cannot be read is listed with the reason, never
left out, and every field that is unknown carries the reason it is unknown. The model
refuses an entry that doesn't, so a remote roster parsed into it (Phase 4) is held to the
same rule.
"""
from __future__ import annotations

import difflib
import functools
import os
import re
import pwd
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, model_validator

#: The endpoint name of this machine's own roster. A remote's entries carry its name.
LOCAL = "local"

#: Where a container's deployment declares its accounts. Hosts have none.
AGENTS_YAML = Path("/etc/maceff/agents.yaml")

#: Where accounts' homes are.
HOMES = Path("/Users") if sys.platform == "darwin" else Path("/home")

#: Seconds a state probe may take. Short: ``harness list`` asks once per local agent.
PROBE_TIMEOUT_S = 2.0

#: Seconds each remote roster may take while completing a word (roadmap Phase 5).
REMOTE_TIMEOUT_S = 1.0

#: Fields whose absence must be explained. ``state`` is explained when it is ``unknown``.
_EXPLAINED = ("card", "moniker", "uuid", "account", "display_name", "session_kind", "home")

#: Prefixes an account name carries before the agent's own name (``pa_lumen``).
_ACCOUNT_PREFIXES = ("pa_", "sa_")


class RosterEntry(BaseModel):
    """One agent this endpoint can attach to, or one home it could not read.

    ``uuid`` is the card's six-character suffix. ``aliases`` are names a deployment gives
    the agent that are not its moniker: its ``agents.yaml`` key and its account. They
    never resolve on their own while they are also a prefix of another agent's name (see
    ``match``). ``reasons`` maps each unknown field to why it is unknown.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    card: Optional[str] = None
    moniker: Optional[str] = None
    uuid: Optional[str] = None
    account: Optional[str] = None
    display_name: Optional[str] = None
    session_kind: Optional[Literal["daemon", "legacy"]] = None
    state: Literal["running", "stopped", "unknown"] = "unknown"
    endpoint: str = LOCAL
    home: Optional[str] = None
    aliases: Tuple[str, ...] = ()
    reasons: Dict[str, str] = {}
    detail: str = ""

    @model_validator(mode="after")
    def _unknown_is_never_empty(self) -> "RosterEntry":
        # Enforced here rather than left to each source, because an entry with a blank
        # field and no reason reads as "nothing there", the very failure a roster that
        # silently omits a home produces, one field at a time.
        missing = [f for f in _EXPLAINED if getattr(self, f) is None and not self.reasons.get(f)]
        if self.state == "unknown" and not self.reasons.get("state"):
            missing.append("state")
        if missing:
            raise ValueError(f"unknown without a reason: {', '.join(missing)}")
        return self

    @property
    def identifier(self) -> Optional[str]:
        """The session identifier the card maps to (``Lumen2MacEff_3f9a1c``)."""
        if not self.card:
            return None
        from .identity import session_identifier
        return session_identifier(self.card)


def card_parts(card: str) -> Tuple[str, Optional[str]]:
    """``Lumen2MacEff@3f9a1c`` -> ``("Lumen2MacEff", "3f9a1c")``; no ``@``, no uuid."""
    moniker, sep, uuid = card.rpartition("@")
    return (moniker, uuid) if sep and moniker and uuid else (card, None)


def _entry(card: Optional[str], **fields) -> RosterEntry:
    """An entry whose moniker and uuid come from its card, with reasons filled for both."""
    reasons = dict(fields.pop("reasons", {}))
    # Replaced by local_roster once agents.yaml has been read (_with_deployment_names).
    reasons.setdefault("display_name", "agents.yaml not consulted")
    moniker = uuid = None
    if card:
        moniker, uuid = card_parts(card)
        if uuid is None:
            reasons.setdefault("uuid", "the name carries no uuid suffix (a legacy harness slug)")
    else:
        why = reasons.get("card", "no card")
        reasons.setdefault("moniker", why)
        reasons.setdefault("uuid", why)
    return RosterEntry(card=card, moniker=moniker, uuid=uuid, reasons=reasons, **fields)


# ============================================================================
# 1. Sources
# ============================================================================

def _account_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def _deployment_names(agents_yaml: Path) -> Tuple[Dict[str, Tuple[str, Optional[str], Optional[str]]], str]:
    """Each account's ``agents.yaml`` key, display name and declared calling card, or nothing
    and the reason.

    Read as plain YAML, not through ``AgentsConfig``: that model refuses any file it does
    not fully understand, which is right for provisioning and wrong for a listing that only
    wants two fields, from a deployment that may be a version ahead or behind.
    """
    try:
        import yaml
        data = yaml.safe_load(Path(agents_yaml).read_text())
    except FileNotFoundError:
        return {}, f"no {agents_yaml} here (a host deployment declares none)"
    except OSError as e:
        return {}, f"{agents_yaml} cannot be read: {e.strerror or type(e).__name__}"
    except ValueError as e:      # yaml.YAMLError derives from it
        return {}, f"{agents_yaml} does not parse: {e}"
    agents = (data or {}).get("agents") if isinstance(data, dict) else None
    if not isinstance(agents, dict):
        return {}, f"{agents_yaml} declares no agents"
    names = {}
    for key, spec in agents.items():
        if isinstance(spec, dict) and isinstance(spec.get("username"), str):
            shown = spec.get("display_name")
            card = spec.get("calling_card")
            names[spec["username"]] = (str(key), shown if isinstance(shown, str) and shown.strip() else None,
                                       card if isinstance(card, str) and card.strip() else None)
    return names, ""


def _agent_home_markers(home: Path) -> Tuple[Optional[bool], str]:
    """Whether *home* holds an agent (a public tree or an identity file), or None and why.

    Asked with ``os.stat`` and named errors, not ``Path.is_dir``: a check that answers
    "no" for "may not look" is exactly how an unreadable home drops out of a listing.
    """
    for marker in (home / "agent" / "public", home / ".maceff_primary_agent.id"):
        try:
            os.stat(marker)
            return True, ""
        except FileNotFoundError:
            continue
        except OSError as e:
            return None, f"{home} cannot be read by this account: {e.strerror or type(e).__name__}"
    return False, ""


def _home_entry(home: Path, own_uid: int, probe: Optional["Probe"], legacy: Sequence[str],
                account_of: Callable[[Path, int], str],
                peers: bool) -> Optional[RosterEntry]:
    """The entry for one home, None when it is plainly not an agent's, or, with *peers*
    False, when it is another account's."""
    from ..pd.names import IdentityError, agent_card
    from ..pd.shared_view import read_agent

    try:
        st = home.stat()
        uid, account = st.st_uid, account_of(home, st.st_uid)
    except OSError as e:
        if not peers:
            return None          # this account's own home can be stat'ed; this one is not it
        return _entry(None, account=home.name, home=str(home), reasons={
            "card": f"{home} cannot be read: {e.strerror or type(e).__name__}",
            "session_kind": "the home cannot be read", "state": "the home cannot be read"})
    if not peers and uid != own_uid:
        # A host's other homes are other people's logins, not seats. Listing each as an
        # unreadable agent would be noise, and would carry their account names into a
        # roster that travels over ssh (Phase 4). The host's sources are this account's.
        return None
    if uid == 0 and own_uid != 0:
        # Root's home is /root. A root-owned directory beside the homes (lost+found, a
        # mount point) is no account's home, and listing each as unreadable would bury the
        # one unreadable home that matters under ones that never could. Root itself can
        # read them, so it is told what they hold.
        return None
    is_agent, why = _agent_home_markers(home)
    if is_agent is False:
        return None
    if is_agent is None:
        return _entry(None, account=account, home=str(home), reasons={
            "card": why, "session_kind": why, "state": why})

    reasons: Dict[str, str] = {}
    kind = None
    view = read_agent(home)
    card = None
    if view.status == "PUBLISHED":
        card = view.units.agent
        if any(u.kind == "session" for u in view.units.units):
            kind = "daemon"
        else:
            reasons["session_kind"] = "its published units declare no session unit"
    else:
        try:
            card = agent_card(home)
        except IdentityError as e:
            reasons["card"] = f"units summary {view.status.lower()} ({view.detail}); {e}"
        reasons["session_kind"] = f"no published units summary ({view.detail})"

    if uid == own_uid and card and probe is not None:
        from .identity import session_identifier
        ident = session_identifier(card)
        probed = probe(ident, ident in legacy)
        state = probed.state
        if state == "unknown":
            reasons["state"] = probed.reason
        if probed.kind:
            kind = probed.kind
            reasons.pop("session_kind", None)
    elif uid == own_uid:
        state = "unknown"
        reasons["state"] = "not asked" if probe is None else "no card to ask about"
    else:
        state = "unknown"
        reasons["state"] = ("another account's agent: its state lives with its own daemon, "
                            "which answers only that account (persistent_layer 8)")
    return _entry(card, account=account, home=str(home), session_kind=kind, state=state,
                  reasons=reasons)


@dataclass(frozen=True, kw_only=True)
class Probed:
    """What a probe found: the session's kind (None when neither kind is set up here), its
    state, and why, which matters when the state is ``unknown``."""

    kind: Optional[str]
    state: str
    reason: str = ""


#: ``probe(identifier, has_legacy_unit) -> Probed``.
Probe = Callable[[str, bool], Probed]


def _tmux_state(kind: str, ident: str, env: Dict[str, str]) -> Probed:
    try:
        rc = subprocess.run(["tmux", "has-session", "-t", f"={ident}"], capture_output=True,
                            env=env, timeout=PROBE_TIMEOUT_S).returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        return Probed(kind=kind, state="unknown", reason=f"tmux could not be asked: {e}")
    return Probed(kind=kind, state="running" if rc == 0 else "stopped")


def probe_local(ident: str, has_legacy_unit: bool,
                base: Optional[Path] = None) -> Probed:
    """This account's agent *ident*: which kind of session it has, and whether it runs.

    A session unit's server socket in the runtime directory makes it the daemon's session
    unit (persistent_layer 6.2); otherwise an installed legacy unit makes it the legacy
    harness, asked on the default server. A name on the default server proves presence,
    not ownership; that is the start script's concern, not a listing's.
    """
    from ..pd.session_unit import client_environment
    env = client_environment(ident, base)
    if env is not None:
        found = _tmux_state("daemon", ident, env)
        if found.state == "running":
            return found
    # The daemon's own answer: its session unit attachable from its status, whatever its
    # server is named (a unit declared with another --agent names its server after that).
    from .attach import NONE as _NONE, plan_attach_for_card
    from .identity import calling_card_from_identifier
    plan = plan_attach_for_card(calling_card_from_identifier(ident), base=base)
    if plan.kind != _NONE:
        return Probed(kind="daemon", state="running")
    if env is not None:
        return found
    if has_legacy_unit:
        plain = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_TMPDIR")}
        return _tmux_state("legacy", ident, plain)
    return Probed(kind=None, state="stopped")


#: Why a probed agent has no session kind: neither kind of session is set up here.
_NO_SESSION = "no session unit server in the runtime directory and no legacy unit installed"


def _daemon_detail(record: Path) -> str:
    """Whether the daemon a record names still runs: a record outlives its daemon."""
    from ..notify.session import verify_incarnation
    from ..pd.interface import DaemonRecord
    try:
        daemon = DaemonRecord.model_validate_json(record.read_text())
    except (OSError, ValueError) as e:
        return f"daemon record unreadable: {e}"
    if verify_incarnation(daemon.pid, daemon.proc_start):
        return f"daemon running (pid {daemon.pid})"
    return f"daemon record names pid {daemon.pid}, which is no longer that daemon"


def _runtime_entries(runtime: Path, account: str, probe: Optional[Probe],
                     legacy: Sequence[str], problems: List[str]) -> List[RosterEntry]:
    """An entry per daemon record in this account's runtime directory."""
    from .identity import calling_card_from_identifier
    try:
        records = sorted(p for p in runtime.iterdir() if p.suffix == ".json" and p.is_file())
    except FileNotFoundError:
        return []
    except OSError as e:
        problems.append(f"the runtime directory {runtime} cannot be read: {e.strerror or e}")
        return []
    out = []
    for record in records:
        ident = record.stem
        reasons = {"home": "a daemon record does not name its home"}
        if probe is None:
            kind, state = "daemon", "unknown"
            reasons["state"] = "not asked"
        else:
            probed = probe(ident, ident in legacy)
            kind, state = probed.kind, probed.state
            if state == "unknown":
                reasons["state"] = probed.reason
            if kind is None:
                reasons["session_kind"] = _NO_SESSION
        out.append(_entry(calling_card_from_identifier(ident), account=account, session_kind=kind,
                          state=state, detail=_daemon_detail(record), reasons=reasons))
    return out


def _legacy_entries(legacy: Sequence[str], account: str, probe: Optional[Probe]) -> List[RosterEntry]:
    from .identity import calling_card_from_identifier
    out = []
    for ident in legacy:
        reasons = {"home": "a legacy unit does not name its home"}
        if probe is None:
            kind, state = "legacy", "unknown"
            reasons["state"] = "not asked"
        else:
            probed = probe(ident, True)
            kind, state = probed.kind, probed.state
            if state == "unknown":
                reasons["state"] = probed.reason
            if kind is None:
                reasons["session_kind"] = _NO_SESSION
        out.append(_entry(calling_card_from_identifier(ident), account=account, session_kind=kind,
                          state=state, detail=f"legacy unit cc-harness-{ident}.service installed",
                          reasons=reasons))
    return out


def _merge(first: RosterEntry, second: RosterEntry) -> RosterEntry:
    """One entry for one card: *first* wins every field both know; *second* fills the rest.

    Sources are passed in the order they are believed about a session: this account's own
    daemon record and probe before a home's published summary.
    """
    data = first.model_dump()
    other = second.model_dump()
    for f in _EXPLAINED:
        if data[f] is None and other[f] is not None:
            data[f] = other[f]
    if data["state"] == "unknown" and other["state"] != "unknown":
        data["state"] = other["state"]
    data["aliases"] = tuple(dict.fromkeys(list(data["aliases"]) + list(other["aliases"])))
    reasons = {**other["reasons"], **data["reasons"]}
    data["reasons"] = {k: v for k, v in reasons.items()
                       if (k == "state" and data["state"] == "unknown") or data.get(k) is None}
    data["detail"] = "; ".join(d for d in (data["detail"], other["detail"]) if d)
    return RosterEntry(**data)


#: The six hex characters a card's uuid suffix must be.
_UUID6 = re.compile(r"^[0-9a-f]{6}$")

#: Who writes a seat's identity file in a deployment: root, at provisioning.
DEPLOYMENT_UID = 0


def _declared_card(home: Optional[str], name: str) -> Tuple[Optional[str], str]:
    """``name@uuid`` from the deployment's declared card and the home's identity file, which
    the deployment writes world-readable; or None and why it couldn't be made."""
    if not home:
        return None, f"agents.yaml declares {name!r}, but the home isn't known"
    path = Path(home) / ".maceff_primary_agent.id"
    try:
        # The deployment writes it root-owned; a seat owns its home and could put its own
        # file there, so only root's is the deployment's word.
        if path.stat().st_uid != DEPLOYMENT_UID:
            return None, f"agents.yaml declares {name!r}, but {path} is not the deployment's file (not root's)"
        uuid = path.read_text().strip()[:6]
    except OSError as e:
        return None, f"agents.yaml declares {name!r}, but {path} can't be read: {e.strerror or type(e).__name__}"
    if not _UUID6.match(uuid):
        return None, f"agents.yaml declares {name!r}, but {path} holds no uuid"
    return f"{name}@{uuid}", ""


def _with_deployment_names(entry: RosterEntry, names: Dict[str, Tuple[str, Optional[str], Optional[str]]],
                           why: str) -> RosterEntry:
    data = entry.model_dump()
    aliases = list(data["aliases"])
    if entry.account:
        aliases.append(entry.account)
        for prefix in _ACCOUNT_PREFIXES:
            if entry.account.startswith(prefix) and len(entry.account) > len(prefix):
                aliases.append(entry.account[len(prefix):])
    found = names.get(entry.account or "")
    if found:
        key, shown, declared = found
        aliases.insert(0, key)
        card, unmade = _declared_card(entry.home, declared) if declared and not entry.card else (None, "")
        if unmade:
            data["reasons"]["card"] = f"{data['reasons'].get('card', 'no card')}; {unmade}"
        if card:
            # A peer's home is private, so its card is read from the deployment that declares
            # it (agents.yaml, root-owned) and its identity file: never from an environment.
            data["card"] = card
            data["moniker"], data["uuid"] = card_parts(card)
            for f in ("card", "moniker", "uuid"):
                data["reasons"].pop(f, None)
        if shown:
            data["display_name"] = shown
            data["reasons"].pop("display_name", None)
        else:
            data["reasons"]["display_name"] = "agents.yaml gives this account no display_name"
    elif data["display_name"] is None:
        data["reasons"]["display_name"] = why or f"agents.yaml declares no account {entry.account!r}"
    own = (entry.moniker or "").casefold()
    data["aliases"] = tuple(dict.fromkeys(a for a in aliases if a and a.casefold() != own))
    return RosterEntry(**data)


def _declared(agents_yaml: Path) -> bool:
    """Whether a deployment declares its accounts here: its agents.yaml exists, readable or
    not. A file that exists and can't be read is still a container's, whose seats count."""
    try:
        os.stat(agents_yaml)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return True


@dataclass
class Roster:
    """The entries, and anything that kept the listing from being complete."""

    entries: List[RosterEntry] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.problems


def local_roster(*, homes: Path = HOMES, runtime: Optional[Path] = None,
                 unit_dir: Optional[Path] = None, agents_yaml: Path = AGENTS_YAML,
                 probe: Optional[Probe] = probe_local, uid: Optional[int] = None,
                 account_of: Optional[Callable[[Path, int], str]] = None) -> Roster:
    """Every agent this endpoint can attach to, read only.

    ``probe`` asks whether this account's agents' sessions run; None skips it (completion
    needs names, not states), and those states read ``unknown`` with "not asked". A home's
    account is its owner's name (``account_of``).

    Every home is scanned only where a deployment declares its accounts (``agents_yaml``
    exists): a container, whose homes are its seats, and where an unreadable one is listed
    with the reason. On a host, which declares none, only this account's own homes are
    read; the other homes there are other people's logins and are not reported at all. Each other parameter exists so a test
    can point it at a fixture.
    """
    from ..pd.names import runtime_dir
    from .harness import installed_agents

    own_uid = os.getuid() if uid is None else uid
    account = _account_name(own_uid)
    problems: List[str] = []
    legacy = installed_agents(unit_dir)
    if probe is probe_local and runtime is not None:
        probe = functools.partial(probe_local, base=runtime)

    by_card: Dict[str, RosterEntry] = {}
    unnamed: List[RosterEntry] = []

    def add(entry: RosterEntry) -> None:
        if entry.card is None:
            unnamed.append(entry)
        elif entry.card in by_card:
            by_card[entry.card] = _merge(by_card[entry.card], entry)
        else:
            by_card[entry.card] = entry

    for e in _runtime_entries(runtime or runtime_dir(), account, probe, legacy, problems):
        add(e)
    for e in _legacy_entries(legacy, account, probe):
        add(e)
    names, why = _deployment_names(agents_yaml)
    peers = _declared(agents_yaml)
    try:
        candidates = sorted(Path(p.path) for p in os.scandir(homes) if p.is_dir())
    except FileNotFoundError:
        candidates = []
    except OSError as e:
        problems.append(f"the homes directory {homes} cannot be listed: {e.strerror or e}")
        candidates = []
    for home in candidates:
        e = _home_entry(home, own_uid, probe, legacy,
                        account_of or (lambda _home, owner: _account_name(owner)), peers)
        if (e is not None and not peers and e.card is None
                and not os.path.lexists(home / ".maceff" / "config.json")):
            # On a host a home is a login's, not a seat's: one with no agent config names no
            # agent, and listing it as an unknown agent is noise. A config that is there but
            # can't be read is an agent we can't see, and stays a row with the reason.
            continue
        if e is not None:
            add(e)

    entries = [_with_deployment_names(e, names, why)
               for e in sorted(by_card.values(), key=lambda e: e.card.casefold())]
    entries += [_with_deployment_names(e, names, why) for e in sorted(unnamed, key=lambda e: e.account or "")]
    return Roster(entries=entries, problems=problems)


# ============================================================================
# 2. Remote rosters, gathered with a deadline
# ============================================================================

#: ``fetch(timeout) -> entries`` for one remote. Phase 4 supplies one per declared remote.
RemoteFetch = Callable[[float], List[RosterEntry]]


def remote_fetchers(problems: Optional[List[str]] = None) -> List[RemoteFetch]:
    """One fetcher per remote the operator declares (utils/remotes.py), each running the
    remote's ``harness list --json --local`` over a non-interactive ssh. A declaration that
    can't be used yields none, and the reason goes to *problems* when given."""
    from .remotes import Fetcher, RemotesRefused, load_remotes
    try:
        return [Fetcher(r) for r in load_remotes().remotes]
    except RemotesRefused as e:
        if problems is not None:
            problems.append(f"the remotes declaration is refused: {e}")
        return []


def gather(local: Sequence[RosterEntry], fetchers: Sequence[RemoteFetch] = (),
           timeout: float = REMOTE_TIMEOUT_S) -> Tuple[List[RosterEntry], List[str]]:
    """The local entries and every remote's, each remote in parallel and bounded by *timeout*.

    Returns ``(entries, unanswered)``, the second naming each fetcher that timed out or
    failed, and why: by its ``name`` attribute, or else by position. Threads are daemons, so one stuck in ssh can't hold the process
    open at exit: completion must return within its deadline whatever a remote does.
    """
    results: List[Optional[List[RosterEntry]]] = [None] * len(fetchers)
    errors: List[str] = [""] * len(fetchers)

    def run(i: int, fetch: RemoteFetch) -> None:
        try:
            results[i] = list(fetch(timeout))
        except Exception as e:  # noqa: BLE001 - GUARD, see below
            # Deliberately broad: a GUARD. One remote's failure, whatever its type, must
            # cost only that remote's entries, never the listing or the completion.
            errors[i] = f"{type(e).__name__}: {e}"

    threads = [threading.Thread(target=run, args=(i, f), daemon=True) for i, f in enumerate(fetchers)]
    for t in threads:
        t.start()
    import time
    deadline = time.monotonic() + timeout
    for t in threads:
        t.join(max(0.0, deadline - time.monotonic()))
    entries = list(local)
    unanswered = []
    for i, got in enumerate(results):
        if got is None:
            label = getattr(fetchers[i], "name", None) or f"remote {i}"
            unanswered.append(f"{label}: {errors[i] or f'no answer within {timeout:g} s'}")
        else:
            entries.extend(got)
    return entries, unanswered


# ============================================================================
# 3. Matching a name to an agent
# ============================================================================

ONE = "one"
SEVERAL = "several"
NONE = "none"

#: Exit codes for a name that doesn't resolve to one agent (roadmap Phase 2).
EXIT_NO_MATCH = 1
EXIT_AMBIGUOUS = 2


@dataclass(frozen=True)
class MatchResult:
    """What a name resolved to. ``tier`` is the tier that decided (1-3), None for no match.
    For ``NONE``, ``entries`` are the nearest candidates rather than matches."""

    kind: str
    query: str
    entries: List[RosterEntry]
    tier: Optional[int] = None

    @property
    def entry(self) -> Optional[RosterEntry]:
        return self.entries[0] if self.kind == ONE else None


def _unique(entries) -> List[RosterEntry]:
    """In order, each entry once. By identity: an entry holds a dict, so it can't be hashed."""
    seen, out = set(), []
    for e in entries:
        if id(e) not in seen:
            seen.add(id(e))
            out.append(e)
    return out


def _decide(query: str, hits: List[RosterEntry], tier: int) -> MatchResult:
    return MatchResult(ONE if len(hits) == 1 else SEVERAL, query, hits, tier)


def match(entries: Sequence[RosterEntry], query: str) -> MatchResult:
    """Resolve *query* against *entries*, by tiers; the first tier with any hit decides.

    1. an exact card, session identifier, or uuid (with or without ``@``);
    2. an exact moniker or display name, ignoring case;
    3. a prefix of a moniker or display name, ignoring case.

    An alias (a deployment key such as ``lumen``, or an account) is matched with tier 3:
    exactly, and counted beside the prefix hits. So it resolves only when nothing else
    starts with it. ``lumen`` is Lumen1's ``agents.yaml`` key and a prefix of Lumen2,
    Lumen3 and Lumen4; were the alias to win, ``attach lumen`` would quietly pick Lumen1
    for an operator who may have meant any of four.

    Entries without a card (unreadable homes) are never matched: there is nothing to
    attach to. They appear among the nearest candidates when nothing matches.
    """
    q = query.strip()
    named = [e for e in entries if e.card]
    if not q:
        return MatchResult(NONE, q, list(entries))
    folded = q.casefold()
    bare = q[1:] if q.startswith("@") else q

    tier1 = [e for e in named if e.card == q or e.identifier == q or (e.uuid and e.uuid == bare)]
    if tier1:
        return _decide(q, tier1, 1)
    tier2 = [e for e in named
             if any((n or "").casefold() == folded for n in (e.moniker, e.display_name))]
    if tier2:
        return _decide(q, tier2, 2)
    by_prefix = [e for e in named
                 if any(n.casefold().startswith(folded) for n in (e.moniker, e.display_name) if n)]
    by_alias = [e for e in named if any(a.casefold() == folded for a in e.aliases)]
    tier3 = _unique(by_prefix + by_alias)
    if tier3:
        return _decide(q, tier3, 3)
    return MatchResult(NONE, q, nearest(entries, q))


def nearest(entries: Sequence[RosterEntry], query: str, limit: int = 5) -> List[RosterEntry]:
    """The entries whose names look most like *query*; the whole roster when none does,
    so a miss always shows what could have been meant."""
    keyed = {}
    for e in entries:
        for n in (e.card, e.moniker, e.display_name, e.account, *e.aliases):
            if n:
                keyed.setdefault(n.casefold(), e)
    close = difflib.get_close_matches(query.casefold(), list(keyed), n=limit * 3, cutoff=0.5)
    picked = _unique(keyed[c] for c in close)[:limit]
    return picked or list(entries)


def describe(entry: RosterEntry) -> str:
    """One line naming the agent so the next call can be exact: card (with its uuid),
    endpoint, account, session kind and state."""
    card = entry.card or f"(no card: {entry.reasons.get('card', 'unknown')})"
    return "  ".join([card, entry.endpoint, entry.account or "?",
                      entry.session_kind or "?", entry.state])


def is_interactive() -> bool:
    """Whether a person can answer a prompt: both stdin and stdout are terminals."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def choose(result: MatchResult, *, interactive: Optional[bool] = None,
           out=None, err=None, read: Callable[[str], str] = input) -> Tuple[Optional[RosterEntry], int]:
    """Turn a match into one agent, or an exit code.

    One match: that entry and 0. Several on a terminal: a numbered list and a prompt; a
    number, or a name that matches exactly one of the listed, picks it. Several not on a
    terminal: the list, then exit 2. None: the nearest candidates, then exit 1. Lists go to
    *out* (stdout) so a script can read the uuids; the headline goes to *err*.
    """
    out = out or sys.stdout
    err = err or sys.stderr
    if result.kind == ONE:
        return result.entry, 0
    if result.kind == NONE:
        print(f"No agent here matches {result.query!r}.", file=err)
        if result.entries:
            print("Nearest:", file=out)
            for e in result.entries:
                print(f"  {describe(e)}", file=out)
        else:
            print("This endpoint lists no agents (macf_tools harness list).", file=err)
        return None, EXIT_NO_MATCH

    interactive = is_interactive() if interactive is None else interactive
    print(f"{len(result.entries)} agents match {result.query!r}:", file=err)
    for i, e in enumerate(result.entries, 1):
        print(f"  {i}) {describe(e)}", file=out)
    if not interactive:
        print("Name one exactly (its card or uuid) to attach.", file=err)
        return None, EXIT_AMBIGUOUS
    try:
        answer = read(f"Attach to which? [1-{len(result.entries)}, Enter to cancel]: ").strip()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.isdigit() and 1 <= int(answer) <= len(result.entries):
        return result.entries[int(answer) - 1], 0
    if answer:
        again = match(result.entries, answer)
        if again.kind == ONE:
            return again.entry, 0
        print(f"{answer!r} picks none of these.", file=err)
    else:
        print("Nothing chosen.", file=err)
    return None, EXIT_NO_MATCH


def resolve(query: str, entries: Sequence[RosterEntry], **kwargs) -> Tuple[Optional[RosterEntry], int]:
    """``match`` then ``choose``: the one call attach makes with a name."""
    return choose(match(entries, query), **kwargs)


# ============================================================================
# 4. Completion candidates
# ============================================================================

def completion_candidates(entries: Sequence[RosterEntry], prefix: str = "") -> List[Tuple[str, str]]:
    """Words that complete *prefix* to an agent, each with a description.

    Each named entry offers its card, moniker and uuid; the card's description is its
    endpoint, the others name the card too. Matched ignoring case, so ``lum`` offers
    ``LumenMacEff``, and in order, first word first. A word two entries share (one moniker
    on two endpoints) is offered once, and the cards tell them apart.
    """
    folded = prefix.casefold()
    at = prefix.startswith("@")
    words: Dict[str, str] = {}
    for e in entries:
        if not e.card:
            continue
        offered = [(e.card, e.endpoint), (e.moniker, f"{e.endpoint} {e.card}")]
        if e.uuid:
            offered.append(((f"@{e.uuid}" if at else e.uuid), f"{e.endpoint} {e.card}"))
        for word, why in offered:
            if word and word.casefold().startswith(folded) and word not in words:
                words[word] = why
    return list(words.items())


# ============================================================================
# 5. The table
# ============================================================================

_COLUMNS = ("CARD", "ENDPOINT", "ACCOUNT", "KIND", "STATE", "DISPLAY NAME")


def render_table(entries: Sequence[RosterEntry], verbose: bool = False) -> str:
    """``harness list``'s table: one row per agent. Under a row whose card is unknown, why,
    since that row can't be attached to by name. ``verbose`` adds the reason for every field
    left unknown, fields that share a reason on one line, and each row's detail."""
    if not entries:
        return "No agents on this endpoint."
    rows = [_COLUMNS] + [(e.card or "?", e.endpoint, e.account or "?", e.session_kind or "?",
                          e.state, e.display_name or "-") for e in entries]
    widths = [max(len(r[i]) for r in rows) for i in range(len(_COLUMNS))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(rows[0], widths, strict=True)).rstrip()]
    quiet = 0
    for e, row in zip(entries, rows[1:], strict=True):
        lines.append("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)).rstrip())
        if not verbose:
            if e.card is None and e.reasons.get("card"):
                lines.append(f"    card unknown: {e.reasons['card']}")
            quiet += bool(e.reasons or e.detail)
            continue
        grouped: Dict[str, List[str]] = {}
        for f, why in e.reasons.items():
            grouped.setdefault(why, []).append(f)
        for why, fields in grouped.items():
            lines.append(f"    {', '.join(fields)} unknown: {why}")
        if e.detail:
            lines.append(f"    {e.detail}")
    if quiet:
        lines.append("(--verbose says why each unknown field is unknown)")
    return "\n".join(lines)
