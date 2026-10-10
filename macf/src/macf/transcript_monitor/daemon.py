"""
Transcript Monitor Daemon — background JSONL watcher with pluggable detectors.

Monitors the CC session JSONL transcript file in real-time using tail-f style
chunk reads. Detectors classify entries and emit MACF events to the event log.

Architecture:
    JSONL file (CC appends) → daemon polls (1s) → detectors classify → event log

Usage:
    macf_tools transcript-monitor start       # in the background
    macf_tools transcript-monitor start -f    # in this terminal
    macf_tools transcript-monitor stop
    macf_tools transcript-monitor status

A monitor is a process of its own, ``python -m macf.transcript_monitor``,
started for one transcript on behalf of one Claude Code process, and it stops
when that process ends. Which monitors run is read from the process table each
time it is asked, never from a file (#529).
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from subprocess import DEVNULL, Popen
from typing import Callable, Dict, List, Optional

from ..agent_events_log import append_event
from ..utils.input_origin import (
    HARNESS_ORIGIN_KINDS,
    opening_channel_source,
    opens_with_harness_notice,
)
from ..utils.paths import user_runtime_dir

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_POLL_INTERVAL = 1.0  # 1 second — negligible CPU, responsive detection
CHUNK_SIZE = 65536  # 64KB read chunks

#: The module a monitor runs as. It is the monitor's name in ``ps``, and how
#: ``find_monitors`` tells a monitor from every other process.
MONITOR_MODULE = "macf.transcript_monitor"

#: Where the code before this one recorded its monitor. That monitor was forked
#: from the session-start hook without exec, so its command line is the hook's
#: and ``find_monitors`` cannot see it; it also never exits on its own.
LEGACY_PID_FILE_NAME = "macf_transcript_monitor.pid"
LEGACY_HOOK_SCRIPT = "session_start.py"
#: A session-start hook finishes within its timeout (60 s by default), so a
#: process with the hook's command line that has run longer is a monitor.
LEGACY_MIN_AGE_S = 120

#: Replaced in the test suite, so that no test starts a real monitor.
_execv = os.execv

#: Consecutive stat-failure counts at which the loop reports. A condition that
#: persists must not produce one message per poll; these points give the first
#: occurrence immediately and then back off by an order of magnitude.
_STAT_FAILURE_REPORT_AT = frozenset({1, 10, 100, 1000, 10000})
LOG_FILE_NAME = "macf_transcript_monitor.log"


# ============================================================================
# Detector Protocol
# ============================================================================

from ..notify.coalescing import coalesce
from ..notify.contracts import validate_detector, validate_sink, validate_source


class Detection:
    """Result from a detector: event name + data to emit."""
    __slots__ = ("event_name", "data")

    def __init__(self, event_name: str, data: dict):
        self.event_name = event_name
        self.data = data


# Type: function(parsed_json_entry) -> Optional[Detection]
Detector = Callable[[dict], Optional[Detection]]


# ============================================================================
# Built-in Detectors
# ============================================================================

def detect_user_activity(entry: dict) -> Optional[Detection]:
    """Detect a message the operator typed or sent through a channel.

    Not tool results, meta entries or compaction summaries, and not input the
    client delivers by itself: a background task's completion notice, or a
    message from another session. The origin record names those; an entry
    written without one is read by how its text opens.
    """
    if entry.get("type") != "user":
        return None
    if "toolUseResult" in entry:
        return None
    if entry.get("isMeta"):
        return None
    if entry.get("isCompactSummary"):
        return None

    origin = entry.get("origin")
    kind = origin.get("kind") if isinstance(origin, dict) else None
    if kind in HARNESS_ORIGIN_KINDS:
        return None
    if kind is None:
        message = entry.get("message")
        content = message.get("content", "") if isinstance(message, dict) else ""
        if opens_with_harness_notice(_entry_text(content)):
            return None

    source = "direct"
    channel_server = ""
    if kind == "channel":
        source = "channel"
        channel_server = origin.get("server", "")

    return Detection("user_activity_detected", {
        "source": source,
        "channel_server": channel_server,
        "timestamp": entry.get("timestamp", ""),
        "detector": "transcript_monitor",
    })


def detect_permission_denial(entry: dict) -> Optional[Detection]:
    """Detect a permission dialog the user answered by rejecting the call.

    `detect_user_activity` deliberately drops entries carrying `toolUseResult`,
    because those are tool results rather than typed messages. A permission
    REJECTION arrives as exactly that shape, so it was dropped too — and the
    framework could mark the user idle while they were gating every tool call
    from the permission surface.

    A rejection is arguably STRONGER presence evidence than a prompt: it proves
    the user is watching the tool stream in real time.

    Shape verified against a live transcript rather than assumed: nine denials,
    every one `type: "user"` with `toolDenialKind: "user-rejected"` and
    `toolUseResult: "User rejected tool use"`. `toolDenialKind` appears on
    denials and nowhere else, which is what makes it a clean discriminator.

    Approvals are NOT covered. An approved ask-gated call is indistinguishable
    from an auto-allowed one at this layer, and inventing presence from an
    ambiguous signal is the failure this whole area already suffers from. The
    rejection path alone fixes the worst case: typed feedback into a dialog,
    followed seconds later by being called idle.
    """
    if entry.get("type") != "user":
        return None
    if not entry.get("toolDenialKind"):
        return None

    return Detection("user_activity_detected", {
        "source": "direct",
        "timestamp": entry.get("timestamp", ""),
        "denial_kind": str(entry.get("toolDenialKind", "")),
        "detector": "transcript_monitor_permission_denial",
    })


def detect_dialog_answer(entry: dict) -> Optional[Detection]:
    """Detect the user answering a question the agent asked in a dialog.

    The answer arrives as a tool result, which `detect_user_activity` drops, so
    a user answering a question was read as idle the moment they had answered.
    An answered question is a `user` entry whose `toolUseResult` holds the
    `questions` asked and the `answers` given. Only a person writes `answers`,
    so, unlike an approval, it is unambiguous, and it is recorded the way a
    rejection is (`detect_permission_denial`): as direct activity. Like a
    rejection, it cannot tell the terminal from a Remote Control view.
    """
    if entry.get("type") != "user":
        return None
    result = entry.get("toolUseResult")
    if not isinstance(result, dict) or not result.get("answers"):
        return None

    return Detection("user_activity_detected", {
        "source": "direct",
        "timestamp": entry.get("timestamp", ""),
        "detector": "transcript_monitor_dialog_answer",
    })


def detect_mid_turn_enqueue(entry: dict) -> Optional[Detection]:
    """Detect a message the session queued (queue-operation enqueue).

    A typed message queued while a turn runs is the operator at the CLI.
    A channel message is not, and it comes through here too: the client
    queues every channel message before delivering it, idle or not, and a
    queue entry carries no origin record. So a queued message whose text
    opens with a channel tag is recorded as ``channel``, with the server
    named by that tag, the way ``detect_user_activity`` records one from its
    origin. Recorded as ``mid_turn_enqueue`` it would end USER_REMOTE on
    every message from the operator's phone. A notice the client queues for
    itself, a background task's or another session's, is not activity at all.
    """
    if entry.get("type") != "queue-operation":
        return None
    if entry.get("operation") != "enqueue":
        return None

    content = entry.get("content", "")
    if isinstance(content, str) and opens_with_harness_notice(content):
        return None
    data = {
        "source": "mid_turn_enqueue",
        "timestamp": entry.get("timestamp", ""),
        "content_preview": str(content)[:50],
        "detector": "transcript_monitor",
    }
    channel_server = opening_channel_source(content) if isinstance(content, str) else None
    if channel_server is not None:
        data["source"] = "channel"
        data["channel_server"] = channel_server
    return Detection("user_activity_detected", data)


def detect_compact_boundary(entry: dict) -> Optional[Detection]:
    """Detect compaction boundary event."""
    if entry.get("type") != "system":
        return None
    if entry.get("subtype") != "compact_boundary":
        return None

    meta = entry.get("compactMetadata", {})
    return Detection("compact_boundary_detected", {
        "trigger": meta.get("trigger", "unknown") if isinstance(meta, dict) else "unknown",
        "pre_tokens": meta.get("preTokens", 0) if isinstance(meta, dict) else 0,
        "timestamp": entry.get("timestamp", ""),
        "detector": "transcript_monitor",
    })


def detect_api_error(entry: dict) -> Optional[Detection]:
    """Detect API error with retry info."""
    if entry.get("type") != "system":
        return None
    if entry.get("subtype") != "api_error":
        return None

    return Detection("api_error_detected", {
        "retry_attempt": entry.get("retryAttempt"),
        "max_retries": entry.get("maxRetries"),
        "timestamp": entry.get("timestamp", ""),
        "detector": "transcript_monitor",
    })


def detect_context_collapse(entry: dict) -> Optional[Detection]:
    """Detect marble-origami context collapse commit."""
    if entry.get("type") != "marble-origami-commit":
        return None

    return Detection("context_collapse_detected", {
        "collapse_id": entry.get("collapseId", ""),
        "summary_preview": str(entry.get("summary", ""))[:100],
        "timestamp": entry.get("timestamp", ""),
        "detector": "transcript_monitor",
    })


# Default detector set
DEFAULT_DETECTORS: List[Detector] = [
    detect_user_activity,
    detect_permission_denial,
    detect_dialog_answer,
    detect_mid_turn_enqueue,
    detect_compact_boundary,
    detect_api_error,
    detect_context_collapse,
]


# ============================================================================
# Channel forwarding (#093) — mirror the live exchange to the remote channel
# ============================================================================

def _entry_text(content) -> str:
    """Best-effort plain text from a transcript message `content` (str or blocks)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p).strip()
    return ""


