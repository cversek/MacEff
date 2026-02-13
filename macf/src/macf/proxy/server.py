"""
Streaming API proxy for Claude Code call interception.

Sits between Claude Code and api.anthropic.com, logging request/response
metadata to JSONL while transparently forwarding all traffic including
SSE streaming responses.

Architecture:
    Claude Code -> ANTHROPIC_BASE_URL=http://localhost:8019
    macf_proxy  -> log metadata -> forward to api.anthropic.com
                <- stream SSE response back <- log response metadata
"""

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ANTHROPIC_API_URL = "https://api.anthropic.com"
DEFAULT_PORT = 8019
DEFAULT_HOST = "127.0.0.1"
PID_FILE_NAME = "macf_proxy.pid"
LOG_FILE_NAME = "agent_api_log.jsonl"


# --------------- Path helpers ---------------

def _get_runtime_dir() -> Path:
    """Runtime directory for PID file."""
    return Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))


def _get_pid_file() -> Path:
    return _get_runtime_dir() / PID_FILE_NAME


def get_log_path() -> Path:
    """Get JSONL log file path. Uses agent home if available."""
    agent_home = os.environ.get("MACEFF_AGENT_HOME_DIR", "")
    if agent_home:
        return Path(agent_home) / ".maceff" / LOG_FILE_NAME
    return _get_runtime_dir() / LOG_FILE_NAME


# --------------- PID file management ---------------

def _write_pid(pid: int) -> None:
    path = _get_pid_file()
    path.write_text(str(pid))


def _read_pid() -> Optional[int]:
    path = _get_pid_file()
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def _remove_pid() -> None:
    try:
        _get_pid_file().unlink(missing_ok=True)
    except OSError:
        pass


# --------------- JSONL logging ---------------

def _log_event(event: dict) -> None:
    """Append event to JSONL log file."""
    log_path = get_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(event) + "\n")


# --------------- SSE metadata extraction ---------------

def _parse_sse_chunk(chunk: bytes, meta: dict) -> None:
    """Extract metadata from SSE event chunk. Updates meta dict in place.

    Generic: captures ALL fields from message_start and message_delta
    events so new API fields are automatically included.
    """
    text = chunk.decode("utf-8", errors="replace")
    for line in text.split("\n"):
        if not line.startswith("data: "):
            continue
        data_str = line[6:].strip()
        if not data_str or data_str == "[DONE]":
            continue
        try:
            data = json.loads(data_str)
            event_type = data.get("type", "")

            if event_type == "message_start":
                # Dump entire message object (minus content)
                msg = data.get("message", {})
                msg.pop("content", None)
                meta.update(msg)

            elif event_type == "message_delta":
                # Merge usage updates and delta fields
                delta_usage = data.get("usage", {})
                if "usage" in meta:
                    meta["usage"].update(delta_usage)
                else:
                    meta["usage"] = delta_usage
                delta = data.get("delta", {})
                meta.update(delta)

        except json.JSONDecodeError:
            pass  # Partial JSON across chunk boundary — acceptable loss


# --------------- Request metadata extraction ---------------

