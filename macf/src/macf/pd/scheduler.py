"""The scheduler: the primal daemon runs its agent's declared schedules (MIS-0002 step 2).

``pd.schedule`` decides what a schedule owes, as pure functions; this runs it. Every fact
it needs after a restart is in the agent's event log, and nothing else is kept
[MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)]:

- ``pd_schedule_seen``: when the daemon first ran a schedule's declaration, the start of
  what it can owe. Nothing before it is owed.
- ``pd_run_started``: the run and the firing it is for, written **before** the run starts,
  so the next run time has moved on before any work is done
  [MIS-0002-R26 (scheduler_MUST_advance_before_run)]. A run that starts late says how late
  [MIS-0002-R34 (late_run_MUST_state_lateness)].
- ``pd_run_done``: how it ended. Each run has a wall-clock limit, and a run past it has its
  process group killed [MIS-0002-R36 (run_MUST_have_wall-clock_limit)].
- ``pd_run_missed``: the firings a downtime missed, once, by the declared policy
  [MIS-0002-R25 (missed-run_policy_MUST_be_listed)]. There is no default policy
  [MIS-0002-R110 (scheduler_MUST-NOT_default_missed-run_policy)], and a missed run whose act
  restarts a unit is never replayed [MIS-0002-R27 (scheduler_MUST-NOT_replay_restart_runs)].

A run still in flight when the daemon restarted is ended and recorded as abandoned, its
process group stopped if it is still that run, so no lease outlives the daemon that held it
[MIS-0002-R28 (scheduler_MUST_release_leases_on_restart)].

A ``command`` run needs no model turn [MIS-0002-R37 (no-judgment_work_SHOULD_skip_model_turn)].
Its declared condition says whether the agent should be woken: ``exit_code``, the way
``grep`` reports, 0 to wake, 1 for nothing to say, anything else a failed run; ``stdout``,
output to wake, a non-zero exit a failed run. Whether a wake is due is recorded in
``pd_run_done``; delivering it waits on a channel source for it.

A ``prompt`` run into an isolated session is a Claude Code client in print mode, the prompt
on its standard input, in a working directory of its own. Its permissions are the ones its
schedule declares, settled when the daemon took the declaration and written before every run
from that, so nothing a run grants itself outlives it
[MIS-0002-R31 (schedule_MUST_settle_permission_at_creation)]. Nothing loads but that settings
file: no user, project or local settings, no MCP server. Anything else that would prompt is
denied at once instead (``dontAsk``, no prompt answerer), so a run never waits on a person. A
run that was denied fails, and raises the ``pd_run_failed`` notice
[MIS-0002-R32 (run_MUST_fail_on_prompt)]. A prompt run into the agent's own live session isn't run yet,
and that is said once.
The schedules are read when the daemon starts and never from a run, so a run cannot change
them [MIS-0002-R33 (run_MUST-NOT_change_schedules)]. Across a restart, a container's
declaration is rendered by root where no run can write it. A host's sits in the agent's own
home, where a run can, so there the change is detected instead: ``pd install``, which the
operator runs, records each schedule's digest (``pd_declaration_installed``), and a daemon whose
schedule differs from that record, or that has none, doesn't run it, says so once, and raises
the ``pd_schedule_changed`` notice. Installing again accepts the change. A run could forge the
install record, since the log is written as the same user, so on a host this detects a change
and doesn't prevent one.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from macf.agent_events_log import append_event, read_events
from macf.notify.session import proc_start, verify_incarnation
from macf.pd.core import group_members
from macf.pd.interface import CommandRun, Declaration, MissedRunPolicy, PromptRun, Schedule, render
from macf.pd.schedule import CronExpr, plan_runs

EVENT_SEEN = "pd_schedule_seen"
EVENT_STARTED = "pd_run_started"
EVENT_DONE = "pd_run_done"
EVENT_MISSED = "pd_run_missed"
EVENT_NOT_RUN = "pd_schedule_not_run"
#: A missed firing its policy defers to a later time (``run_once_in_window``), so a reader can
#: tell a run that waits as declared from one that is late (MIS-0002-R17, R18).
EVENT_DEFERRED = "pd_run_deferred"
#: The run's process, written once it exists, so a later daemon can tell it from a stranger.
EVENT_PID = "pd_run_pid"
#: A schedule's pass that raised, so the daemon skipped that schedule for the pass (#737).
EVENT_PASS_FAILED = "pd_schedule_pass_failed"

#: How long a run past its limit has after SIGTERM before SIGKILL.
KILL_GRACE_S = 5.0
#: How much of a run's output is kept to decide a ``stdout`` wake; none of it is recorded.
STDOUT_PEEK = 4096
#: How much of a prompt run's result is read to find what it was denied.
RESULT_MAX = 4 * 1024 * 1024
#: The notice a prompt run that met a permission prompt raises (MIS-0002-R32).
NOTICE_RUN_FAILED = "pd_run_failed"
#: Each schedule's digest as ``pd install`` took it, the record a host's daemon checks (R33).
EVENT_INSTALLED = "pd_declaration_installed"
#: Where a check template's digest sits among the schedules' (the scheduler design, 4.2).
TEMPLATE_PREFIX = "template:"
#: How much of a check's output is kept for the woken agent to read.
CHECK_OUTPUT_BYTES = 4096
#: The notice a schedule changed since that record raises.
NOTICE_SCHEDULE_CHANGED = "pd_schedule_changed"
#: An agent's own entry, due: its notice's id is the entry's (the scheduler design, 4.1).
NOTICE_ENTRY_DUE = "pd_entry_due"
#: An entry fired for an instant, written before its notice, so a restart never fires it again.
EVENT_ENTRY_FIRED = "pd_entry_fired"
#: How late a firing may be and still count as on time: room for a slow pass, as for schedules.
ENTRY_GRACE_S = 60.0


def schedule_digests(declaration: Declaration, agent_home: Optional[Path] = None) -> Dict[str, str]:
    """Each schedule's digest: its declared form, the timezone its cron is read in, and for a
    prompt run the bytes of its prompt file, which sits in the agent's home where a run can
    rewrite it. A command's script isn't read: its path is digested, its contents aren't."""
    digests = {s.name: hashlib.sha256(json.dumps([declaration.timezone, s.model_dump(mode="json"),
                                                  _prompt_digest(s, agent_home)],
                                                 sort_keys=True).encode()).hexdigest()
               for s in declaration.schedules}
    # A check template is the operator's too, so a template added or changed in a home copy
    # since pd install runs nothing until installed again (the scheduler design, 4.2).
    digests.update({f"{TEMPLATE_PREFIX}{name}": hashlib.sha256(json.dumps(t.model_dump(mode="json"),
                                                                           sort_keys=True).encode()).hexdigest()
                    for name, t in declaration.check_templates.items()})
    return digests