def extract_forwardable(entry: dict):
    """Classify a transcript entry as a ``(prefix, text)`` to mirror to the channel,
    or ``None``.

    Forwards the agent's narrative (assistant text) and CLI-typed user messages so a
    *remote* operator sees the full exchange, not only turn-finals + tool events.
    Deliberately skips: tool results, meta/compaction entries, and **channel-origin**
    user messages (the operator already sees those on the channel — forwarding them
    would echo their own words back). Pure and side-effect-free, so it is unit-tested
    without the daemon or the network.
    """
    etype = entry.get("type")
    msg = entry.get("message") or {}
    content = msg.get("content")

    if etype == "assistant":
        text = _entry_text(content)
        return ("💬", text) if text else None

    if etype == "user":
        if entry.get("isMeta") or entry.get("isCompactSummary") or "toolUseResult" in entry:
            return None
        origin = entry.get("origin")
        if isinstance(origin, dict) and origin.get("kind") == "channel":
            return None  # already visible on the channel; do not echo it back
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        ):
            return None
        text = _entry_text(content)
        return ("👤 CLI", text) if text else None

    return None


# ============================================================================
# Which Monitors Run
# ============================================================================

def get_log_file_path() -> Path:
    """Get path for the monitors' stderr log file in this user's runtime directory."""
    return user_runtime_dir() / LOG_FILE_NAME


