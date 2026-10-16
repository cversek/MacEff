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
``pd_run_done``; delivering it waits on a channel source for it. A ``prompt`` run, which
needs an isolated session with its permissions settled, is not run yet and is said so once.
The schedules are read when the daemon starts and never from a run, so a run cannot change
them [MIS-0002-R33 (run_MUST-NOT_change_schedules)].
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from macf.agent_events_log import append_event, read_events
from macf.notify.session import proc_start, verify_incarnation
from macf.pd.core import group_members
from macf.pd.interface import CommandRun, Declaration, Schedule, render
from macf.pd.schedule import CronExpr, plan_runs

EVENT_SEEN = "pd_schedule_seen"
EVENT_STARTED = "pd_run_started"
EVENT_DONE = "pd_run_done"
EVENT_MISSED = "pd_run_missed"
EVENT_NOT_RUN = "pd_schedule_not_run"
#: The run's process, written once it exists, so a later daemon can tell it from a stranger.
EVENT_PID = "pd_run_pid"

#: How long a run past its limit has after SIGTERM before SIGKILL.
KILL_GRACE_S = 5.0
#: How much of a run's output is kept to decide a ``stdout`` wake; none of it is recorded.
STDOUT_PEEK = 4096


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat()


def _when(text) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(text) if isinstance(text, str) else None
    except ValueError:
        return None  # noqa: MACEFF003 - a time read back that doesn't parse is no time: the row is skipped


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

    def _say(self, event: str, data: dict) -> None:
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
        names = {s.name for s in self.declaration.schedules}
        open_runs: Dict[tuple, dict] = {}
        done: set = set()
        pids: Dict[tuple, dict] = {}
        read = self.events or (lambda: read_events(reverse=True, scope="all",
                                                   only=(EVENT_SEEN, EVENT_STARTED, EVENT_DONE, EVENT_PID)))
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
            if not isinstance(s.run, CommandRun):
                self._say(EVENT_NOT_RUN, {"schedule": s.name, "reason": "a prompt run needs an isolated "
                                          "session, which this daemon does not start yet"})

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
            self._check_run(self.running[name])
        now = self.now()
        for s in self.declaration.schedules:
            if s.name in self.running or not isinstance(s.run, CommandRun):
                continue
            plan = plan_runs(CronExpr.parse(s.cron, self._tz()), s.missed_run,
                             last_due=self.last_due.get(s.name), boot=self.boot_at, now=now,
                             since=self.since.get(s.name), restarts_unit=s.restarts_unit)
            if plan.missed and self.reported.get(s.name) != plan.last_missed:
                self.reported[s.name] = plan.last_missed
                self._say(EVENT_MISSED, {"schedule": s.name, "count": plan.missed,
                                         "first": _iso(plan.first_missed) if plan.first_missed else None,
                                         "last": _iso(plan.last_missed) if plan.last_missed else None,
                                         "policy": s.missed_run.kind})
            if plan.run_at is not None and plan.run_at <= now:
                self._start(s, plan.scheduled_for, plan.late_s)

    def _start(self, s: Schedule, scheduled_for: datetime, late_s: Optional[float]) -> None:
        # The next run time moves on first (R26): this record is what the next plan reads.
        self.last_due[s.name] = scheduled_for
        try:
            command = [render(a, self.placeholders) for a in s.run.command]
            env = {"PATH": "/usr/bin:/bin", "HOME": self.placeholders.get("agent_home", "")}
            env.update({k: render(v, self.placeholders) for k, v in s.run.environment.items()})
        except KeyError as e:
            self._say(EVENT_DONE, {"schedule": s.name, "scheduled_for": _iso(scheduled_for),
                                   "outcome": f"not started: no value for the placeholder {{{e.args[0]}}}",
                                   "exit_code": None, "wake": False})
            return
        out = self.work_dir / f"{s.name}.stdout"
        self.work_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._say(EVENT_STARTED, {"schedule": s.name, "scheduled_for": _iso(scheduled_for),
                                  "late_s": round(late_s, 1) if late_s is not None else None})
        try:
            with open(out, "wb") as sink:
                proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=sink,
                                        stderr=subprocess.DEVNULL, cwd=str(self.work_dir),
                                        env=env,
                                        start_new_session=True, close_fds=True)
        except OSError as e:
            self._say(EVENT_DONE, {"schedule": s.name, "scheduled_for": _iso(scheduled_for),
                                   "outcome": f"not started: {e}", "exit_code": None, "wake": False})
            return
        # Its identity, so a later daemon can tell the run from a stranger (R28).
        self._say(EVENT_PID, {"schedule": s.name, "scheduled_for": _iso(scheduled_for),
                                          "pid": proc.pid, "proc_start": proc_start(proc.pid)})
        self.running[s.name] = _Run(s, scheduled_for, proc, self.clock(), out)

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
        try:
            run.stdout_path.unlink()
        except FileNotFoundError:
            pass  # noqa: MACEFF003 - the run removed it or never wrote it; nothing is lost
        self._say(EVENT_DONE, {"schedule": run.schedule.name, "scheduled_for": _iso(run.scheduled_for),
                               "outcome": outcome, "exit_code": code, "wake": wake})

    def _judge(self, run: _Run, code: int) -> tuple:
        if run.stopped_by is not None:
            return f"stopped: {run.stopped_by}", False
        if run.killed_at is not None:
            return f"killed: past its {run.schedule.timeout_s:g} s limit", False
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