def agent_can_write(program: Path) -> bool:
    """Whether this account can rewrite ``program``: the file itself, or the folder that holds it,
    where it could be replaced. On a shared login that reaches past the agent's home, to a
    package manager's bin among others (MIS-0002-R143)."""
    return os.access(program, os.W_OK) or os.access(program.parent, os.W_OK)


def _prompt_digest(s: Schedule, agent_home: Optional[Path]) -> Optional[str]:
    if not isinstance(s.run, PromptRun):
        return None
    try:
        path = Path(render(s.run.prompt_file, {"agent_home": str(agent_home or "")}))
    except KeyError:
        path = Path(s.run.prompt_file)
    if not path.is_absolute() and agent_home is not None:
        path = Path(agent_home) / path
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "unreadable"  # noqa: MACEFF003 - digested as such, so a file that appears later counts as a change


def installed_digests(card: str, events: Optional[Iterable[dict]] = None) -> Optional[Dict[str, str]]:
    """The schedule digests the newest ``pd install`` recorded for this agent, or None if none
    did. Lifetime state: the install may be any age, so the whole log is in scope."""
    rows = events if events is not None else read_events(reverse=True, scope="all", only=(EVENT_INSTALLED,))
    for event in rows:
        data = event.get("data") or {}
        if event.get("event") == EVENT_INSTALLED and data.get("agent") == card \
                and isinstance(data.get("digests"), dict):
            return {str(k): str(v) for k, v in data["digests"].items()}
    return None


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat()


def _notice_id(name: str, when: datetime) -> str:
    """A notice's id: the schedule's name and an epoch second. It fits the MacEff channel's id
    pattern, ``[A-Za-z0-9._:-]``, as the daemon's other notice ids do. An ISO time carries its
    offset's ``+``, and the channel refuses a record holding one (#734)."""
    return f"{name}:{int(when.timestamp())}"


def _when(text) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(text) if isinstance(text, str) else None
    except ValueError:
        return None  # noqa: MACEFF003 - a time read back that doesn't parse is no time: the row is skipped


@dataclass(frozen=True, kw_only=True)
class _Launch:
    """What a run is started with."""

    command: List[str]
    env: Dict[str, str]
    cwd: Path
    stdin: Optional[Path] = None


@dataclass
class _Run:
    schedule: Schedule
    scheduled_for: datetime
    proc: subprocess.Popen
    started: float                       # monotonic
    stdout_path: Path
    killed_at: Optional[float] = None
    stopped_by: Optional[str] = None     # the daemon stopped it, and why
    term_at: Optional[float] = None      # when its group was sent SIGTERM
    group_left: bool = False             # its leader ended with members still running