@dataclass(frozen=True)
class MonitorProcess:
    """A live monitor, as the process table shows it."""

    pid: int
    #: When it started. Comparable between processes on one host, nothing more.
    started: float
    #: The Claude Code process it serves; 0 when it was started outside one.
    owner: int
    transcript: Path


def _monitor_from_argv(pid: int, started: float, argv: List[str]) -> Optional[MonitorProcess]:
    """The monitor these arguments start, or None when they start something else."""
    def after(flag: str) -> Optional[str]:
        i = argv.index(flag) + 1 if flag in argv else len(argv)
        return argv[i] if i < len(argv) else None

    transcript, owner = after("--transcript"), after("--owner") or "0"
    if after("-m") != MONITOR_MODULE or transcript is None or not owner.isdigit():
        return None
    return MonitorProcess(pid, started, int(owner), Path(transcript))


def _stat_started(stat: str) -> float:
    """The start time in a Linux ``/proc/<pid>/stat`` line, in seconds since boot.

    Field 22, counted after the parenthesised command name, which may itself
    contain spaces and parentheses.
    """
    return int(stat.rsplit(")", 1)[1].split()[19]) / os.sysconf("SC_CLK_TCK")


def _parse_lstart(text: str) -> float:
    """A start time as ``ps -o lstart`` prints it in the C locale.

    Raises ValueError when *text* is not one.
    """
    return time.mktime(time.strptime(" ".join(text.split()), "%a %b %d %H:%M:%S %Y"))


def _monitors_from_proc(proc: Path) -> List[MonitorProcess]:
    """Monitors in a Linux ``/proc`` tree, with their exact arguments."""
    found = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = [a.decode(errors="replace")
                    for a in (entry / "cmdline").read_bytes().split(b"\0") if a]
            if MONITOR_MODULE not in argv:
                continue
            started = _stat_started((entry / "stat").read_text())
        except (OSError, ValueError, IndexError):
            continue  # it ended while we looked, or is not ours to read
        monitor = _monitor_from_argv(int(entry.name), started, argv)
        if monitor is not None:
            found.append(monitor)
    return found


def _parse_ps(output: str) -> List[MonitorProcess]:
    """Monitors in the output of ``ps -axww -o pid=,lstart=,args=`` in the C locale.

    ``ps`` joins the arguments with spaces. The transcript is the last argument
    a monitor is given, so everything after ``--transcript`` is its path, spaces
    and all.
    """
    found = []
    for line in output.splitlines():
        fields = line.split(None, 6)
        if len(fields) < 7 or not fields[0].isdigit():
            continue
        head, sep, transcript = fields[6].partition(" --transcript ")
        if not sep:
            continue
        try:
            started = _parse_lstart(" ".join(fields[1:6]))
        except ValueError:
            continue
        monitor = _monitor_from_argv(int(fields[0]), started,
                                     head.split() + ["--transcript", transcript.rstrip()])
        if monitor is not None:
            found.append(monitor)
    return found


def _monitors_from_ps() -> Optional[List[MonitorProcess]]:
    try:
        result = subprocess.run(
            ["ps", "-axww", "-o", "pid=,lstart=,args="],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"⚠️ MACF: cannot read the process table, so which transcript "
              f"monitors run is UNKNOWN: {e}", file=sys.stderr)
        return None
    if result.returncode != 0:
        print(f"⚠️ MACF: ps failed ({result.returncode}), so which transcript "
              f"monitors run is UNKNOWN: {result.stderr.strip()}", file=sys.stderr)
        return None
    return _parse_ps(result.stdout)


def find_monitors() -> Optional[List[MonitorProcess]]:
    """Every live transcript monitor on this host, or None when that cannot be read.

    Read from the process table each time, because what runs is a measurement,
    not a record. A pid file stood in for it until #529 and was wrong three ways
    at once: one file per account named one monitor for every agent on that
    account, every monitor that exited deleted the file whichever monitor it
    named, and a forked monitor kept its parent's command line, so nothing could
    find the ones the file had lost.
    """
    proc = Path("/proc")
    if (proc / "self" / "cmdline").exists():
        return _monitors_from_proc(proc)
    return _monitors_from_ps()


