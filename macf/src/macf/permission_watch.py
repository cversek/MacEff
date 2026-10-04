"""A permission prompt nobody is answering, seen from outside the session.

While Claude Code shows a permission dialog, the whole session waits: no tool
runs, no scheduled prompt fires, and nothing the session could run to report
itself will run. The PermissionRequest hook tells the operator once, at the
moment the dialog opens. If that one message is missed, the agent waits for
hours and looks, from every angle but this one, exactly like an agent at rest.
Measured: three stalls of 3, 17 and 12 hours, each on a command an allow rule
was meant to cover.

This module answers "is any session of this agent waiting on a permission
dialog right now, and since when?" from the agent's event log, and `watch`
turns the answer into reminders. It must run OUTSIDE the session it watches (a
timer, a cron job, a supervisor): the watched session cannot run it while it
waits. Policy: autonomous_operation section 5.5.

How a wait is read. For each session, the newest event that decides the
question settles it: a ``permission_requested`` means waiting since that
event's time; any PROGRESS event (a tool starting or finishing, a prompt
starting or ending, a session starting or ending, a compaction) means not
waiting. Events that happen DURING a dialog decide nothing:
``notification_received`` fires because of the dialog, and
``user_activity_detected`` carries no session and fires while the operator
types anywhere.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

REQUEST = "permission_requested"
PROGRESS = frozenset({
    "tool_call_started",
    "tool_call_completed",
    "dev_drv_started",
    "dev_drv_ended",
    "session_started",
    "session_ended",
    "compaction_detected",
})

STATE_NAME = "permission_watch.json"


@dataclass(frozen=True)
class Waiting:
    """One session waiting on one permission dialog."""
    session_id: str
    since: float
    tool: str
    preview: str

    def age_minutes(self, now: float) -> float:
        return (now - self.since) / 60.0

    @property
    def key(self) -> str:
        return f"{self.session_id}@{self.since:.3f}"


def _session_of(event: dict) -> Optional[str]:
    data = event.get("data") or {}
    hook_input = event.get("hook_input") or {}
    return data.get("session_id") or hook_input.get("session_id")


def _preview(event: dict) -> str:
    hook_input = event.get("hook_input") or {}
    tool_input = hook_input.get("tool_input")
    if isinstance(tool_input, dict):
        text = tool_input.get("command") or tool_input.get("file_path") or tool_input.get("skill")
        if text:
            return str(text)
    return str((event.get("data") or {}).get("tool_input_preview", ""))


def waiting(events_newest_first: Iterable[dict]) -> List[Waiting]:
    """Sessions whose newest deciding event is a permission request.

    ``events_newest_first`` must be newest first; the first deciding event
    seen for a session settles it and older ones are ignored.
    """
    decided: Dict[str, Optional[Waiting]] = {}
    for event in events_newest_first:
        name = event.get("event")
        if name != REQUEST and name not in PROGRESS:
            continue
        sid = _session_of(event)
        if not sid or sid in decided:
            continue
        if name == REQUEST:
            data = event.get("data") or {}
            decided[sid] = Waiting(
                session_id=sid,
                since=float(data.get("timestamp") or event.get("timestamp") or 0.0),
                tool=str(data.get("tool_name", "unknown")),
                preview=_preview(event),
            )
        else:
            decided[sid] = None
    return sorted((w for w in decided.values() if w is not None), key=lambda w: w.since)


def read_waiting() -> List[Waiting]:
    """``waiting`` over this agent's log, current cycle only.

    Cycle scope is exact here, not an approximation: a session that is waiting
    on a dialog cannot compact, so its request is in the current cycle.
    """
    from macf.agent_events_log import read_events
    return waiting(read_events(reverse=True, scope="cycle", only=PROGRESS | {REQUEST}))


# ---- history: the dialogs this agent met, read from the log alone ---------------------------
#
# The operator, 2026-10-04: every prompt should be countable, so that permissions can be loosened
# from evidence; and the record is the event log, not another state file. A dialog is answered at
# the first PROGRESS event after it in its session (the same reading `waiting` uses). It RAN when a
# tool_call_completed for the same tool and the same command or path follows before the turn ends,
# and is NOT RUN when the turn ends first. The rule that asked is not in the event (the hook input
# carries the tool, its input, the cwd and the mode), so it is matched at report time against the
# ask rules of today's settings.

TURN_ENDS = frozenset({"dev_drv_started", "dev_drv_ended", "session_started", "session_ended",
                       "compaction_detected"})
QUESTIONS = frozenset({"AskUserQuestion", "ExitPlanMode"})  # dialogs that ask, not permissions


@dataclass
class Dialog:
    """One permission dialog: when it opened, what it asked to run, and how it ended."""
    session_id: str
    opened: float
    tool: str
    command: str
    cwd: str
    outcome: str = "waiting"  # "ran", "not run", "answered" (turn not over yet) or "waiting"
    resolved: Optional[float] = None
    rule: Optional[str] = None

    @property
    def waited_minutes(self) -> Optional[float]:
        return None if self.resolved is None else (self.resolved - self.opened) / 60.0


def _identity(tool_input) -> str:
    """What a dialog asked to run: the command, the path or the skill."""
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("command") or tool_input.get("file_path") or tool_input.get("skill") or "")


def history(events_oldest_first: Iterable[dict], *, include_questions: bool = False) -> List[Dialog]:
    """The permission dialogs in ``events_oldest_first``, each paired with how it ended."""
    unanswered: Dict[str, List[Dialog]] = {}
    unrun: Dict[str, List[Dialog]] = {}
    dialogs: List[Dialog] = []
    for event in events_oldest_first:
        name = event.get("event")
        if name != REQUEST and name not in PROGRESS:
            continue
        sid = _session_of(event)
        if not sid:
            continue
        hook_input = event.get("hook_input") or {}
        when = float((event.get("data") or {}).get("timestamp") or event.get("timestamp") or 0.0)
        if name == REQUEST:
            tool = str(hook_input.get("tool_name") or (event.get("data") or {}).get("tool_name") or "unknown")
            if tool in QUESTIONS and not include_questions:
                continue
            d = Dialog(session_id=sid, opened=when, tool=tool,
                       command=_identity(hook_input.get("tool_input")) or _preview(event),
                       cwd=str(hook_input.get("cwd") or ""))
            dialogs.append(d)
            unanswered.setdefault(sid, []).append(d)
            unrun.setdefault(sid, []).append(d)
            continue
        for d in unanswered.pop(sid, []):
            d.resolved, d.outcome = when, "answered"
        if name == "tool_call_completed":
            key = (str(hook_input.get("tool_name") or ""), _identity(hook_input.get("tool_input")))
            pending = unrun.get(sid, [])
            match = next((d for d in pending if (d.tool, d.command) == key), None)
            if match is not None:
                match.outcome = "ran"
                pending.remove(match)
        elif name in TURN_ENDS:
            for d in unrun.pop(sid, []):
                d.outcome = "not run"
    return sorted(dialogs, key=lambda d: d.opened)


def _segments(command: str) -> List[str]:
    """The simple commands of a chain or pipe, leading VAR=value words dropped."""
    import shlex
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    segments, current = [], []
    try:
        for tok in lex:
            if tok and set(tok) <= set(";&|"):
                segments.append(current)
                current = []
            else:
                current.append(tok)
    except ValueError:  # unbalanced quotes: judge the text as one command
        return [command.strip()]
    segments.append(current)
    out = []
    for seg in segments:
        while seg and "=" in seg[0] and not seg[0].startswith("="):
            seg = seg[1:]
        if seg:
            out.append(" ".join(seg))
    return out


def matching_rule(tool: str, tool_input, rules: Iterable[str]) -> Optional[str]:
    """The first rule in ``rules`` that matches the call, with the client's meaning.

    ``Tool`` alone matches any call of that tool. ``Bash(prefix:*)`` matches a command any of
    whose simple commands starts with that prefix, as a whole word; ``Bash(text)`` matches one
    that is exactly that text. Specifiers of other tools are not evaluated.
    """
    import re
    command = _identity(tool_input)
    for rule in rules:
        m = re.fullmatch(r"([A-Za-z_]\w*)(?:\((.*)\))?", rule.strip())
        if not m or m.group(1) != tool:
            continue
        spec = m.group(2)
        if spec is None:
            return rule
        if tool != "Bash":
            continue
        prefix, wild = (spec[:-2], True) if spec.endswith(":*") else (spec, False)
        for seg in _segments(command):
            if seg == prefix or (wild and seg.startswith(prefix + " ")):
                return rule
    return None


def ask_rules(cwd: str, home: Path) -> List[str]:
    """The ask rules in force for a call made in ``cwd``: home settings, then each directory's
    ``.claude/settings*.json`` from ``cwd`` up to ``home``. Order kept, duplicates dropped."""
    files = [home / ".claude" / "settings.json", home / ".claude" / "settings.local.json"]
    if cwd:
        p = Path(cwd)
        chain = []
        while True:
            chain.append(p)
            if p == home or p.parent == p:
                break
            p = p.parent
        for d in reversed(chain):
            files += [d / ".claude" / "settings.json", d / ".claude" / "settings.local.json"]
    rules: List[str] = []
    for f in files:
        try:
            ask = (json.loads(f.read_text(encoding="utf-8")).get("permissions") or {}).get("ask") or []
        except (OSError, ValueError, AttributeError):
            continue
        rules += [r for r in ask if isinstance(r, str) and r not in rules]
    return rules


def read_history(days: float, *, include_questions: bool = False, home: Optional[Path] = None) -> List[Dialog]:
    """``history`` over the last ``days`` of this agent's log, each dialog given the ask rule
    of today's settings that matches it. Bounded by time: the newest-first read stops at the
    first event older than the cutoff (agent_events_log: bound by meaning)."""
    from macf.agent_events_log import read_events
    cutoff = time.time() - days * 86400.0
    window = []
    for event in read_events(reverse=True, scope="all", only=PROGRESS | {REQUEST}):
        if float(event.get("timestamp") or 0.0) < cutoff:
            break
        window.append(event)
    window.reverse()
    dialogs = history(window, include_questions=include_questions)
    home = home or Path.home()
    cache: Dict[str, List[str]] = {}
    for d in dialogs:
        if d.cwd not in cache:
            cache[d.cwd] = ask_rules(d.cwd, home)
        d.rule = matching_rule(d.tool, {"command": d.command, "file_path": d.command}, cache[d.cwd])
    return dialogs


def history_text(dialogs: List[Dialog], *, by_rule: bool) -> str:
    if not dialogs:
        return "no permission dialogs in this window"
    if by_rule:
        groups: Dict[str, List[Dialog]] = {}
        for d in dialogs:
            groups.setdefault(d.rule or "no ask rule matched (a hook or auto mode asked)", []).append(d)
        lines = ["dialogs  waited  longest  rule (ask rules of today's settings)"]
        for rule, ds in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            waits = [d.waited_minutes for d in ds if d.waited_minutes is not None]
            lines.append(f"{len(ds):7d}  {_fmt_age(sum(waits)):>6}  {_fmt_age(max(waits, default=0)):>7}  {rule}")
        return "\n".join(lines)
    lines = []
    for d in dialogs:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.opened))
        waited = "-" if d.waited_minutes is None else _fmt_age(d.waited_minutes)
        command = " ".join(d.command.split())
        lines.append(f"{when}  waited {waited:>7}  {d.outcome:<8}  {d.tool:<5}  "
                     f"{d.rule or '(no ask rule matched)'}  | {command[:160]}")
    return "\n".join(lines)


def history_json(dialogs: List[Dialog]) -> str:
    return json.dumps([dict(asdict(d), waited_minutes=None if d.waited_minutes is None
                            else round(d.waited_minutes, 2)) for d in dialogs], indent=2)


def state_path() -> Path:
    from macf.agent_events_log import get_log_path
    return get_log_path().parent / STATE_NAME


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    tmp.replace(path)


def _fmt_age(minutes: float) -> str:
    if minutes < 90:
        return f"{minutes:.0f} min"
    return f"{minutes / 60:.1f} h"


def reminder_text(w: Waiting, now: float, agent: str) -> str:
    started = time.strftime("%H:%M", time.localtime(w.since))
    command = w.preview if len(w.preview) <= 600 else w.preview[:600] + " ..."
    return (
        f"⏳ {agent} has been WAITING on a permission prompt for {_fmt_age(w.age_minutes(now))} "
        f"(since {started}). Nothing in that session runs until it is answered.\n"
        f"Tool: {w.tool}\n{command}"
    )


def resolved_text(key_state: dict, now: float, agent: str) -> str:
    minutes = (now - key_state["since"]) / 60.0
    return f"✅ {agent}: the permission prompt from {time.strftime('%H:%M', time.localtime(key_state['since']))} was answered (waited {_fmt_age(minutes)})."


def watch(
    current: List[Waiting],
    now: float,
    *,
    older_than_min: float,
    repeat_min: float,
    state: dict,
    send: Callable[[str], bool],
    agent: str,
) -> dict:
    """One pass: remind about each wait past ``older_than_min``, again every
    ``repeat_min``, and say once when a wait we reminded about is over.

    Returns the new state. A reminder that fails to send is not recorded as
    sent, so the next pass tries again.
    """
    new_state: dict = {}
    live = {w.key: w for w in current}
    for key, w in live.items():
        if w.age_minutes(now) < older_than_min:
            continue
        prior = state.get(key)
        due = prior is None or (now - prior["last_sent"]) / 60.0 >= repeat_min
        if due and send(reminder_text(w, now, agent)):
            new_state[key] = {"since": w.since, "last_sent": now, "tool": w.tool}
        elif prior is not None:
            new_state[key] = prior
    for key, prior in state.items():
        if key not in live and send(resolved_text(prior, now, agent)) is False:
            new_state[key] = prior  # try the all-clear again next pass
    return new_state


def as_json(current: List[Waiting], now: float) -> str:
    return json.dumps(
        [dict(asdict(w), age_minutes=round(w.age_minutes(now), 1)) for w in current],
        indent=2,
    )
