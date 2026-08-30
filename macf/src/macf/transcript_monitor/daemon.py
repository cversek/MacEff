"""
Transcript Monitor Daemon — background JSONL watcher with pluggable detectors.

Monitors the CC session JSONL transcript file in real-time using tail-f style
chunk reads. Detectors classify entries and emit MACF events to the event log.

Architecture:
    JSONL file (CC appends) → daemon polls (1s) → detectors classify → event log

Usage:
    macf_tools transcript-monitor start       # daemonize
    macf_tools transcript-monitor start -f    # foreground
    macf_tools transcript-monitor stop
    macf_tools transcript-monitor status

Pattern follows search_service/daemon.py: PID file lifecycle, signal handling,
daemonize fork, CLI integration.
"""
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..agent_events_log import append_event

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_POLL_INTERVAL = 1.0  # 1 second — negligible CPU, responsive detection
CHUNK_SIZE = 65536  # 64KB read chunks
PID_FILE_NAME = "macf_transcript_monitor.pid"

#: Consecutive stat-failure counts at which the loop reports. A condition that
#: persists must not produce one message per poll; these points give the first
#: occurrence immediately and then back off by an order of magnitude.
_STAT_FAILURE_REPORT_AT = frozenset({1, 10, 100, 1000, 10000})
LOG_FILE_NAME = "macf_transcript_monitor.log"


# ============================================================================
# Detector Protocol
# ============================================================================

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
    """Detect real user messages (not tool results, not meta)."""
    if entry.get("type") != "user":
        return None
    if "toolUseResult" in entry:
        return None
    if entry.get("isMeta"):
        return None
    if entry.get("isCompactSummary"):
        return None

    # Check for channel message (Telegram etc.)
    origin = entry.get("origin")
    source = "direct"
    channel_server = ""
    if isinstance(origin, dict) and origin.get("kind") == "channel":
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


def detect_mid_turn_enqueue(entry: dict) -> Optional[Detection]:
    """Detect mid-turn user message (queue-operation enqueue)."""
    if entry.get("type") != "queue-operation":
        return None
    if entry.get("operation") != "enqueue":
        return None

    return Detection("user_activity_detected", {
        "source": "mid_turn_enqueue",
        "timestamp": entry.get("timestamp", ""),
        "content_preview": str(entry.get("content", ""))[:50],
        "detector": "transcript_monitor",
    })


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
# PID File Management
# ============================================================================

def get_pid_file_path() -> Path:
    """Get path for PID file in runtime directory."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return Path(runtime_dir) / PID_FILE_NAME


def get_log_file_path() -> Path:
    """Get path for daemon stderr log file in runtime directory."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return Path(runtime_dir) / LOG_FILE_NAME


def _detach_standard_streams() -> None:
    """Fully detach the child's standard streams from the parent's environment.

    Redirects stdin/stdout to /dev/null and stderr to a log file. This is the
    textbook daemon-detach: without redirecting fd 2, the child inherits
    whatever stderr the parent had — and if the parent's stderr was part of a
    shell pipeline (e.g. `macf_tools mode set-work X 2>&1 | tail -50`), the
    pipe's read-end stays held open by the daemon's fd 2 and the downstream
    `tail` hangs until the daemon exits (issue #54).

    dup2 implicitly closes the target fd first, so the parent pipe's
    write-end is released even though Python still has an fd 2.
    """
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)  # stdin
    os.dup2(devnull, 1)  # stdout
    try:
        log_fd = os.open(
            str(get_log_file_path()),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o644,
        )
        os.dup2(log_fd, 2)  # stderr → daemon log file
        os.close(log_fd)
    except OSError:
        # Fall back to /dev/null rather than keeping the inherited stderr open.
        os.dup2(devnull, 2)
    os.close(devnull)


def write_pid_file(pid: int) -> None:
    """Write PID to file for service management."""
    get_pid_file_path().write_text(str(pid))