def _alive(pid: int) -> bool:
    """Whether *pid* is a live process of this user.

    A pid that answers with PermissionError belongs to another user now, so the
    process that held it has ended and the kernel has reused the number.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


_ETIME = re.compile(r"^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$")


def _parse_etime(text: str) -> Optional[int]:
    """Seconds from ``ps -o etime``'s ``[[dd-]hh:]mm:ss``, or None if it is not one."""
    match = _ETIME.match(text.strip())
    if match is None:
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def legacy_monitor() -> Optional[int]:
    """The pid of a monitor started by the code before this one, if one still runs.

    Three facts identify it, because a pid alone is not proof: the pid in the
    file that code wrote is alive, its command line names the session-start hook,
    and it has run longer than any hook does. A pid that fails any of them is left
    alone.
    """
    path = user_runtime_dir() / LEGACY_PID_FILE_NAME
    if not path.exists():
        return None  # the normal case: no monitor from before the upgrade
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: cannot read {path}: {e}", file=sys.stderr)
        return None
    if not _alive(pid):
        return None
    try:
        out = subprocess.run(["ps", "-ww", "-o", "etime=", "-o", "args=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=10,
                             env={**os.environ, "LC_ALL": "C"}).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        print(f"⚠️ MACF: cannot read process {pid} from ps: {e}", file=sys.stderr)
        return None
    fields = out.split(None, 1)
    if len(fields) != 2:
        return None  # ps printed no such process
    etime, args = fields
    age = _parse_etime(etime)
    if age is None or age < LEGACY_MIN_AGE_S or LEGACY_HOOK_SCRIPT not in args:
        return None
    return pid


def stop_legacy_monitor() -> Optional[int]:
    """Stop a monitor the code before this one started, and remove its pid file.

    Returns the pid it stopped, or None when there was none or it did not exit.
    """
    pid = legacy_monitor()
    if pid is None:
        return None
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(f"⚠️ Could not signal the old-form monitor {pid}: {e}", file=sys.stderr)
        return None
    for _ in range(10):
        if not _alive(pid):
            break
        time.sleep(0.5)
    if _alive(pid):
        print(f"⚠️ The old-form monitor {pid} is still running after 5s", file=sys.stderr)
        return None
    try:
        (user_runtime_dir() / LEGACY_PID_FILE_NAME).unlink()
    except OSError as e:
        print(f"⚠️ MACF: could not remove the old monitor's pid file: {e}", file=sys.stderr)
    print(f"📡 Stopped a transcript monitor started before the upgrade (PID {pid})", file=sys.stderr)
    return pid


def _process_started(pid: int) -> Optional[float]:
    """When process *pid* started, in the units of ``MonitorProcess.started``.

    None when the process table does not say: there is no such process, or its
    answer could not be read, which is warned on stderr.
    """
    if pid <= 0:
        return None
    stat = Path("/proc") / str(pid) / "stat"
    if Path("/proc/self/cmdline").exists():
        if not stat.exists():
            return None
        try:
            return _stat_started(stat.read_text())
        except (OSError, ValueError, IndexError) as e:
            print(f"⚠️ MACF: cannot read when process {pid} started: {e}", file=sys.stderr)
            return None
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"⚠️ MACF: cannot read when process {pid} started: {e}", file=sys.stderr)
        return None
    if result.returncode != 0:
        return None  # ps exits non-zero when there is no such process
    try:
        return _parse_lstart(result.stdout)
    except ValueError as e:
        print(f"⚠️ MACF: cannot read when process {pid} started: {e}", file=sys.stderr)
        return None


def _serving(monitor: MonitorProcess) -> bool:
    """A monitor serves while its Claude Code process lives, or, when it was
    started outside one, until it is stopped.

    The owner started the monitor, so the owner is the older of the two. A
    process under the owner's pid that started after the monitor took the
    number once the owner had ended; another user's is caught by ``_alive``,
    this user's only by its start time. A monitor that saw its owner end would
    have stopped within a poll, so this guards the judgment made from outside:
    of a monitor that is stopped or stuck, long after its owner ended. When the
    start time cannot be read, the pid alone decides, as before.
    """
    if monitor.owner == 0:
        return True
    if not _alive(monitor.owner):
        return False
    owner_started = _process_started(monitor.owner)
    return owner_started is None or owner_started <= monitor.started


def _session_owner() -> int:
    """The Claude Code process the caller runs under, or 0 outside one.

    Claude Code gives its hooks and tool commands its own pid as ``CLAUDE_PID``.
    """
    try:
        return int(os.environ.get("CLAUDE_PID") or 0)
    except ValueError:
        return 0


