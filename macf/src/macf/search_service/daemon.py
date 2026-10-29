"""
SearchService Daemon - Persistent socket server with pluggable retrievers.

Generic infrastructure for warm search services. The service loads heavy
dependencies once at startup, then accepts queries over TCP socket.

Architecture mirrors BaseIndexer pattern:
- SearchService = generic socket infrastructure
- AbstractRetriever = domain-specific search logic (pluggable)

Protocol (newline-delimited JSON):
    Request:  {"namespace": "policy", "query": "...", "limit": 5}
    Response: {"formatted": "...", "explanations": [...], "search_time_ms": 45}

Usage:
    # Create service with retrievers
    service = SearchService()
    service.register(PolicyRetriever())
    service.start()

    # Or via CLI
    macf_tools search-service start
"""

import json
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from .retrievers.base import AbstractRetriever, SearchResult

# Default configuration
DEFAULT_PORT = 9001
DEFAULT_HOST = "127.0.0.1"
PID_FILE_NAME = "macf_search_service.pid"


def get_pid_file_path() -> Path:
    """Get path for PID file in runtime directory."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return Path(runtime_dir) / PID_FILE_NAME


def write_pid_file(pid: int) -> None:
    """Write PID to file for service management."""
    pid_file = get_pid_file_path()
    pid_file.write_text(str(pid))


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
    pid_file = get_pid_file_path()
    try:
        pid_file.unlink(missing_ok=True)
    except OSError:
        pass


#: How long the load-phase ticker vouches for a model load before it stops, so a load that
#: hangs reads overdue to the primal daemon instead of alive forever.
LOAD_TICK_LIMIT_S = 600.0


class _LoadTicker:
    """Ticks a unit's heartbeat about once a second while one blocking call (the model
    load) runs, for at most ``limit_s``."""

    def __init__(self, tick: Callable[[], None], period_s: float = 1.0,
                 limit_s: Optional[float] = None):
        import threading
        self._tick, self._period = tick, period_s
        self._limit = LOAD_TICK_LIMIT_S if limit_s is None else limit_s
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, name="search-load-ticker", daemon=True)

    def start(self) -> "_LoadTicker":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._done.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        deadline = time.monotonic() + self._limit
        while not self._done.wait(self._period):
            if time.monotonic() >= deadline:
                print(f"⚠️ MACF: search service unit: the model has not loaded in {self._limit:g} s; "
                      f"no more liveness until it does", file=sys.stderr)
                return
            self._tick()


class SearchService:
    """Socket-based search service with pluggable retrievers.

    Register retrievers for different namespaces, then start the service.
    Queries are routed to the appropriate retriever by namespace.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.retrievers: dict[str, AbstractRetriever] = {}
        #: Called once per pass of the serve loop (at least once a second, the accept
        #: timeout). A primal daemon unit sets it to its heartbeat's ``tick``.
        self.on_pass: Callable[[], None] = lambda: None
        self._serving = False

    def register(self, retriever: AbstractRetriever) -> "SearchService":
        """Register a retriever for its namespace.

        Args:
            retriever: Retriever instance to register

        Returns:
            self for chaining
        """
        self.retrievers[retriever.namespace] = retriever
        return self

    def _warmup_retrievers(self) -> None:
        """Warm up all registered retrievers."""
        for namespace, retriever in self.retrievers.items():
            print(f"Warming up retriever: {namespace}...", file=sys.stderr)
            start = time.perf_counter()
            retriever.warmup()
            warmup_time = time.perf_counter() - start
            print(f"  {namespace} ready in {warmup_time:.2f}s", file=sys.stderr)

    def _handle_request(self, request: dict) -> SearchResult:
        """Route request to appropriate retriever."""
        namespace = request.get("namespace", "policy")  # Default to policy
        query = request.get("query", "")
        limit = request.get("limit", 5)

        if not query:
            return SearchResult(formatted="", error="empty_query")

        if namespace not in self.retrievers:
            return SearchResult(
                formatted="",
                error=f"unknown_namespace: {namespace}",
            )

        return self.retrievers[namespace].search(query, limit=limit)

    def _handle_client(self, client_socket: socket.socket) -> None:
        """Handle a single client connection."""
        try:
            # Read JSON request (newline-delimited)
            data = b""
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            if not data:
                return

            request_text = data.decode("utf-8").split("\n")[0]
            request = json.loads(request_text)

            # Route to retriever
            result = self._handle_request(request)

            # Send response
            response_json = json.dumps(result.to_dict()) + "\n"
            client_socket.sendall(response_json.encode())

            # Log query
            namespace = request.get("namespace", "policy")
            query = request.get("query", "")[:50]
            suffix = "..." if len(request.get("query", "")) > 50 else ""
            print(
                f"[{namespace}] {query}{suffix} -> {result.search_time_ms:.1f}ms",
                file=sys.stderr
            )

        except json.JSONDecodeError as e:
            error_response = SearchResult(formatted="", error=f"invalid_json: {e}")
            try:
                client_socket.sendall(
                    (json.dumps(error_response.to_dict()) + "\n").encode()
                )
            except OSError as e:
                print(f"⚠️ MACF: failed to send JSON decode error response to client: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error handling client: {e}", file=sys.stderr)
            try:
                error_response = SearchResult(formatted="", error=str(e))
                client_socket.sendall(
                    (json.dumps(error_response.to_dict()) + "\n").encode()
                )
            except OSError as send_err:
                print(f"⚠️ MACF: failed to send error response to client: {send_err}", file=sys.stderr)
        finally:
            try:
                client_socket.close()
            except OSError as e:
                print(f"⚠️ MACF: failed to close client socket: {e}", file=sys.stderr)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        print(f"\nReceived signal {signum}, shutting down...", file=sys.stderr)
        self.running = False

    def _unit_signal_handler(self, signum: int, frame) -> None:
        """A unit is stopped with SIGTERM, possibly while its model still loads: before the
        serve loop runs there is nothing to drain, so it exits at once and cleanly."""
        self._signal_handler(signum, frame)
        if not self._serving:
            raise SystemExit(0)

    def start(self, daemonize: bool = False) -> None:
        """Start the search service.

        Args:
            daemonize: If True, fork to background (Unix only)
        """
        if not self.retrievers:
            print("Error: No retrievers registered", file=sys.stderr)
            sys.exit(1)

        if daemonize:
            self._daemonize()

        # Warm up all retrievers
        self._warmup_retrievers()

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Create and bind socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.server_socket.bind((self.host, self.port))
        except OSError as e:
            print(f"Failed to bind to {self.host}:{self.port}: {e}", file=sys.stderr)
            sys.exit(1)

        self.running = True
        self._serve()

    def run_as_unit(self, heartbeat=None) -> int:
        """Run in the foreground as a primal daemon unit, and return the exit code.

        Never forks: the daemon tracks the pid it spawned, and a process that daemonizes
        leaves it supervising a parent that has already exited. Liveness: *heartbeat*
        (``macf.pd.liveness.heartbeat_from_env()``, None outside a daemon) is ticked once
        before anything heavy, then about once a second while the model loads, then once
        per pass of the serve loop. The load is one blocking call, so a thread ticks for
        it, but only for ``LOAD_TICK_LIMIT_S``: a load that hangs past that stops the
        beats and the daemon sees the unit go overdue, as it would a wedged loop.

        The port is bound before the load, so a port already taken fails in seconds, not
        after the model is in memory; it listens only after the load, so a client during
        the load is refused at once instead of waiting on a backlog nobody accepts.
        """
        if not self.retrievers:
            print("Error: No retrievers registered", file=sys.stderr)
            return 1
        tick = heartbeat.tick if heartbeat is not None else (lambda: None)
        signal.signal(signal.SIGTERM, self._unit_signal_handler)
        signal.signal(signal.SIGINT, self._unit_signal_handler)
        ticker = None
        try:
            tick()
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.server_socket.bind((self.host, self.port))
            except OSError as e:
                print(f"⚠️ MACF: search service unit: cannot bind {self.host}:{self.port}: {e}. "
                      f"Another search service holds the port, most likely one started outside "
                      f"the primal daemon (search-service start --daemon). Stop it with "
                      f"'macf_tools search-service stop'; this unit is restarted by its daemon "
                      f"and takes the port once it is free.", file=sys.stderr)
                self.server_socket.close()
                self.server_socket = None
                return 1
            ticker = _LoadTicker(tick).start()
            try:
                self._warmup_retrievers()
            finally:
                ticker.stop()
            self.running = True
            self._serving = True
            self.on_pass = tick
            self._serve()
            return 0
        except SystemExit as e:
            if self.server_socket is not None and not self._serving:
                self.server_socket.close()
            return e.code if isinstance(e.code, int) else 0
        finally:
            if heartbeat is not None:
                heartbeat.stop()

    def _serve(self) -> None:
        """Listen on the bound socket and answer clients until ``running`` is cleared."""
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)  # Allow periodic signal checks

        # Write PID file
        write_pid_file(os.getpid())

        namespaces = ", ".join(self.retrievers.keys())
        print(
            f"Search service listening on {self.host}:{self.port} "
            f"[namespaces: {namespaces}]",
            file=sys.stderr
        )
        print("Press Ctrl+C to stop", file=sys.stderr)

        try:
            while self.running:
                self.on_pass()
                try:
                    client, addr = self.server_socket.accept()
                    self._handle_client(client)
                except socket.timeout:
                    continue  # Check running flag
                except OSError:
                    if self.running:
                        raise
        finally:
            self._cleanup()

    def _daemonize(self) -> None:
        """Fork to background (Unix double-fork pattern)."""
        # First fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)

        # Decouple from parent
        os.setsid()
        os.umask(0)

        # Second fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)

        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()

        with open("/dev/null", "r") as devnull:
            os.dup2(devnull.fileno(), sys.stdin.fileno())
        with open("/dev/null", "w") as devnull:
            os.dup2(devnull.fileno(), sys.stdout.fileno())

    def _cleanup(self) -> None:
        """Clean up resources on shutdown."""
        # Shutdown retrievers
        for namespace, retriever in self.retrievers.items():
            try:
                retriever.shutdown()
            except Exception as e:
                print(f"Error shutting down {namespace}: {e}", file=sys.stderr)

        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError as e:
                print(f"⚠️ MACF: failed to close server socket on shutdown: {e}", file=sys.stderr)

        remove_pid_file()
        print("Search service stopped", file=sys.stderr)