def read_pid_file() -> Optional[int]:
    """Return the recorded daemon pid, or None when there is no usable one.

    None covers two cases the return type cannot separate: the pid file is
    absent, or it is present and unreadable. The unreadable case warns to
    stderr. Callers that treat None as "not running" are correct for the first
    case and wrong for the second.
    """
    pid_file = get_pid_file_path()
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError) as e:
        print(
            f"⚠️ MACF: pid file unreadable, daemon state UNKNOWN and will report "
            f"as NOT RUNNING ({pid_file}): {e}",
            file=sys.stderr,
        )
        return None


def remove_pid_file() -> None:
    """Remove the pid file. Warns to stderr if it could not be removed.

    A pid file left behind makes the next liveness check report this daemon as
    running after it has exited.
    """
    try:
        get_pid_file_path().unlink(missing_ok=True)
    except OSError as e:
        print(
            f"⚠️ MACF: could not remove pid file, a dead daemon may report as "
            f"RUNNING on the next check: {e}",
            file=sys.stderr,
        )


def is_running() -> bool:
    """Check if the transcript monitor daemon is running."""
    pid = read_pid_file()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # signal 0 = check if process exists
        return True
    except OSError:
        remove_pid_file()  # stale PID file
        return False


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
    ):
        self.jsonl_path = jsonl_path
        self.poll_interval = poll_interval
        self.detectors = detectors or list(DEFAULT_DETECTORS)
        self.sources = []
        self.sinks = []
        self.running = False

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
        """Register an additional detector. Returns self for chaining."""
        self.detectors.append(detector)
        return self

    def add_source(self, source) -> "TranscriptMonitor":
        """Register a polled source. Returns self for chaining.

        A detector is FED a transcript entry; a source is ASKED what is new.
        Sources are polled when the transcript is idle, so a busy transcript
        never delays them beyond one poll interval and a quiet one costs a
        directory listing.
        """
        self.sources.append(source)
        return self

    def add_sink(self, sink) -> "TranscriptMonitor":
        """Register a callable invoked with every Detection a source produced.

        Sinks see source detections only. Transcript detectors already have a
        terminus in the event log, and routing them here would silently widen
        what gets delivered to an agent.
        """
        self.sinks.append(sink)
        return self

    def _poll_sources(self) -> None:
        """Ask every source what is new, emit it, and offer it to every sink."""
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
                append_event(detection.event_name, detection.data)
                self.events_emitted += 1
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
                    append_event(detection.event_name, detection.data)
                    self.events_emitted += 1
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
                    send_telegram_notification(text[:1500], prefix=prefix)
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
            append_event("context_rewind_detected", {
                "previous_size": self.last_file_size,
                "current_size": current_size,
                "bytes_lost": self.last_file_size - current_size,
                "detector": "transcript_monitor",
            })
            self.events_emitted += 1
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

                            # If file was truncated, reopen from start
                            if current_size < f.tell():
                                print("📡 TM: file truncated, reopening", file=sys.stderr)
                                break  # exit inner loop, outer caller can restart
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

    def stop(self) -> None:
        """Signal the daemon to stop."""
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

def find_current_transcript() -> Optional[Path]:
    """Find the current session's JSONL transcript file."""
    try:
        from ..utils.session import get_current_session_id
        from ..utils.paths import find_project_root, encode_cc_project_path

        session_id = get_current_session_id()
        project_root = find_project_root()
        cc_home = Path.home() / ".claude"
        encoded = encode_cc_project_path(str(project_root))
        jsonl_path = cc_home / "projects" / encoded / f"{session_id}.jsonl"

        if jsonl_path.exists():
            return jsonl_path
    except (OSError, ImportError, ValueError) as e:
        print(f"⚠️ TM: transcript path resolution failed: {e}", file=sys.stderr)
    return None