def _extract_request_meta(body: bytes) -> dict:
    """Extract metadata from API request body."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"type": "api_request", "ts": int(time.time()), "parse_error": True}

    messages = data.get("messages", [])
    system = data.get("system", "")
    # system can be string or list of content blocks
    if isinstance(system, list):
        system_chars = sum(len(str(b)) for b in system)
    else:
        system_chars = len(str(system))

    meta = {
        "type": "api_request",
        "ts": int(time.time()),
        "model": data.get("model", "unknown"),
        "message_count": len(messages),
        "system_prompt_chars": system_chars,
        "tool_count": len(data.get("tools", [])),
        "stream": data.get("stream", False),
        "max_tokens": data.get("max_tokens", 0),
    }

    # Dump full request to capture dir if enabled
    capture_dir = os.environ.get("MACF_PROXY_CAPTURE_DIR")
    if capture_dir:
        cap = Path(capture_dir)
        cap.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        model = data.get("model", "unknown").replace("/", "_")
        (cap / f"{ts}_{model}_request.json").write_text(
            json.dumps(data, indent=2, default=str)
        )

    return meta


def _capture_response(data, resp_meta: dict, model: str, streaming: bool = True) -> None:
    """Capture API response to capture dir if enabled.

    For streaming: reassembles content from SSE chunks and merges with resp_meta
    (which already has usage/stop_reason from _parse_sse_chunk).
    For non-streaming: saves raw response JSON directly.
    """
    capture_dir = os.environ.get("MACF_PROXY_CAPTURE_DIR")
    if not capture_dir:
        return

    cap = Path(capture_dir)
    cap.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    model_safe = model.replace("/", "_")

    if streaming:
        # Reassemble content text from SSE chunks
        content_blocks = []
        raw = b"".join(data).decode("utf-8", errors="replace")
        for line in raw.split("\n"):
            if not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            if not data_str or data_str == "[DONE]":
                continue
            try:
                event = json.loads(data_str)
                etype = event.get("type", "")
                if etype == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        content_blocks.append(delta.get("text", ""))
                    elif delta.get("type") == "input_json_delta":
                        content_blocks.append(delta.get("partial_json", ""))
            except json.JSONDecodeError:
                pass

        # Merge ALL fields from resp_meta (usage, stop_reason, model, etc.)
        # plus reassembled content text
        captured = dict(resp_meta)  # includes stop_reason, tokens, model, message_id
        captured["content_text"] = "".join(content_blocks)
        captured["ts"] = ts

        (cap / f"{ts}_{model_safe}_response.json").write_text(
            json.dumps(captured, indent=2, default=str)
        )
    else:
        # Non-streaming: save raw response
        try:
            resp_data = json.loads(data) if isinstance(data, bytes) else data
            (cap / f"{ts}_{model_safe}_response.json").write_text(
                json.dumps(resp_data, indent=2, default=str)
            )
        except (json.JSONDecodeError, TypeError):
            (cap / f"{ts}_{model_safe}_response.raw").write_bytes(
                data if isinstance(data, bytes) else b""
            )


# --------------- aiohttp handlers ---------------

def _create_app():
    """Create aiohttp application with proxy routes."""
    from aiohttp import web, ClientSession, TCPConnector

    # Shared client session for connection reuse
    _client_session = None

    async def _get_client() -> ClientSession:
        nonlocal _client_session
        if _client_session is None or _client_session.closed:
            connector = TCPConnector(limit=10)
            _client_session = ClientSession(connector=connector)
        return _client_session

    def _forward_headers(request):
        """Extract headers to forward, stripping hop-by-hop."""
        skip = {"host", "content-length", "transfer-encoding"}
        return {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in skip
        }

    async def handle_messages(request: web.Request) -> web.StreamResponse:
        """Proxy /v1/messages with metadata logging."""
        body = await request.read()

        # Log request metadata
        req_meta = _extract_request_meta(body)
        _log_event(req_meta)

        # Rewrite stale policy injections in request body
        try:
            from .message_rewriter import (
                rewrite_messages, detect_replacement_mode, get_event_log_path,
            )
            body_json = json.loads(body)
            messages = body_json.get("messages", [])
            if messages:
                last_ts = request.app.get("last_api_call_ts", 0.0)
                event_log = get_event_log_path()
                mode = detect_replacement_mode(event_log, last_ts)
                messages, rewrite_stats = rewrite_messages(messages, mode)
                if rewrite_stats["replacements_made"] > 0:
                    body_json["messages"] = messages
                    body = json.dumps(body_json).encode("utf-8")
                    print(
                        f"[proxy] Rewrote {rewrite_stats['replacements_made']} "
                        f"policy injection(s), saved ~{rewrite_stats['bytes_saved']} bytes "
                        f"(mode={mode}, policies={rewrite_stats['policies_replaced']})",
                        file=sys.stderr,
                    )
            request.app["last_api_call_ts"] = time.time()
        except Exception as e:
            print(f"[proxy] ERROR in message rewrite (forwarding original): {e}", file=sys.stderr)

        headers = _forward_headers(request)
        target_url = f"{ANTHROPIC_API_URL}{request.path}"
        start_time = time.time()

        session = await _get_client()
        async with session.post(target_url, data=body, headers=headers) as upstream:
            is_stream = req_meta.get("stream", False)

            if is_stream:
                # Streaming SSE response
                resp = web.StreamResponse(status=upstream.status)
                # Forward response headers
                skip_resp = {"content-length", "transfer-encoding", "content-encoding"}
                for k, v in upstream.headers.items():
                    if k.lower() not in skip_resp:
                        resp.headers[k] = v
                await resp.prepare(request)

                resp_meta = {}
                sse_chunks = []  # Buffer for response capture
                async for chunk in upstream.content.iter_any():
                    await resp.write(chunk)
                    sse_chunks.append(chunk)
                    _parse_sse_chunk(chunk, resp_meta)

                await resp.write_eof()

                # Log response metadata
                resp_meta["type"] = "api_response"
                resp_meta["ts"] = int(time.time())
                resp_meta["latency_ms"] = int((time.time() - start_time) * 1000)
                _log_event(resp_meta)

                # Capture response if enabled
                _capture_response(
                    sse_chunks, resp_meta, req_meta.get("model", "unknown"),
                    streaming=True
                )

                return resp
            else:
                # Non-streaming response
                resp_body = await upstream.read()
                resp = web.Response(status=upstream.status, body=resp_body)
                skip_resp = {"content-length", "transfer-encoding", "content-encoding"}
                for k, v in upstream.headers.items():
                    if k.lower() not in skip_resp:
                        resp.headers[k] = v

                # Log full response metadata
                try:
                    resp_data = json.loads(resp_body)
                    resp_meta = resp_data.copy()
                    resp_meta["type"] = "api_response"
                    resp_meta["ts"] = int(time.time())
                    resp_meta["latency_ms"] = int((time.time() - start_time) * 1000)
                    # Remove content array to keep log manageable
                    resp_meta.pop("content", None)
                    _log_event(resp_meta)
                except (json.JSONDecodeError, Exception):
                    resp_data = None

                # Capture response if enabled
                _capture_response(
                    resp_body, resp_meta if resp_data else {},
                    req_meta.get("model", "unknown"), streaming=False
                )

                return resp

    async def handle_catchall(request: web.Request) -> web.StreamResponse:
        """Proxy any non-messages request transparently."""
        body = await request.read()
        headers = _forward_headers(request)
        target_url = f"{ANTHROPIC_API_URL}{request.path}"

        session = await _get_client()
        async with session.request(
            request.method, target_url, data=body, headers=headers
        ) as upstream:
            resp_body = await upstream.read()
            resp = web.Response(status=upstream.status, body=resp_body)
            skip_resp = {"content-length", "transfer-encoding", "content-encoding"}
            for k, v in upstream.headers.items():
                if k.lower() not in skip_resp:
                    resp.headers[k] = v
            return resp

    async def on_cleanup(app_instance):
        nonlocal _client_session
        if _client_session and not _client_session.closed:
            await _client_session.close()

    app = web.Application()
    app.router.add_post("/v1/messages", handle_messages)
    app.router.add_route("*", "/{path_info:.*}", handle_catchall)
    app.on_cleanup.append(on_cleanup)
    return app


# --------------- Daemon lifecycle ---------------

def run_proxy(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> None:
    """Run proxy server (blocking). Used by daemon child process."""
    from aiohttp import web

    app = _create_app()
    _write_pid(os.getpid())

    # Register cleanup for PID file
    def _cleanup_handler(signum, frame):
        _remove_pid()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup_handler)

    print(f"macf proxy listening on {host}:{port}", file=sys.stderr)
    print(f"Log: {get_log_path()}", file=sys.stderr)
    print(f"Activate: ANTHROPIC_BASE_URL=http://{host}:{port} claude", file=sys.stderr)

    try:
        web.run_app(app, host=host, port=port, print=None)
    finally:
        _remove_pid()


def start_proxy_daemon(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> int:
    """Start proxy as background daemon (Unix double-fork).

    Returns PID of daemon process, or -1 on error.
    """
    # First fork
    pid = os.fork()
    if pid > 0:
        # Parent waits briefly then checks PID file
        time.sleep(0.5)
        child_pid = _read_pid()
        return child_pid if child_pid else pid

    # Child: decouple
    os.setsid()
    os.umask(0)

    # Second fork
    pid = os.fork()
    if pid > 0:
        os._exit(0)

    # Grandchild: redirect file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    log_file = _get_runtime_dir() / "macf_proxy.log"
    with open("/dev/null", "r") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    log_fd = open(log_file, "a")
    os.dup2(log_fd.fileno(), sys.stdout.fileno())
    os.dup2(log_fd.fileno(), sys.stderr.fileno())

    run_proxy(port=port, host=host)
    os._exit(0)


def is_proxy_running() -> bool:
    """Check if proxy daemon is running."""
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        _remove_pid()
        return False
    except PermissionError:
        return True


def stop_proxy() -> bool:
    """Stop running proxy daemon. Returns True if stopped."""
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            time.sleep(0.1)
            if not is_proxy_running():
                return True
        os.kill(pid, signal.SIGKILL)
        _remove_pid()
        return True
    except ProcessLookupError:
        _remove_pid()
        return False
    except PermissionError:
        print(f"Permission denied stopping PID {pid}", file=sys.stderr)
        return False


def get_proxy_status() -> dict:
    """Get proxy status information."""
    running = is_proxy_running()
    result = {
        "running": running,
        "pid": _read_pid() if running else None,
        "port": DEFAULT_PORT,
        "log_path": str(get_log_path()),
        "pid_file": str(_get_pid_file()),
    }
    return result


# --------------- Analytics ---------------

def get_proxy_stats() -> dict:
    """Parse JSONL log and aggregate token/cost statistics."""
    log_path = get_log_path()
    if not log_path.exists():
        return {"error": "No log file found", "log_path": str(log_path)}

    stats = {
        "total_requests": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read": 0,
        "total_cache_creation": 0,
        "models": {},
        "avg_latency_ms": 0,
        "log_path": str(log_path),
    }
    latencies = []

    with open(log_path) as f:
        for line in f:
            try:
                event = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            if event.get("type") == "api_request":
                stats["total_requests"] += 1
                model = event.get("model", "unknown")
                stats["models"][model] = stats["models"].get(model, 0) + 1

            elif event.get("type") == "api_response":
                stats["total_input_tokens"] += event.get("input_tokens", 0)
                stats["total_output_tokens"] += event.get("output_tokens", 0)
                stats["total_cache_read"] += event.get(
                    "cache_read_input_tokens", 0
                )
                stats["total_cache_creation"] += event.get(
                    "cache_creation_input_tokens", 0
                )
                if "latency_ms" in event:
                    latencies.append(event["latency_ms"])

    if latencies:
        stats["avg_latency_ms"] = sum(latencies) // len(latencies)

    # Rough cost estimate (Claude Opus 4 pricing)
    # Input: $15/MTok, Output: $75/MTok, Cache read: $1.875/MTok
    stats["estimated_cost_usd"] = round(
        stats["total_input_tokens"] * 15 / 1_000_000
        + stats["total_output_tokens"] * 75 / 1_000_000
        + stats["total_cache_read"] * 1.875 / 1_000_000,
        4,
    )

    return stats


def get_recent_log(limit: int = 10) -> list:
    """Get the N most recent log events."""
    log_path = get_log_path()
    if not log_path.exists():
        return []

    events = []
    with open(log_path) as f:
        for line in f:
            try:
                events.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue

    return events[-limit:]


# --------------- Direct invocation ---------------

def main():
    """Entry point for python -m macf.proxy."""
    import argparse

    parser = argparse.ArgumentParser(description="MACF API Proxy")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help=f"Host (default: {DEFAULT_HOST})"
    )
    args = parser.parse_args()
    run_proxy(port=args.port, host=args.host)


if __name__ == "__main__":
    main()
