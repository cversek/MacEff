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
import os
import re
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
# the first PROGRESS event after it from the same caller (session, and subagent when there is one).
# It RAN when a tool_call_completed for the same tool and the same command or path follows before
# the turn ends, and is NOT RUN when the turn ends first. When a later session of this agent starts
# while a dialog is still open, the session that raised it ended without saying so (killed, its
# terminal closed), and the dialog is closed as "session ended" instead of waiting forever.
#
# The rule that asked is not in the event (the hook input carries the tool, its input, the cwd, the
# mode and any rule the client offered), so it is matched at report time against the ask rules of
# today's settings, read the way the client reads them (Claude Code docs, "Configure permissions"
# and "Settings files and precedence").

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
    outcome: str = "waiting"  # "ran", "not run", "answered", "session ended" or "waiting"
    resolved: Optional[float] = None
    rule: Optional[str] = None
    agent_id: str = ""            # set when a subagent raised it
    mode: str = ""                # the permission mode the dialog opened in
    offered: Optional[str] = None  # the rule the client offered in the dialog, if any
    project_dir: str = ""         # the session's primary working directory, if its start is in view

    @property
    def waited_minutes(self) -> Optional[float]:
        return None if self.resolved is None else (self.resolved - self.opened) / 60.0


def _identity(tool_input) -> str:
    """What a dialog asked to run: the command, the path or the skill."""
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("command") or tool_input.get("file_path") or tool_input.get("skill") or "")


def _offered_rule(hook_input: dict) -> Optional[str]:
    """The first rule the client offered to add in the dialog, as Tool(content)."""
    for s in hook_input.get("permission_suggestions") or []:
        for r in (s.get("rules") or []) if isinstance(s, dict) else []:
            if isinstance(r, dict) and r.get("toolName"):
                content = r.get("ruleContent")
                return f"{r['toolName']}({content})" if content else str(r["toolName"])
    return None


def history(events_oldest_first: Iterable[dict], *, include_questions: bool = False) -> List[Dialog]:
    """The permission dialogs in ``events_oldest_first``, each paired with how it ended.

    Waits are lower bounds when calls run in parallel: a sibling call's progress ends the wait.
    """
    unanswered: Dict[tuple, List[Dialog]] = {}
    unrun: Dict[tuple, List[Dialog]] = {}
    project: Dict[str, str] = {}
    dialogs: List[Dialog] = []
    for event in events_oldest_first:
        name = event.get("event")
        if name != REQUEST and name not in PROGRESS:
            continue
        sid = _session_of(event)
        if not sid:
            continue
        hook_input = event.get("hook_input") or {}
        caller = (sid, str(hook_input.get("agent_id") or ""))
        when = float((event.get("data") or {}).get("timestamp") or event.get("timestamp") or 0.0)
        if name == "session_started":
            if hook_input.get("cwd"):
                project[sid] = str(hook_input["cwd"])
            # A later session of this agent: whatever an earlier session left open never ended.
            for key in [k for k in unanswered if k[0] != sid]:
                for d in unanswered.pop(key):
                    d.outcome = "session ended"
            for key in [k for k in unrun if k[0] != sid]:
                del unrun[key]
        if name == REQUEST:
            tool = str(hook_input.get("tool_name") or (event.get("data") or {}).get("tool_name") or "unknown")
            if tool in QUESTIONS and not include_questions:
                continue
            d = Dialog(session_id=sid, opened=when, tool=tool,
                       command=_identity(hook_input.get("tool_input")) or _preview(event),
                       cwd=str(hook_input.get("cwd") or ""), agent_id=caller[1],
                       mode=str(hook_input.get("permission_mode") or ""),
                       offered=_offered_rule(hook_input), project_dir=project.get(sid, ""))
            dialogs.append(d)
            unanswered.setdefault(caller, []).append(d)
            unrun.setdefault(caller, []).append(d)
            continue
        if name in TURN_ENDS:
            # The primary's turn boundary ends every caller in that session, subagents included.
            keys = [k for k in set(unanswered) | set(unrun) if k[0] == sid]
        else:
            keys = [caller]
        for key in keys:
            for d in unanswered.pop(key, []):
                d.resolved, d.outcome = when, "answered"
        if name == "tool_call_completed":
            key = (str(hook_input.get("tool_name") or ""), _identity(hook_input.get("tool_input")))
            pending = unrun.get(caller, [])
            match = next((d for d in pending if (d.tool, d.command) == key), None)
            if match is not None:
                match.outcome = "ran"
                pending.remove(match)
        elif name in TURN_ENDS:
            for key in keys:
                for d in unrun.pop(key, []):
                    if d.outcome != "session ended":
                        d.outcome = "not run"
    return sorted(dialogs, key=lambda d: d.opened)