def _duplicate_of(pid: int, transcript: Path, monitors: List[MonitorProcess]) -> Optional[MonitorProcess]:
    """The older monitor that already serves *transcript*, if monitor *pid* is a second one.

    Two monitors on one transcript write every event twice. The older one keeps
    its place in the transcript and the newer one gives way, which every monitor
    decides the same way, so exactly one of any pair stays.
    """
    me = next((m for m in monitors if m.pid == pid), None)
    if me is None:
        return None
    older = [m for m in monitors
             if m.pid != pid and m.transcript == transcript and _serving(m)
             and (m.started, m.pid) < (me.started, me.pid)]
    return min(older, key=lambda m: (m.started, m.pid), default=None)


def _serving_on(transcript: Path, monitors: List[MonitorProcess]) -> Optional[MonitorProcess]:
    """The oldest monitor that serves *transcript*, or None."""
    serving = [m for m in monitors if m.transcript == transcript and _serving(m)]
    return min(serving, key=lambda m: (m.started, m.pid), default=None)


def is_running(transcript: Optional[Path] = None) -> bool:
    """Whether a monitor serves this session's transcript.

    Per transcript, and so per agent: agents that share an account have their
    own transcripts and never count each other's monitor (#529). When the
    process table cannot be read the answer is unknown, and it is given as
    running, so that no caller starts a monitor blind: a missing monitor is
    announced (above, on stderr) and a duplicate is silent.
    """
    transcript = transcript or find_current_transcript()
    if transcript is None:
        return False
    monitors = find_monitors()
    if monitors is None:
        return True
    return _serving_on(transcript, monitors) is not None


# ============================================================================
# Transcript Monitor Daemon
# ============================================================================