@dataclass
class Scheduler:
    """Run an agent's declared schedules; ``boot`` once, then ``tick`` every pass."""

    declaration: Declaration
    card: str
    placeholders: Dict[str, str]
    work_dir: Path
    append: Callable[[str, dict], bool] = append_event
    events: Optional[Callable[[], Iterable[dict]]] = None
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    clock: Callable[[], float] = time.monotonic
    boot_at: Optional[datetime] = None
    last_due: Dict[str, datetime] = field(default_factory=dict)
    since: Dict[str, datetime] = field(default_factory=dict)
    running: Dict[str, _Run] = field(default_factory=dict)
    reported: Dict[str, Optional[datetime]] = field(default_factory=dict)
    #: The Claude Code client a prompt run starts, found on the daemon's PATH at boot.
    client: Optional[str] = None
    #: Owes the agent a notice the daemon raised itself (``Notifier.raise_notice``).
    on_notice: Optional[Callable[[str, str], bool]] = None
    #: The schedules this daemon runs: every command run, and prompt runs it can start.
    runnable: set = field(default_factory=set)
    #: Whether this daemon checks its schedules against what ``pd install`` recorded (R33):
    #: on a host, where the declaration is in the agent's reach, and not where it's rendered.
    check_installed: bool = False
    #: The digests that install recorded, None if none did; read at boot when checking.
    installed: Optional[Dict[str, str]] = None
    #: Each runnable prompt schedule's prompt, read once at boot, where its digest is checked.
    #: Every run in this daemon's life is fed these bytes, so a run that rewrites the file in
    #: the home changes nothing until the next start, where the check refuses it (R33).
    prompts: Dict[str, bytes] = field(default_factory=dict)
    deferred: Dict[str, Optional[datetime]] = field(default_factory=dict)
    #: Each schedule's pass failure last recorded, so the same failure isn't recorded every pass.
    pass_failed: Dict[str, str] = field(default_factory=dict)
    #: The agent's own entries, folded from the event log at boot and added by the daemon as
    #: it records them, and the instant each last fired for.
    entries: Dict[str, dict] = field(default_factory=dict)
    entry_fired: Dict[str, datetime] = field(default_factory=dict)
    #: How late each started run began, by (schedule, firing), until its done record states it.
    late: Dict[tuple, Optional[float]] = field(default_factory=dict)

    def _say(self, event: str, data: dict) -> None:
        # A failed run's notice points to its done record, so that record states how late the
        # run began, not only the record of its start (MIS-0002-R34 (late_run_MUST_state_lateness)).
        if event == EVENT_DONE and "late_s" not in data:
            data = {**data, "late_s": self.late.pop((data.get("schedule"), data.get("scheduled_for")), None)}
        if not self.append(event, {"agent": self.card, **data}):
            print(f"⚠️ MACF: pd: the {event} event for {data.get('schedule')} was not recorded",
                  file=sys.stderr)

    def _tz(self):
        return ZoneInfo(self.declaration.timezone) if self.declaration.timezone else timezone.utc

    # ------------------------------------------------------------------ boot

    def boot(self) -> None:
        """Read back each schedule's last run and first sighting, and end what a previous
        daemon left running (R28)."""
        self.boot_at = self.now()
        if self.check_installed and self.installed is None:
            self.installed = installed_digests(self.card, self.events() if self.events else None)
        names = {s.name for s in self.declaration.schedules}
        open_runs: Dict[tuple, dict] = {}
        done: set = set()
        pids: Dict[tuple, dict] = {}
        read = self.events or (lambda: read_events(reverse=True, scope="all",
                                                   only=(EVENT_SEEN, EVENT_STARTED, EVENT_DONE, EVENT_PID,
                                                         EVENT_MISSED)))
        for event in read():
            data = event.get("data") or {}
            if not isinstance(data, dict) or data.get("agent") != self.card:
                continue
            name = data.get("schedule")
            if name not in names:
                continue
            kind = event.get("event")
            if kind == EVENT_SEEN:
                at = _when(data.get("at"))
                if at is not None:
                    self.since[name] = at                  # reading newest first: the oldest wins
            elif kind == EVENT_DONE:
                done.add((name, data.get("scheduled_for")))
            elif kind == EVENT_MISSED:
                # Missed firings already recorded, so a restart before the next run doesn't
                # record them again (#738). Reading newest first: the newest record wins.
                last = _when(data.get("last"))
                if last is not None:
                    self.reported.setdefault(name, last)
            elif kind == EVENT_PID:
                pids.setdefault((name, data.get("scheduled_for")), data)
            elif kind == EVENT_STARTED:
                key = (name, data.get("scheduled_for"))
                due = _when(data.get("scheduled_for"))
                if due is not None and name not in self.last_due:
                    self.last_due[name] = due
                if key not in done:
                    open_runs.setdefault(key, pids.get(key, {}))
        for (name, scheduled_for), data in open_runs.items():
            self._abandon(name, scheduled_for, data)
        for s in self.declaration.schedules:
            if s.name not in self.since and s.name not in self.last_due:
                self.since[s.name] = self.boot_at
                self._say(EVENT_SEEN, {"schedule": s.name, "at": _iso(self.boot_at)})
            why = self._changed_since_install(s) or self._not_runnable(s)
            if why:
                self._say(EVENT_NOT_RUN, {"schedule": s.name, "reason": why})
            else:
                self.runnable.add(s.name)
                if isinstance(s.run, PromptRun):
                    try:
                        self.prompts[s.name] = self._prompt_path(s).read_bytes()
                    except OSError as e:
                        print(f"⚠️ MACF: pd: the prompt for {s.name} can't be read at start ({e}); "
                              f"its runs fail until the daemon restarts with it in place", file=sys.stderr)
        self._load_entries()

    def _changed_since_install(self, s: Schedule) -> str:
        if not self.check_installed:
            return ""
        if self.installed is None:
            why = "no pd install has recorded this declaration's schedules"
        elif s.name not in self.installed:
            why = "it was added since the last pd install"
        elif self.installed[s.name] != schedule_digests(self.declaration, self._home())[s.name]:
            why = "it changed since the last pd install"
        else:
            return ""
        if self.on_notice is not None:
            self.on_notice(NOTICE_SCHEDULE_CHANGED, _notice_id(s.name, self.boot_at))
        # Only the operator can accept it, so it is said where the operator reads the daemon too.
        print(f"⚠️ MACF: pd: schedule {s.name} is not run: {why}; run `macf_tools pd install` to accept it",
              file=sys.stderr)
        return why + "; run `macf_tools pd install` to accept it (MIS-0002-R33)"

    def _home(self) -> Optional[Path]:
        home = self.placeholders.get("agent_home")
        return Path(home) if home else None

    def _not_runnable(self, s: Schedule) -> str:
        if isinstance(s.run, CommandRun):
            return ""
        if s.target != "isolated":
            return "a prompt run into the agent's own live session is not run yet"
        path, where = self._client_path()
        if self.client is None:
            self.client = shutil.which("claude", path=path)
        if self.client is None:
            return (f"no Claude Code client (claude) is on {where} ({path}); declare a PATH that holds "
                    f"it in the session unit's environment")
        return ""

    def _client_path(self) -> tuple:
        """The PATH a prompt run's client is found on and runs with: the session unit's declared
        one, the environment the agent's own session runs in, else the daemon's. An installed
        daemon gets its service manager's PATH, which on macOS, and on Linux when linger starts
        it before any login, rarely holds the client, so the core finds the session's client
        the same way."""
        for unit in self.declaration.units:
            declared = unit.environment.get("PATH") if unit.kind == "session" else None
            if declared:
                try:
                    return render(declared, self.placeholders), "the session unit's declared PATH"
                except KeyError:
                    break  # noqa: MACEFF003 - a placeholder it can't fill: fall back to the daemon's
        return os.environ.get("PATH", "/usr/bin:/bin"), "the daemon's PATH"

    def _abandon(self, name: str, scheduled_for, data: dict) -> None:
        """A run the previous daemon started and never recorded ending: stop it if it is
        still that process, and record it ended, so its lease does not outlive that daemon."""
        pid, start = data.get("pid"), data.get("proc_start")
        stopped = isinstance(pid, int) and bool(start) and _still_the_runs(pid, start) \
            and _stop_group(pid, name)
        self._say(EVENT_DONE, {"schedule": name, "scheduled_for": scheduled_for,
                               "outcome": "abandoned: the daemon restarted while it ran"
                                          + ("; its process group was stopped" if stopped else ""),
                               "exit_code": None, "wake": False})

    # ------------------------------------------------------------------ the pass

    def tick(self) -> None:
        for name in list(self.running):
            self._guarded(name, lambda: self._check_run(self.running[name]))
        now = self.now()
        for s in self.declaration.schedules:
            if s.name in self.running or s.name not in self.runnable:
                continue
            self._guarded(s.name, lambda: self._pass(s, now))
        for entry_id in list(self.entries):
            self._guarded(entry_id, lambda: self._fire_entry(entry_id, now))

    def add_entry(self, entry: dict) -> None:
        """An entry the daemon has just recorded, so it fires without waiting for a restart."""
        self.entries[entry["id"]] = entry

    def _load_entries(self) -> None:
        """The entries the log folds to, and the instant each last fired for (R16)."""
        from macf.pd.entries import ENTRY_EVENTS, fold
        from macf.pd.notifier import HOLD_MAX_S, SETTLED
        read = self.events or (lambda: read_events(reverse=True, scope="all",
                                                   only=(*ENTRY_EVENTS, EVENT_ENTRY_FIRED, *SETTLED)))
        rows = list(read())                      # newest first
        self.entries = fold(reversed(rows), self.card)
        newest: Dict[str, str] = {}              # each entry's newest firing or delivery
        for event in rows:
            data = event.get("data") or {}
            kind = event.get("event")
            if kind == EVENT_ENTRY_FIRED and data.get("agent") == self.card:
                fired = _when(data.get("for"))
                if fired is not None:
                    self.entry_fired.setdefault(data.get("id"), fired)
                newest.setdefault(data.get("id"), "fired" if data.get("notified", True) else "quiet")
            elif kind in SETTLED and data.get("source") == NOTICE_ENTRY_DUE:
                # Delivered, or kept from the session by the operator's rules: either way not owed
                # again past a day (MIS-0002-R152).
                newest.setdefault(data.get("arrival_id"), "delivered")
        # A notice still owed is held by the notifier through its pd_notices_owed checkpoint,
        # whatever its age. The first start after checkpoints came in reads back only a day, so a
        # wake owed longer is owed again here, under its own id, which the notifier owes once: a
        # wake owed over a weekend must not vanish at a Monday restart (the scheduler design, 4.1).
        for entry_id, last in sorted(newest.items()):
            fired = self.entry_fired.get(entry_id)
            if (last == "fired" and entry_id in self.entries and fired is not None
                    and (self.boot_at - fired).total_seconds() > HOLD_MAX_S and self.on_notice is not None):
                self.on_notice(NOTICE_ENTRY_DUE, entry_id)

    def template_refusal(self, name: Optional[str], args: Dict[str, str]) -> str:
        """Why a check may not run this template with these arguments, or "" when it may: one the
        declaration names, unchanged since pd install where that's checked, whose program isn't in
        the agent's home, where the agent could rewrite it (the scheduler design, 4.2)."""
        template = self.declaration.check_templates.get(name or "")
        if template is None:
            return f"no check template {name!r} is declared"
        if self.check_installed:
            key = f"{TEMPLATE_PREFIX}{name}"
            if self.installed is None or self.installed.get(key) != schedule_digests(self.declaration)[key]:
                return f"the check template {name!r} changed since the last pd install"
        try:
            argv = template.argv(args)
            program = Path(render(argv[0], self.placeholders))
        except (ValueError, KeyError) as e:
            return f"the check's arguments don't fit its template: {e}"
        if not program.is_absolute():
            return f"the template names its program {program} without an absolute path, so what runs isn't fixed"
        if agent_can_write(program.resolve()):
            return f"the template's program {program} is one the agent's account can write, so it could rewrite it"
        return ""

    def _start_check(self, entry_id: str, entry: dict, due: datetime, late_s: float) -> None:
        """Run an entry's check through the declared-command path, as an isolated command run."""
        why = self.template_refusal(entry.get("template"), entry.get("args") or {})
        template = self.declaration.check_templates.get(entry.get("template") or "")
        self.late[(entry_id, _iso(due))] = round(late_s, 1)
        if why or template is None:
            self._say(EVENT_DONE, {"schedule": entry_id, "scheduled_for": _iso(due),
                                   "outcome": f"not started: {why}", "exit_code": None, "wake": False})
            if self.on_notice is not None:
                self.on_notice(NOTICE_RUN_FAILED, _notice_id(entry_id, due))
            return
        run = Schedule(name=entry_id, cron="* * * * *", missed_run=MissedRunPolicy(kind="skip"), target="isolated",
                       run=CommandRun(command=template.argv(entry.get("args") or {}), wake_when=template.wake_when),
                       timeout_s=template.timeout_s)
        self._start(run, due, late_s)

    def _fire_entry(self, entry_id: str, now: datetime) -> None:
        """Fire an entry that is due: once, for the newest instant owed, however many passed while
        the daemon was down. The firing is recorded before the notice is raised (R26)."""
        from macf.pd.entries import OneShot, parse_when
        entry = self.entries[entry_id]
        tz = timezone.utc if entry.get("zone") in (None, "UTC") else ZoneInfo(entry["zone"])
        start = _when(entry.get("start"))
        try:
            when = OneShot(datetime.fromisoformat(entry["when"]))
        except ValueError:
            when = parse_when(entry["when"], tz, start, start=start)
        # Strictly after the start: a recurrence counts its start as its first occurrence, and an
        # entry's start is the moment it was made, so firing it would wake on creation.
        due = when.next_after(self.entry_fired.get(entry_id) or start)
        if due is None or due > now:
            return
        missed = 0
        while (later := when.next_after(due)) is not None and later <= now and missed < 10000:
            due, missed = later, missed + 1
        # A firing a minute past its time was missed. Its entry's policy says whether the agent
        # hears of it: "skip" records it and says nothing (the scheduler design, 3.5).
        late = (now - due).total_seconds() > ENTRY_GRACE_S
        quiet = late and entry.get("missed") == "skip"
        # "report" says it was missed and does nothing else (R25): a late check is reported, not run.
        report_only = late and entry.get("missed") == "report"
        self.entry_fired[entry_id] = due
        if entry.get("action") == "check" and not report_only:
            # A check wakes nobody by firing: its run does, when its condition holds (4.2).
            self._say(EVENT_ENTRY_FIRED, {"id": entry_id, "for": _iso(due), "missed": missed, "notified": False,
                                          "late_s": round((now - due).total_seconds(), 1)})
            if entry_id not in self.running and not quiet:
                self._start_check(entry_id, entry, due, (now - due).total_seconds())
            return
        self._say(EVENT_ENTRY_FIRED, {"id": entry_id, "for": _iso(due), "missed": missed, "notified": not quiet,
                                      "late_s": round((now - due).total_seconds(), 1)})
        if self.on_notice is not None and not quiet:
            self.on_notice(NOTICE_ENTRY_DUE, entry_id)

    def _guarded(self, name: str, step: Callable[[], None]) -> None:
        """Run one schedule's part of a pass. An exception costs that schedule this pass, and
        it's recorded and said once for as long as it repeats. The daemon's loop never sees it,
        so one bad schedule can't stop the units the daemon supervises (#737)."""
        try:
            step()
        except Exception as e:  # one schedule's failure must not end the daemon's loop
            said = f"{type(e).__name__}: {e}"
            if self.pass_failed.get(name) != said:
                self.pass_failed[name] = said
                self._say(EVENT_PASS_FAILED, {"schedule": name, "error": said})
                print(f"⚠️ MACF: pd: schedule {name} failed its pass and was skipped ({said}); "
                      f"the other schedules go on", file=sys.stderr)
        else:
            self.pass_failed.pop(name, None)

    def _pass(self, s: Schedule, now: datetime) -> None:
        """Plan one schedule against the clock, and start its run if one is due."""
        plan = plan_runs(CronExpr.parse(s.cron, self._tz()), s.missed_run,
                         last_due=self.last_due.get(s.name), boot=self.boot_at, now=now,
                         since=self.since.get(s.name), restarts_unit=s.restarts_unit)
        if plan.missed and self.reported.get(s.name) != plan.last_missed:
            self.reported[s.name] = plan.last_missed
            self._say(EVENT_MISSED, {"schedule": s.name, "count": plan.missed,
                                     "first": _iso(plan.first_missed) if plan.first_missed else None,
                                     "last": _iso(plan.last_missed) if plan.last_missed else None,
                                     "policy": s.missed_run.kind})
        if plan.run_at is not None and plan.run_at > now and self.deferred.get(s.name) != plan.scheduled_for:
            self.deferred[s.name] = plan.scheduled_for
            self._say(EVENT_DEFERRED, {"schedule": s.name, "scheduled_for": _iso(plan.scheduled_for),
                                       "run_at": _iso(plan.run_at), "policy": s.missed_run.kind})
        if plan.run_at is not None and plan.run_at <= now:
            self._start(s, plan.scheduled_for, plan.late_s)

    def _start(self, s: Schedule, scheduled_for: datetime, late_s: Optional[float]) -> None:
        # The next run time moves on first (R26): this record is what the next plan reads.
        self.last_due[s.name] = scheduled_for
        self.late[(s.name, _iso(scheduled_for))] = round(late_s, 1) if late_s is not None else None
        self.work_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            if isinstance(s.run, PromptRun):
                launch = self._prompt_run(s)
            else:
                env = {"PATH": "/usr/bin:/bin", "HOME": self.placeholders.get("agent_home", "")}
                env.update({k: render(v, self.placeholders) for k, v in s.run.environment.items()})
                launch = _Launch(command=[render(a, self.placeholders) for a in s.run.command],
                                 env=env, cwd=self.work_dir)
        except KeyError as e:
            self._say(EVENT_DONE, {"schedule": s.name, "scheduled_for": _iso(scheduled_for),
                                   "outcome": f"not started: no value for the placeholder {{{e.args[0]}}}",
                                   "exit_code": None, "wake": False})
            self._notice_failed(s, scheduled_for)
            return
        except OSError as e:
            self._say(EVENT_DONE, {"schedule": s.name, "scheduled_for": _iso(scheduled_for),
                                   "outcome": f"not started: {e}", "exit_code": None, "wake": False})
            self._notice_failed(s, scheduled_for)
            return
        out = self.work_dir / f"{s.name}.stdout"
        self._say(EVENT_STARTED, {"schedule": s.name, "scheduled_for": _iso(scheduled_for),
                                  "late_s": round(late_s, 1) if late_s is not None else None})
        try:
            with open(out, "wb") as sink, open(launch.stdin or os.devnull, "rb") as source:
                proc = subprocess.Popen(launch.command, stdin=source, stdout=sink,
                                        stderr=subprocess.DEVNULL, cwd=str(launch.cwd),
                                        env=launch.env,
                                        start_new_session=True, close_fds=True)
        except OSError as e:
            self._say(EVENT_DONE, {"schedule": s.name, "scheduled_for": _iso(scheduled_for),
                                   "outcome": f"not started: {e}", "exit_code": None, "wake": False})
            self._notice_failed(s, scheduled_for)
            return
        # Its identity, so a later daemon can tell the run from a stranger (R28).
        self._say(EVENT_PID, {"schedule": s.name, "scheduled_for": _iso(scheduled_for),
                                          "pid": proc.pid, "proc_start": proc_start(proc.pid)})
        self.running[s.name] = _Run(s, scheduled_for, proc, self.clock(), out)

    def _prompt_run(self, s: Schedule) -> _Launch:
        """The client's command, environment, working directory and prompt for one run.

        The permissions are the schedule's, written again before every run from the
        declaration the daemon took (R31), and the only settings the client loads."""
        home = self.placeholders.get("agent_home", "")
        if s.name not in self.prompts:
            raise OSError(f"the prompt file {self._prompt_path(s)} couldn't be read when the daemon started")
        prompt = self.work_dir / f"{s.name}.prompt"
        prompt.write_bytes(self.prompts[s.name])
        prompt.chmod(0o600)
        settings = self.work_dir / f"{s.name}.settings.json"
        settings.write_text(json.dumps(settled_permissions(s.run)))
        settings.chmod(0o600)
        cwd = self.work_dir / s.name
        if cwd.exists():
            shutil.rmtree(cwd)
        cwd.mkdir(mode=0o700)
        env = {"PATH": self._client_path()[0], "HOME": home}
        command = [self.client, "--print", "--output-format", "json", "--no-session-persistence",
                   # project settings only, from an empty directory: none load but these
                   "--setting-sources", "project", "--settings", str(settings), "--strict-mcp-config",
                   "--permission-mode", "dontAsk", "--permission-prompts", "none"]
        return _Launch(command=command, env=env, cwd=cwd, stdin=prompt)

    def _prompt_path(self, s: Schedule) -> Path:
        prompt = Path(render(s.run.prompt_file, self.placeholders))
        return prompt if prompt.is_absolute() else Path(self.placeholders.get("agent_home", "")) / prompt

    def _check_run(self, run: _Run) -> None:
        code = run.proc.poll()
        now = self.clock()
        if code is None and run.killed_at is None and now - run.started > run.schedule.timeout_s:
            run.killed_at = now
            self._term(run, now)
        # A run ends when its process group does, not its leader: a member left running
        # would hold whatever the run held past the run's record (R36, R28).
        if code is not None and group_members(run.proc.pid):
            if run.term_at is None:
                run.group_left = True
                self._term(run, now)
            code = None
        if code is None:
            if run.term_at is not None and now - run.term_at > KILL_GRACE_S:
                self._signal(run, signal.SIGKILL)
            return
        del self.running[run.schedule.name]
        outcome, wake = self._judge(run, code)
        if run.group_left and run.stopped_by is None and run.killed_at is None:
            outcome += "; the rest of its process group was stopped"
        is_check = run.schedule.name in self.entries
        if is_check and wake:
            # What moved, kept for the woken agent, so it needn't run a check whose state has moved on.
            kept = self.work_dir / f"{run.schedule.name}.out"
            try:
                with open(run.stdout_path, "rb") as f:
                    kept.write_bytes(f.read(CHECK_OUTPUT_BYTES))
            except OSError:
                kept.write_bytes(b"")
        try:
            run.stdout_path.unlink()
        except FileNotFoundError:
            pass  # noqa: MACEFF003 - the run removed it or never wrote it; nothing is lost
        self._say(EVENT_DONE, {"schedule": run.schedule.name, "scheduled_for": _iso(run.scheduled_for),
                               "outcome": outcome, "exit_code": code, "wake": wake})
        # Failed as `pd status` reads it, less a run stopped on purpose.
        if not outcome.startswith(("ok", "stopped")):
            self._notice_failed(run.schedule, run.scheduled_for)
        elif is_check and wake and self.on_notice is not None:
            self.on_notice(NOTICE_ENTRY_DUE, run.schedule.name)

    def _notice_failed(self, s: Schedule, scheduled_for: datetime) -> None:
        """Owe the agent the failure notice for a run that failed, was killed at its limit, or
        couldn't start (R32, #739). It's raised after the run's done record, which holds what
        the notice points to. Without it, a run that keeps failing looks like one with nothing
        to say: MIS-0002's "an expired login reads as quiet"."""
        if self.on_notice is not None:
            self.on_notice(NOTICE_RUN_FAILED, _notice_id(s.name, scheduled_for))

    def _judge(self, run: _Run, code: int) -> tuple:
        if run.stopped_by is not None:
            return f"stopped: {run.stopped_by}", False
        if run.killed_at is not None:
            return f"killed: past its {run.schedule.timeout_s:g} s limit", False
        if isinstance(run.schedule.run, PromptRun):
            return self._judge_prompt(run, code)
        if run.schedule.run.wake_when == "exit_code":
            if code == 0:
                return "ok: its condition holds", True
            if code == 1:
                return "ok: nothing to say", False
            return f"failed: exit {code}", False
        if code != 0:
            return f"failed: exit {code}", False
        try:
            with open(run.stdout_path, "rb") as f:
                said = f.read(STDOUT_PEEK).strip()
        except OSError:
            said = b""
        return ("ok: it had something to say", True) if said else ("ok: nothing to say", False)

    def _judge_prompt(self, run: _Run, code: int) -> tuple:
        """A prompt run that was denied anything met a permission prompt: it fails, and so the
        agent is owed a notice naming where the facts are (R32). The result's text is never
        recorded."""
        try:
            with open(run.stdout_path, "rb") as f:
                result = json.loads(f.read(RESULT_MAX))
        except (OSError, ValueError) as e:
            return f"failed: exit {code}, its result unreadable ({type(e).__name__})", False
        if isinstance(result, list):
            # The client prints the conversation's messages, the result last.
            result = next((m for m in reversed(result) if isinstance(m, dict) and m.get("type") == "result"), None)
        denials = result.get("permission_denials") if isinstance(result, dict) else None
        if denials:
            tools = sorted({str(d.get("tool_name", "?")) for d in denials if isinstance(d, dict)}) or ["?"]
            return (f"failed: met a permission prompt for {', '.join(tools)}, which its schedule "
                    f"doesn't settle; denied, not waited on"), False
        if code != 0 or (isinstance(result, dict) and result.get("is_error")):
            return f"failed: exit {code}", False
        return "ok: the prompt ran", False

    def _term(self, run: _Run, now: float) -> None:
        run.term_at = now
        self._signal(run, signal.SIGTERM)

    def _signal(self, run: _Run, sig) -> None:
        try:
            os.killpg(run.proc.pid, sig)
        except ProcessLookupError:
            pass  # noqa: MACEFF003 - the group ended between the poll and the signal

    def shutdown(self) -> None:
        """Stop the runs in flight as the daemon stops; each is recorded as it ends."""
        for run in list(self.running.values()):
            run.stopped_by = "the daemon stopped"
            self._term(run, self.clock())
        # The grace, then SIGKILL (in _check_run), then time for the kill to land.
        deadline = self.clock() + KILL_GRACE_S + 2.0
        while self.running and self.clock() < deadline:
            for run in list(self.running.values()):
                self._check_run(run)
            time.sleep(0.05)