def is_service_running() -> bool:
    """Check if search service is running."""
    pid = read_pid_file()
    if pid is None:
        return False

    try:
        os.kill(pid, 0)  # Signal 0 checks existence without killing
        return True
    except ProcessLookupError:
        remove_pid_file()
        return False
    except PermissionError:
        return True  # Process exists but we can't signal it


def stop_service() -> bool:
    """Stop running search service.

    Returns True if service was stopped, False if not running.
    """
    pid = read_pid_file()
    if pid is None:
        return False

    try:
        os.kill(pid, signal.SIGTERM)
        # Wait briefly for clean shutdown
        for _ in range(10):
            time.sleep(0.1)
            if not is_service_running():
                return True
        # Force kill if still running
        os.kill(pid, signal.SIGKILL)
        remove_pid_file()
        return True
    except ProcessLookupError:
        remove_pid_file()
        return False
    except PermissionError:
        print(f"Permission denied stopping PID {pid}", file=sys.stderr)
        return False


def get_service_status() -> dict:
    """Get service status information.

    Returns dict with:
        running: bool
        pid: int or None
        port: int
    """
    pid = read_pid_file()
    running = is_service_running()
    if not running and port_answers():
        # A service whose pid file is elsewhere answers on the port all the same: a primal
        # daemon unit gets only its declared environment, so its XDG_RUNTIME_DIR, and with it
        # its pid file, may differ from this shell's.
        return {"running": True, "pid": None, "port": DEFAULT_PORT,
                "note": "answers on the port; no pid file here (a primal daemon unit? "
                        "see macf_tools pd status)"}

    return {
        "running": running,
        "pid": pid if running else None,
        "port": DEFAULT_PORT,
    }


def port_answers(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 0.5) -> bool:
    """Whether something accepts connections on the service's port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main(argv=None) -> int:
    """Main entry point for direct invocation."""
    import argparse

    parser = argparse.ArgumentParser(description="MACF Search Service Daemon")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"Host to bind to (default: {DEFAULT_HOST})")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--daemon", "-d", action="store_true",
                      help="Run in background (daemonize); not under a primal daemon")
    mode.add_argument("--unit", action="store_true",
                      help="Run in the foreground as a primal daemon unit: never forks, "
                           "reports liveness, exits on SIGTERM")

    args = parser.parse_args(argv)

    # Create service with default policy retriever
    from .retrievers.policy_retriever import PolicyRetriever

    service = SearchService(host=args.host, port=args.port)
    service.register(PolicyRetriever())
    if args.unit:
        from macf.pd.liveness import heartbeat_from_env
        return service.run_as_unit(heartbeat_from_env())
    service.start(daemonize=args.daemon)
    return 0


if __name__ == "__main__":
    sys.exit(main())
