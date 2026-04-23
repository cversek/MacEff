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
    detect_mid_turn_enqueue,
    detect_compact_boundary,
    detect_api_error,
    detect_context_collapse,
]


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
    """Read PID from file, return None if not exists or invalid."""
    pid_file = get_pid_file_path()
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def remove_pid_file() -> None:
    """Remove PID file on shutdown."""
    try:
        get_pid_file_path().unlink(missing_ok=True)
    except OSError:
        pass


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
        self.running = False

        # Stats
        self.entries_processed = 0
        self.events_emitted = 0
        self.last_file_size = 0

    def add_detector(self, detector: Detector) -> "TranscriptMonitor":
        """Register an additional detector. Returns self for chaining."""
        self.detectors.append(detector)
        return self

    def _process_line(self, line: str) -> None:
        """Parse a JSONL line and run all detectors."""
        line = line.strip()
        if not line:
            return
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
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
                        except OSError:
                            pass

                        time.sleep(self.poll_interval)

        except KeyboardInterrupt:
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
            "running": self.running,
            "detectors": len(self.detectors),
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
        print(f"📡 Transcript Monitor already running (PID {pid})")
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
        print(f"📡 Transcript Monitor started (PID {pid})")
        print(f"   Watching: {jsonl_path}")
        print(f"   Poll interval: {poll_interval}s")
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