# Wrappers the client strips before matching (docs, "Process wrappers"), with the options they take.
_WRAPPERS = {"timeout": 1, "nice": 0, "nohup": 0, "time": 0, "stdbuf": 0}
# Words that open a loop or branch body: the command after them is still a command.
_BODY_WORDS = {"do", "then", "else", "if", "elif", "while", "until", "!", "{"}
_SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")


def _segments(command: str) -> List[str]:
    """Every simple command the client would match a rule against.

    Commands are separated by ; & | && || and newlines; the body of a command substitution, a
    loop or a branch counts as commands too; leading VAR=value words and process wrappers are
    dropped. Unbalanced quotes: the text is judged as one command.
    """
    import shlex
    inner: List[str] = []
    for m in _SUBSTITUTION.finditer(command):
        inner += _segments(m.group(1) if m.group(1) is not None else m.group(2))
    flat = _SUBSTITUTION.sub(" SUBST ", command)
    lex = shlex.shlex(flat, posix=True, punctuation_chars=";&|()<>\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    segments, current = [], []
    try:
        for tok in lex:
            if tok and set(tok) <= set(";&|()\n"):
                segments.append(current)
                current = []
            else:
                current.append(tok)
    except ValueError:
        return [command.strip()] + inner
    segments.append(current)
    out = []
    for seg in segments:
        while seg and seg[0] in _BODY_WORDS:
            seg = seg[1:]
        if seg and seg[0] in {"for", "case", "select", "done", "fi", "esac", "}"}:
            continue  # loop headers and closers carry no command of their own
        changed = True
        while seg and changed:
            changed = False
            while seg and "=" in seg[0] and not seg[0].startswith("="):
                seg, changed = seg[1:], True
            if seg and seg[0] in _WRAPPERS:
                skip = 1
                while skip < len(seg) and seg[skip].startswith("-"):
                    skip += 2 if seg[skip] in ("-n", "-s", "-k", "-o", "-e", "-i") else 1
                skip += _WRAPPERS[seg[0]]
                seg, changed = seg[skip:], True
        if seg:
            out.append(" ".join(seg))
    return out + inner


def _bash_spec_matches(spec: str, segment: str) -> bool:
    """A Bash rule's specifier against one simple command, as the docs define it.

    ``*`` is any text at any position; ``:*`` is the older spelling of a trailing `` *``, and a
    trailing `` *`` keeps its word boundary, so ``git push *`` matches ``git push`` and
    ``git push -u`` but not ``git pushx``. Without ``*`` the command must match exactly.
    """
    if spec.endswith(":*"):
        spec = spec[:-2] + " *"
    if spec.endswith(" *"):
        head = spec[:-2]
        if "*" not in head:
            return segment == head or segment.startswith(head + " ")
        return bool(re.fullmatch(_glob_re(head) + r"(?: .*)?", segment, re.S))
    return bool(re.fullmatch(_glob_re(spec), segment, re.S))


def _glob_re(text: str) -> str:
    return ".*".join(re.escape(part) for part in text.split("*"))


def matching_rule(tool: str, tool_input, rules: Iterable[str]) -> Optional[str]:
    """The first rule in ``rules`` that matches the call, with the client's meaning.

    ``Tool`` alone matches any call of that tool. A Bash rule matches when any simple command of
    the call matches its specifier (``_segments``, ``_bash_spec_matches``). Specifiers of other
    tools are not evaluated.
    """
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
        if any(_bash_spec_matches(spec, seg) for seg in _segments(command)):
            return rule
    return None


def _git_root(path: Path) -> Path:
    for p in [path, *path.parents]:
        if (p / ".git").exists():
            return p
    return path


def settings_files(project_dir: str, home: Path, environ=None) -> List[Path]:
    """The settings files the client reads for a session, in its order of precedence, lowest first.

    User settings live in CLAUDE_CONFIG_DIR, or ~/.claude. Project settings are read from the
    session's primary working directory, and the local file from that project's repository root.
    Nothing between the project and home is read, and a later ``cd`` does not change them.
    """
    env = os.environ if environ is None else environ
    config = Path(env["CLAUDE_CONFIG_DIR"]) if env.get("CLAUDE_CONFIG_DIR") else home / ".claude"
    files = [config / "settings.json"]
    if project_dir:
        proj = Path(project_dir)
        files += [proj / ".claude" / "settings.json", _git_root(proj) / ".claude" / "settings.local.json"]
    files += [Path("/etc/claude-code/managed-settings.json"),
              Path("/Library/Application Support/ClaudeCode/managed-settings.json")]
    out: List[Path] = []
    for f in files:
        if f not in out:
            out.append(f)
    return out


def ask_rules(project_dir: str, home: Path, environ=None) -> List[str]:
    """The ask rules in force for a session started in ``project_dir``. Order kept, duplicates dropped."""
    rules: List[str] = []
    for f in settings_files(project_dir, home, environ):
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
        # The session's start is the project; a session begun before the window falls back to
        # the dialog's own directory, which is right unless the session had moved with cd.
        where = d.project_dir or d.cwd
        if where not in cache:
            cache[where] = ask_rules(where, home)
        d.rule = matching_rule(d.tool, {"command": d.command, "file_path": d.command}, cache[where])
    return dialogs


def _unmatched_group(d: Dialog) -> str:
    """Where a dialog no ask rule explains goes, so the group says what to allow."""
    if d.offered and "*" in d.offered:  # an exact offered rule is one command, not a group
        return f"no ask rule matched; the dialog offered {d.offered}"
    if d.tool != "Bash":
        return f"no ask rule matched; {d.tool}"  # paths and inputs vary per call; the tool is the group
    first = next(iter(_segments(d.command)), "")  # past assignments, wrappers and chaining
    words = " ".join(first.split()[:2])
    return f"no ask rule matched; Bash: {words}" if words else "no ask rule matched; Bash"


def history_text(dialogs: List[Dialog], *, by_rule: bool) -> str:
    if not dialogs:
        return "no permission dialogs in this window"
    if by_rule:
        groups: Dict[str, List[Dialog]] = {}
        for d in dialogs:
            groups.setdefault(d.rule or _unmatched_group(d), []).append(d)
        lines = ["dialogs  waited  longest  modes      rule (ask rules of today's settings), or what was asked"]
        for rule, ds in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            waits = [d.waited_minutes for d in ds if d.waited_minutes is not None]
            modes = ",".join(sorted({d.mode for d in ds if d.mode})) or "-"
            lines.append(f"{len(ds):7d}  {_fmt_age(sum(waits)):>6}  {_fmt_age(max(waits, default=0)):>7}  "
                         f"{modes:<9}  {rule}")
        lines.append("(no ask rule matched: an allow rule was missing, or a hook, auto mode or a built-in"
                     " check asked; waits are lower bounds when calls ran in parallel)")
        return "\n".join(lines)
    lines = []
    for d in dialogs:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.opened))
        waited = "-" if d.waited_minutes is None else _fmt_age(d.waited_minutes)
        command = " ".join(d.command.split())
        who = f" [{d.agent_id[:8]}]" if d.agent_id else ""
        lines.append(f"{when}  waited {waited:>7}  {d.outcome:<13}  {d.tool:<5}{who}  "
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