def _still_the_runs(pgid: int, start: str) -> bool:
    """Whether process group ``pgid`` is still the recorded run's: its leader is alive with
    the recorded start, or no process leads that number and members remain. A number can't
    be reused while any member of its group lives. A leader there with another start means
    the number now names someone else's group, which is left alone."""
    if verify_incarnation(pgid, start):
        return True
    return proc_start(pgid) is None and bool(group_members(pgid))


def _stop_group(pgid: int, name: str) -> bool:
    """Send group ``pgid`` SIGTERM, then SIGKILL after the grace, and follow it until it is
    empty. Used at boot, where no pass loop is running yet. Returns whether it was signalled."""
    signalled = False
    for sig, wait in ((signal.SIGTERM, KILL_GRACE_S), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(pgid, sig)
            signalled = True
        except ProcessLookupError:
            return signalled  # the group has ended
        except PermissionError as e:
            print(f"⚠️ MACF: pd: cannot stop abandoned run {name} (group {pgid}): {e}", file=sys.stderr)
            return signalled
        end = time.monotonic() + wait
        while time.monotonic() < end and group_members(pgid):
            time.sleep(0.05)
        if not group_members(pgid):
            return signalled
    print(f"⚠️ MACF: pd: abandoned run {name} (group {pgid}) outlived SIGKILL", file=sys.stderr)
    return signalled


def settled_permissions(run: PromptRun) -> dict:
    """The settings a prompt run's client loads, and the only ones: the schedule's tools
    allowed, and anything else denied without a prompt
    (MIS-0002-R31 (schedule_MUST_settle_permission_at_creation))."""
    return {"permissions": {"allow": list(run.allowed_tools), "defaultMode": "dontAsk"}}