class TranscriptMonitor:
    """
    Background daemon that watches a JSONL transcript file and emits MACF events.

    Uses tail-f style chunk reads: open file, seek to position, read chunks,
    parse lines, run detectors, emit events. Poll interval default 1s —
    negligible CPU on empty reads, responsive detection on new content.
    """

    def __init__(
        self,
        jsonl_path: Path,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        detectors: Optional[List[Detector]] = None,
        owner: int = 0,
    ):
        self.jsonl_path = jsonl_path
        self.poll_interval = poll_interval
        self.detectors = detectors or list(DEFAULT_DETECTORS)
        self.sources = []
        self.sinks = []
        self.running = False
        # The Claude Code process this monitor serves (0: none, run until stopped)
        # and, once the loop has ended, why it ended.
        self.owner = owner
        self.stop_reason: Optional[str] = None

        # Stats
        self.entries_processed = 0
        self.events_emitted = 0
        self.unparsed_lines = 0
        self.stat_failures = 0
        self.source_failures = 0
        self.sink_failures = 0
        self.last_file_size = 0

        # Channel forwarding: USER_REMOTE state, re-checked at most every 5s so a
        # per-line mode read does not thrash the event log on a busy transcript.
        self._fwd_checked_at = 0.0
        self._fwd_cached = False

    def add_detector(self, detector: Detector) -> "TranscriptMonitor":
        """Register an additional detector. Returns self for chaining.

        Validated HERE rather than at first use: a detector is invoked inside a
        guard that treats failure as non-fatal, so a wrongly shaped one would
        raise into a log nobody reads and otherwise look installed forever.
        """
        self.detectors.append(validate_detector(detector))
        return self

    def add_source(self, source) -> "TranscriptMonitor":
        """Register a polled source. Returns self for chaining.

        A detector is FED a transcript entry; a source is ASKED what is new.
        Sources are polled when the transcript is idle, so a busy transcript
        never delays them beyond one poll interval and a quiet one costs a
        directory listing.
        """
        self.sources.append(validate_source(source))
        return self

    def add_sink(self, sink) -> "TranscriptMonitor":
        """Register a callable invoked with every Detection a source produced.

        Sinks see source detections only. Transcript detectors already have a
        terminus in the event log, and routing them here would silently widen
        what gets delivered to an agent.
        """
        self.sinks.append(validate_sink(sink))
        return self

    def _emit(self, event_name: str, data: dict) -> None:
        """Record an event, naming the monitor that wrote it.

        With the writer's pid in every event, a duplicate shows up as two pids
        for one boundary instead of as copies nobody can tell apart (#529).
        """
        append_event(event_name, {**data, "monitor_pid": os.getpid()})
        self.events_emitted += 1

    def _poll_sources(self) -> None:
        """Ask every source what is new, emit it, and offer it to every sink."""
        cycle = []
        for source in self.sources:
            try:
                detections = source.poll()
            except Exception as e:  # noqa: BLE001 - GUARD, not handler: see coding_standards
                # A source is an optional input. Its failure must not stop the
                # monitor observing the transcript, which is its primary job.
                self.source_failures += 1
                print(f"⚠️ MACF: source poll failed (monitor continues): {e}", file=sys.stderr)
                continue
            for detection in detections or ():
                self._emit(detection.event_name, detection.data)
                cycle.append(detection)

        # THE FLOOR IS APPLIED HERE, ACROSS SOURCES, AND ONLY TO THE SINK PATH.
        # Every detection above is already in the event log individually -- the
        # log is the archaeology and collapsing it would destroy the record of
        # what actually arrived. What is coalesced is what INTERRUPTS: two
        # sources reporting in one cycle are one thing to look at, not two.
        #
        # It lives in the daemon rather than in each source because a floor each
        # source implements for itself is a floor the next source forgets.
        for detection in coalesce(cycle):
            for sink in self.sinks:
                try:
                    sink(detection)
                except Exception as e:  # noqa: BLE001 - GUARD, not handler
                    self.sink_failures += 1
                    print(f"⚠️ MACF: sink failed for {detection.event_name} "
                          f"(event still recorded): {e}", file=sys.stderr)

    def _process_line(self, line: str) -> None:
        """Parse a JSONL line and run all detectors."""
        line = line.strip()
        if not line:
            return
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            self.unparsed_lines += 1
            print(
                f"⚠️ MACF: transcript line {self.entries_processed + self.unparsed_lines} "
                f"is not valid JSON, skipped and NOT observed by any detector: {e}",
                file=sys.stderr,
            )
            return

        self.entries_processed += 1

        for detector in self.detectors:
            try:
                detection = detector(entry)
                if detection is not None:
                    self._emit(detection.event_name, detection.data)
            except (OSError, ValueError, TypeError) as e:
                print(f"⚠️ TM: detector error: {e}", file=sys.stderr)

        # Channel forwarding (#093): when the operator is remote, mirror the agent's
        # narrative and CLI-typed user messages to the channel so they see the full
        # exchange — not only turn-finals + tool events. Gated on USER_REMOTE (no
        # noise when present), reuses the shared telegram module, best-effort.
        try:
            if self._forward_to_channel_enabled():
                fwd = extract_forwardable(entry)
                if fwd:
                    prefix, text = fwd
                    from ..channels.telegram import send_telegram_notification
                    send_telegram_notification(text[:1500], prefix=prefix, trace=True)
        except Exception as e:  # noqa: BLE001 - GUARD, not handler: see coding_standards
            # Mirroring to the channel is best-effort and must never take down
            # the monitor. Nothing here depends on which exception occurred, so
            # enumerating types would only add a way to crash.
            print(f"⚠️ TM: channel forward failed (non-blocking): {e}", file=sys.stderr)

    def _forward_to_channel_enabled(self) -> bool:
        """True iff USER_REMOTE is active. Cached for 5s to bound event-log reads.

        Returns False when the mode cannot be determined, and warns to stderr:
        forwarding stops, which is indistinguishable from an operator who is not
        remote unless the failure is announced.
        """
        now = time.time()
        if now - self._fwd_checked_at < 5.0:
            return self._fwd_cached
        self._fwd_checked_at = now
        try:
            from ..modes.detection import _detect_user_remote
            from ..utils import get_current_session_id
            self._fwd_cached = bool(_detect_user_remote(get_current_session_id()))
        except Exception as e:  # noqa: BLE001 - GUARD, not handler: see coding_standards
            # Deliberately broad: this is a GUARD, not a handler. Mode detection
            # is best-effort and must never take down the monitor, so an
            # enumerated list would eventually miss a type and crash for exactly
            # the thing the guard exists to absorb. Nothing here is recovered —
            # it is announced and forwarding stays off.
            print(
                f"⚠️ MACF: cannot determine USER_REMOTE, channel forwarding is OFF "
                f"until this clears: {e}",
                file=sys.stderr,
            )
            self._fwd_cached = False
        return self._fwd_cached

    def _detect_rewind(self, current_size: int) -> None:
        """Check if JSONL was truncated (context rewind)."""
        if self.last_file_size > 0 and current_size < self.last_file_size:
            self._emit("context_rewind_detected", {
                "previous_size": self.last_file_size,
                "current_size": current_size,
                "bytes_lost": self.last_file_size - current_size,
                "detector": "transcript_monitor",
            })
        self.last_file_size = current_size

    def run(self, start_from_end: bool = True) -> None:
        """
        Main daemon loop. Tail-f style chunk reads.

        Args:
            start_from_end: If True, seek to end of file (skip history).
                           If False, process from beginning.
        """
        self.running = True
        buffer = ""

        print(f"📡 Transcript Monitor started", file=sys.stderr)
        print(f"   Watching: {self.jsonl_path}", file=sys.stderr)
        print(f"   Poll interval: {self.poll_interval}s", file=sys.stderr)
        print(f"   Detectors: {len(self.detectors)}", file=sys.stderr)

        try:
            with open(self.jsonl_path, 'r', errors='replace') as f:
                if start_from_end:
                    f.seek(0, 2)  # seek to end
                    self.last_file_size = f.tell()

                while self.running:
                    data = f.read(CHUNK_SIZE)

                    if data:
                        buffer += data
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            self._process_line(line)
                    else:
                        # No new data — check for rewind, then sleep
                        try:
                            current_size = self.jsonl_path.stat().st_size
                            self._detect_rewind(current_size)

                            # A truncated file ends this monitor; nothing starts
                            # another before the next session start.
                            if current_size < f.tell():
                                print("📡 TM: file truncated, stopping", file=sys.stderr)
                                self.stop("the transcript was truncated")
                                break
                        except OSError as e:
                            self.stat_failures += 1
                            if self.stat_failures in _STAT_FAILURE_REPORT_AT:
                                print(
                                    f"⚠️ MACF: cannot stat the transcript "
                                    f"({self.stat_failures} consecutive), so truncation "
                                    f"and rewind are undetectable; still polling: {e}",
                                    file=sys.stderr,
                                )
                        else:
                            self.stat_failures = 0

                        # Sources are polled on the idle path deliberately: the
                        # transcript is the primary input and must never wait
                        # behind a directory listing.
                        self._poll_sources()

                        # A monitor serves one Claude Code process. When that
                        # process ends, so does the monitor's job; the next
                        # session starts its own (#529).
                        if self.owner and not _alive(self.owner):
                            self.stop(f"its Claude Code process {self.owner} ended")
                            break

                        time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            # Ordinary shutdown path: the finally block reports the totals.
            pass
        finally:
            self.running = False
            print(
                f"\n📡 Transcript Monitor stopped. "
                f"Processed {self.entries_processed} entries, "
                f"emitted {self.events_emitted} events.",
                file=sys.stderr,
            )

    def stop(self, reason: str = "stopped") -> None:
        """Signal the loop to end. The first reason given is the one kept."""
        self.stop_reason = self.stop_reason or reason
        self.running = False

    def get_stats(self) -> dict:
        """Return daemon statistics."""
        return {
            "jsonl_path": str(self.jsonl_path),
            "entries_processed": self.entries_processed,
            "events_emitted": self.events_emitted,
            "unparsed_lines": self.unparsed_lines,
            "stat_failures": self.stat_failures,
            "source_failures": self.source_failures,
            "sink_failures": self.sink_failures,
            "running": self.running,
            "detectors": len(self.detectors),
            "sources": len(self.sources),
            "sinks": len(self.sinks),
            "poll_interval": self.poll_interval,
        }


