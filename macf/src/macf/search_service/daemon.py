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
from typing import Optional

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
            except Exception:
                pass
        except Exception as e:
            print(f"Error handling client: {e}", file=sys.stderr)
            try:
                error_response = SearchResult(formatted="", error=str(e))
                client_socket.sendall(
                    (json.dumps(error_response.to_dict()) + "\n").encode()
                )
            except Exception:
                pass
        finally:
            try:
                client_socket.close()
            except Exception:
                pass

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        print(f"\nReceived signal {signum}, shutting down...", file=sys.stderr)
        self.running = False

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

        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)  # Allow periodic signal checks

        # Write PID file
        write_pid_file(os.getpid())

        self.running = True
        namespaces = ", ".join(self.retrievers.keys())
        print(
            f"Search service listening on {self.host}:{self.port} "
            f"[namespaces: {namespaces}]",
            file=sys.stderr
        )
        print("Press Ctrl+C to stop", file=sys.stderr)

        try:
            while self.running:
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
            except Exception:
                pass

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

    return {
        "running": running,
        "pid": pid if running else None,
        "port": DEFAULT_PORT,
    }


def main():
    """Main entry point for direct invocation."""
    import argparse

    parser = argparse.ArgumentParser(description="MACF Search Service Daemon")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"Host to bind to (default: {DEFAULT_HOST})")
    parser.add_argument("--daemon", "-d", action="store_true",
                        help="Run in background (daemonize)")

    args = parser.parse_args()

    # Create service with default policy retriever
    from .retrievers.policy_retriever import PolicyRetriever

    service = SearchService(host=args.host, port=args.port)
    service.register(PolicyRetriever())
    service.start(daemonize=args.daemon)


if __name__ == "__main__":
    main()