def start_daemon(foreground: bool = False, poll_interval: float = DEFAULT_POLL_INTERVAL) -> int:
    """Start the transcript monitor daemon.

    Args:
        foreground: Run in foreground (don't daemonize)
        poll_interval: Seconds between polls (default 1.0)

    Returns:
        0 on success, 1 on error
    """
    if is_running():
        pid = read_pid_file()
        # stderr, not stdout: start_daemon is called from the SessionStart hook,
        # whose stdout must be parseable JSON. See the note on the started-banner
        # below — this branch has the same defect and is merely harder to reach.
        print(f"📡 Transcript Monitor already running (PID {pid})", file=sys.stderr)
        return 0

    jsonl_path = find_current_transcript()
    if jsonl_path is None:
        print("❌ Cannot find session transcript JSONL", file=sys.stderr)
        return 1

    if foreground:
        # Run in foreground
        write_pid_file(os.getpid())
        monitor = TranscriptMonitor(jsonl_path, poll_interval=poll_interval)

        def handle_signal(signum, frame):
            monitor.stop()

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        try:
            monitor.run(start_from_end=True)
        finally:
            remove_pid_file()
        return 0

    # Daemonize: fork to background
    try:
        pid = os.fork()
    except OSError as e:
        print(f"❌ Fork failed: {e}", file=sys.stderr)
        return 1

    if pid > 0:
        # Parent: report and exit
        write_pid_file(pid)
        # stderr, ALL THREE. The SessionStart hook calls this when the monitor is
        # down, and the hook's stdout must parse as JSON. Three lines here made
        # json.loads fail at char 0, so Claude Code never extracted
        # systemMessage and the compaction-recovery banner was silently dropped
        # — the operator saw nothing at all on a compaction restart, while the
        # agent still received the content as unparsed context. A one-directional
        # failure with no error, no warning, and no partial output: it looks
        # exactly like a session where nothing needed saying.
        #
        # Latent because the guard only calls this when the daemon is DOWN, and
        # the daemon persists across sessions. The bug needed a session start
        # coinciding with a dead monitor, which is why it read as intermittent.
        print(f"📡 Transcript Monitor started (PID {pid})", file=sys.stderr)
        print(f"   Watching: {jsonl_path}", file=sys.stderr)
        print(f"   Poll interval: {poll_interval}s", file=sys.stderr)
        return 0

    # Child: become daemon
    os.setsid()

    # Fully detach standard streams — including stderr — so a parent bash
    # pipeline (e.g. `... 2>&1 | tail -50`) doesn't stay held open via the
    # daemon's inherited fd 2 (issue #54).
    _detach_standard_streams()

    monitor = TranscriptMonitor(jsonl_path, poll_interval=poll_interval)

    def handle_signal(signum, frame):
        monitor.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        monitor.run(start_from_end=True)
    finally:
        remove_pid_file()

    os._exit(0)


def stop_daemon() -> int:
    """Stop the running transcript monitor daemon."""
    pid = read_pid_file()
    if pid is None:
        print("📡 Transcript Monitor is not running")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
        # Wait for process to exit
        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(0.5)
            except OSError:
                break
        remove_pid_file()
        print(f"📡 Transcript Monitor stopped (was PID {pid})")
        return 0
    except OSError as e:
        print(f"⚠️ Process {pid} not found: {e}", file=sys.stderr)
        remove_pid_file()
        return 0


def daemon_status() -> int:
    """Print transcript monitor daemon status."""
    pid = read_pid_file()
    if pid is None or not is_running():
        print("⏹️  Transcript Monitor not running")
        return 0

    print(f"✅ Transcript Monitor running (PID {pid})")
    return 0


def ensure_running(poll_interval: float = DEFAULT_POLL_INTERVAL) -> None:
    """Start the daemon if not already running. Called by AUTO_MODE activation."""
    if not is_running():
        start_daemon(foreground=False, poll_interval=poll_interval)