# ============================================================================
# Daemon Lifecycle (start/stop/status)
# ============================================================================

def _transcripts_dir() -> Path:
    """This agent's Claude Code transcript directory: one per project root."""
    from ..utils.paths import find_project_root, encode_cc_project_path
    return Path.home() / ".claude" / "projects" / encode_cc_project_path(str(find_project_root()))


def find_current_transcript() -> Optional[Path]:
    """Find the current session's JSONL transcript file."""
    try:
        from ..utils.session import get_current_session_id

        jsonl_path = _transcripts_dir() / f"{get_current_session_id()}.jsonl"
        if jsonl_path.exists():
            return jsonl_path
    except (OSError, ImportError, ValueError) as e:
        print(f"⚠️ TM: transcript path resolution failed: {e}", file=sys.stderr)
    return None


def _monitor_argv(transcript: Path, poll_interval: float, owner: int) -> List[str]:
    """The command that runs one monitor.

    The transcript goes last: it is the one argument that may contain spaces,
    and ``ps`` shows the arguments joined with them.
    """
    return [sys.executable, "-m", MONITOR_MODULE,
            "--interval", str(poll_interval), "--owner", str(owner),
            "--transcript", str(transcript)]


def start_daemon(foreground: bool = False, poll_interval: float = DEFAULT_POLL_INTERVAL) -> int:
    """Start a monitor for this session's transcript, unless one already serves it.

    The monitor is a fresh interpreter, not a fork of the caller. A fork kept
    the caller's command line, so ``ps`` showed a monitor as the hook or command
    that started it, it ran that caller's code for as long as it lived, and it
    inherited whatever context the caller had open (#492, #529).

    Args:
        foreground: Become the monitor in this process instead
        poll_interval: Seconds between polls (default 1.0)

    Returns:
        0 on success, 1 on error
    """
    # A monitor the code before this one started is invisible to find_monitors,
    # so it would serve beside the new one and outlive it.
    stop_legacy_monitor()
    if is_running():
        # stderr, not stdout: start_daemon is called from the SessionStart hook,
        # whose stdout must be parseable JSON. See the note on the started-banner
        # below.
        print("📡 Transcript Monitor already running on this transcript", file=sys.stderr)
        return 0

    jsonl_path = find_current_transcript()
    if jsonl_path is None:
        print("❌ Cannot find session transcript JSONL", file=sys.stderr)
        return 1

    argv = _monitor_argv(jsonl_path, poll_interval, _session_owner())

    if foreground:
        # The same command a background start runs, so a monitor run in a
        # terminal is found and counted like any other.
        try:
            _execv(argv[0], argv)  # replaces this process; returns only on failure
        except OSError as e:
            print(f"❌ Could not run the Transcript Monitor: {e}", file=sys.stderr)
        return 1

    # The monitor's stderr goes to the log, and it holds nothing else of the
    # caller's: with an inherited pipe as stderr, a caller's pipeline (`... 2>&1
    # | tail`) stayed open until the monitor died (#54).
    try:
        log_fd = os.open(str(get_log_file_path()), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    except OSError as e:
        print(f"⚠️ TM: no monitor log ({e}); its stderr is discarded", file=sys.stderr)
        log_fd = DEVNULL
    try:
        proc = Popen(argv, stdin=DEVNULL, stdout=DEVNULL, stderr=log_fd,
                     start_new_session=True, close_fds=True)
    except OSError as e:
        print(f"❌ Could not start the Transcript Monitor: {e}", file=sys.stderr)
        return 1
    finally:
        if log_fd != DEVNULL:
            os.close(log_fd)

    # stderr, ALL THREE. The SessionStart hook calls this when the monitor is
    # down, and the hook's stdout must parse as JSON. Three lines here made
    # json.loads fail at char 0, so Claude Code never extracted
    # systemMessage and the compaction-recovery banner was silently dropped
    # — the operator saw nothing at all on a compaction restart, while the
    # agent still received the content as unparsed context. A one-directional
    # failure with no error, no warning, and no partial output: it looks
    # exactly like a session where nothing needed saying.
    print(f"📡 Transcript Monitor started (PID {proc.pid})", file=sys.stderr)
    print(f"   Watching: {jsonl_path}", file=sys.stderr)
    print(f"   Poll interval: {poll_interval}s", file=sys.stderr)
    return 0


def run_monitor(transcript: Path, poll_interval: float = DEFAULT_POLL_INTERVAL, owner: int = 0) -> int:
    """Be one monitor on *transcript*, in this process, until there is a reason to stop.

    The reasons: a signal, the end of the Claude Code process *owner*, a
    truncated transcript, or, at the start, an older monitor that already serves
    the transcript. The start and the end are events, so the event log records
    which monitors ran, for how long, and why each ended.
    """
    me = os.getpid()
    monitors = find_monitors()
    older = _duplicate_of(me, transcript, monitors) if monitors else None
    identity = {"pid": me, "owner": owner, "transcript": str(transcript)}
    append_event("transcript_monitor_started", identity)

    monitor = TranscriptMonitor(transcript, poll_interval=poll_interval, owner=owner)
    if older is not None:
        monitor.stop(f"monitor {older.pid} already serves this transcript")
    else:
        def handle_signal(signum, frame):
            monitor.stop(f"signal {signum}")

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)
    try:
        if older is None:
            monitor.run(start_from_end=True)
    finally:
        append_event("transcript_monitor_stopped", {
            **identity,
            "reason": monitor.stop_reason or "ended without a reason (see the monitor log)",
            "entries_processed": monitor.entries_processed,
            "events_emitted": monitor.events_emitted,
        })
    return 0


def _agent_monitors(monitors: List[MonitorProcess]) -> List[MonitorProcess]:
    """This agent's monitors: those on a transcript in its project's directory."""
    directory = _transcripts_dir()
    return sorted((m for m in monitors if m.transcript.parent == directory),
                  key=lambda m: (m.started, m.pid))


def stop_daemon() -> int:
    """Stop every monitor of this agent, including one the code before this one started."""
    stop_legacy_monitor()
    monitors = find_monitors()
    if monitors is None:
        print("⚠️ Which monitors run is unknown; nothing was signaled.", file=sys.stderr)
        return 1
    mine = _agent_monitors(monitors)
    if not mine:
        print("📡 Transcript Monitor is not running")
        return 0

    for m in mine:
        try:
            os.kill(m.pid, signal.SIGTERM)
        except OSError as e:
            print(f"⚠️ Could not signal monitor {m.pid}: {e}", file=sys.stderr)

    # Wait for them to exit
    for _ in range(10):
        if not any(_alive(m.pid) for m in mine):
            break
        time.sleep(0.5)
    still = [m.pid for m in mine if _alive(m.pid)]
    stopped = [m.pid for m in mine if m.pid not in still]
    if stopped:
        print(f"📡 Transcript Monitor stopped (was PID {', '.join(map(str, stopped))})")
    if still:
        print(f"⚠️ Still running after 5s: PID {', '.join(map(str, still))}", file=sys.stderr)
        return 1
    return 0


def daemon_status() -> int:
    """Print this agent's monitors, one line each."""
    legacy = legacy_monitor()
    if legacy is not None:
        print(f"⚠️ A transcript monitor started before the upgrade is running (PID {legacy}); "
              f"'macf_tools transcript-monitor start' or 'stop' stops it")
    monitors = find_monitors()
    if monitors is None:
        print("❓ Transcript Monitor state unknown: the process table cannot be read")
        return 1
    mine = _agent_monitors(monitors)
    if not mine:
        print("⏹️  Transcript Monitor not running")
        return 0

    current = find_current_transcript()
    for m in mine:
        notes = []
        if m.transcript != current:
            notes.append("not this session's transcript")
        if not _serving(m):
            notes.append(f"its Claude Code process {m.owner} has ended")
        suffix = f" ({'; '.join(notes)})" if notes else ""
        print(f"✅ Transcript Monitor running (PID {m.pid}) on {m.transcript.name}{suffix}")
    return 0


def ensure_running(poll_interval: float = DEFAULT_POLL_INTERVAL) -> None:
    """Start the daemon if not already running. Called by AUTO_MODE activation."""
    if not is_running():
        start_daemon(foreground=False, poll_interval=poll_interval)
