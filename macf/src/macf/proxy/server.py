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
import logging
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

# aiohttp's web.Application defaults to client_max_size=1 MiB and rejects larger
# bodies with 413 *before* any handler runs (so nothing is logged). Conversation
# requests routinely exceed 1 MiB, and Claude Code renders any 413 as
# "Request too large (max 32MB)" — a hardcoded label unrelated to the real limit.
# Its recovery then strips images/documents; with none present the retry is
# byte-identical, so the session wedges permanently (even /compact fails, since
# the compaction request takes the same path). Cap generously instead: a
# pass-through proxy must not impose a limit stricter than upstream's.
MAX_REQUEST_BYTES = int(os.environ.get("MACF_PROXY_MAX_REQUEST_BYTES", 256 * 1024 * 1024))


# --------------- Feature gates ---------------

def _rewrite_enabled() -> bool:
    """Whether in-flight message rewriting is enabled. Default: OFF.

    Rewriting (policy-injection retraction/dedup) mutates the message-array
    prefix, which can invalidate Anthropic prompt-cache prefix stability —
    cache misses inflate token burn and can force premature compaction.
    It is therefore EXPERIMENTAL and opt-in: set MACF_PROXY_REWRITE=on
    (accepted truthy values: on/1/true/yes) to enable for scratch-session
    experiments. Detection and stderr reporting remain active either way —
    the gate covers only the mutation.

    Single source of truth: both the startup banner and the request path MUST
    call this. The banner once read the env var while the rewrite path ignored
    it entirely, so the proxy advertised rewrite=off while rewriting every
    request — an instrument reporting a value nobody enforces is worse than no
    instrument at all.
    """
    return os.environ.get("MACF_PROXY_REWRITE", "off").strip().lower() in ("on", "1", "true", "yes")


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
    # Single choke point for response metadata, so the clamp detector hangs here
    # rather than being duplicated across the streaming and non-streaming paths.
    # The guard also terminates the one-level recursion: the detector's own event
    # is not an "api_response", so it cannot re-enter.
    if event.get("type") == "api_response":
        _warn_if_approaching_clamp(event.get("usage") or {})


# --------------- Failure-path observability ---------------
#
# Every instrument in this proxy used to sit *after* `await request.read()` in
# the handler — which is precisely the call that fails when a request exceeds
# client_max_size. Rejected requests therefore produced no log line at all, and
# that silence was repeatedly misread as "the request never reached the proxy".
# An empty log is only evidence of absence if the log is known to cover the
# failure mode. These three additions make it cover them.


def _log_error_event(request, status: int, kind: str, detail: str) -> None:
    """Record a failed request in the SAME log readers already watch.

    Idempotent per request: a handler may log a precise diagnosis before the
    middleware sees the same exception, and one failure should be one record.
    """
    try:
        if request.get("_macf_error_logged"):
            return
        request["_macf_error_logged"] = True
    except (AttributeError, TypeError):
        pass  # not a mutable request mapping — log anyway

    _log_event({
        "type": "api_error",
        "ts": int(time.time()),
        "status": status,
        "kind": kind,
        "detail": detail[:500],
        "method": getattr(request, "method", "?"),
        "path": str(getattr(request, "path", "?")),
        "content_length": getattr(request, "content_length", None),
        "client_max_size": MAX_REQUEST_BYTES,
    })
    print(f"[proxy:error] {status} {kind}: {detail[:200]}", file=sys.stderr)


def _make_error_middleware():
    """Middleware logging every failed request, including framework rejections.

    aiohttp enforces client_max_size inside request.read(), raising
    HTTPRequestEntityTooLarge. Without this, that exception becomes a bare 413
    on the wire with zero telemetry.
    """
    from aiohttp import web

    @web.middleware
    async def error_middleware(request, handler):
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            kind = ("request_too_large_REJECTED_BY_THIS_PROXY"
                    if exc.status == 413 else "http_exception")
            _log_error_event(request, exc.status, kind, str(exc.reason or exc))
            raise
        except Exception as exc:
            _log_error_event(request, 500, type(exc).__name__, str(exc))
            raise
        if response.status >= 400:
            # Capture the upstream error BODY, not just the status. A 429 whose
            # message says "…required for long context" makes the client clamp
            # its context window 1M -> 200K for the rest of the process, after
            # which it refuses to send at ~180K while still displaying 1M. The
            # status alone cannot distinguish that from an ordinary rate limit,
            # and we lost days to exactly that ambiguity. Streaming responses
            # expose no .body; record what is available and say which it was.
            detail = ""
            body = getattr(response, "body", None)
            if isinstance(body, (bytes, bytearray)):
                detail = bytes(body)[:2048].decode("utf-8", "replace")
            elif body is not None:
                detail = f"<unreadable body type {type(body).__name__}>"
            else:
                detail = "<streaming response; body not buffered>"
            _log_error_event(request, response.status, "upstream_error_status", detail)
        return response

    return error_middleware


# --------------- 200K-window clamp detector ---------------
#
# This proxy's own existence downgrades the client's context window, silently.
#
# Observed behaviour: when ANTHROPIC_BASE_URL points at a host that is not
# api.anthropic.com, the client stops extending the 1M long-context window and
# falls back to 200K -- so it auto-compacts around 167K while every UI surface
# still reports 1M. Nothing is logged, warned, or errored on the client side;
# the only symptom is compacting early. That is what made it cost months.
#
# Established by A/B, not by assumption: same conversation, proxy ON compacted
# at 166,403 and again at 167,108 (a 700-token spread); proxy OFF ran past 180K
# with no compaction at all. The undocumented env var below restores the window
# with the proxy in place. Its name is the clue to the rule -- the client wants
# to know the endpoint is first-party, and decides that from the base URL host.
#
# The proxy cannot read the client's env, so it cannot check the flag directly.
# What it CAN see is every request's true input size. So it says the actionable
# thing at the moment the evidence first exists, rather than leaving a silence to
# be misread later. Warn once per process; this is a config fault, not an event.

CLAMPED_WINDOW = 200_000
# Warn below the ~167K compaction point so the message lands BEFORE the symptom.
WINDOW_WARN_AT = 150_000
_window_warned = False

# The client rejects oversized requests with "Request too large (max 32MB)" —
# a hardcoded client-side label, so 32MB is the wall we are measured against,
# not a limit this proxy imposes. Warn at a fraction of it while the session is
# still alive to act (compact, clear a runaway tool_result). Override the ratio
# with MACF_PROXY_SIZE_WARN_RATIO; 0 disables the warning.
CLIENT_REQUEST_WALL_BYTES = 32 * 1024 * 1024
_request_size_warned = False


def _request_warn_at() -> int:
    """Byte threshold for the growth warning (0 = disabled)."""
    try:
        ratio = float(os.environ.get("MACF_PROXY_SIZE_WARN_RATIO", "0.6"))
    except ValueError:
        ratio = 0.6
    if ratio <= 0:
        return 0
    return int(CLIENT_REQUEST_WALL_BYTES * ratio)


def _warn_if_request_growing(request_bytes: int) -> None:
    """Make the request-size cliff visible before it is fatal.

    Hitting the wall is unrecoverable in practice: the client refuses to
    serialize, `/compact` fails on the same wall because the compaction request
    takes the same path, and `/clear` — total context loss — is the only exit.
    One warning per process, on the way up, is the whole point.
    """
    global _request_size_warned
    threshold = _request_warn_at()
    if _request_size_warned or not threshold or request_bytes < threshold:
        return
    _request_size_warned = True
    pct = round(100 * request_bytes / CLIENT_REQUEST_WALL_BYTES)
    _log_event({
        "type": "request_size_watch", "ts": int(time.time()),
        "request_bytes": request_bytes,
        "wall_bytes": CLIENT_REQUEST_WALL_BYTES,
        "pct_of_wall": pct,
    })
    print(
        f"[proxy:size] ⚠️  request reached {request_bytes / 1_048_576:.1f} MB "
        f"({pct}% of the client's ~32MB wall).\n"
        f"  At the wall the client refuses to serialize, and /compact fails the same\n"
        f"  way (it takes this path too) — /clear becomes the only exit, losing the\n"
        f"  whole context. Compact NOW while it still works.\n"
        f"  See per-block bytes in this request's api_request log entry to find what grew.",
        file=sys.stderr,
    )


def _warn_if_approaching_clamp(usage: dict) -> None:
    """Say the actionable thing while the session is still alive to act on it."""
    global _window_warned
    if _window_warned or not isinstance(usage, dict):
        return
    total = (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
    )
    if total < WINDOW_WARN_AT:
        return
    _window_warned = True
    _log_event({
        "type": "window_clamp_watch", "ts": int(time.time()),
        "input_tokens": total, "clamped_window": CLAMPED_WINDOW,
        "remedy_env": "_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL",
    })
    print(
        f"[proxy:window] ⚠️  context reached {total:,} tokens.\n"
        f"  If this session compacts before ~{CLAMPED_WINDOW:,}, the client is on the\n"
        f"  200K fallback window, NOT the 1M it displays. Routing through this proxy\n"
        f"  makes ANTHROPIC_BASE_URL's host != api.anthropic.com, and the client then\n"
        f"  withholds the 1M long-context window.\n"
        f"  Remedy: set _CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1 in the client's env\n"
        f"  (accurate here -- this proxy forwards to {ANTHROPIC_API_URL} unmodified).\n"
        f"  Verify with the ACTUAL compaction point, never a status line/banner.",
        file=sys.stderr,
    )


def _log_effective_config(port: int, host: str) -> None:
    """Log the limits actually in force. Silent defaults are invisible policy."""
    cfg = {
        "type": "proxy_start",
        "ts": int(time.time()),
        "pid": os.getpid(),
        "host": host,
        "port": port,
        "upstream": ANTHROPIC_API_URL,
        "client_max_size": MAX_REQUEST_BYTES,
        "rewrite_enabled": _rewrite_enabled(),
        "capture_dir": os.environ.get("MACF_PROXY_CAPTURE_DIR") or None,
    }
    _log_event(cfg)
    print(
        f"[proxy:start] pid={cfg['pid']} {host}:{port} -> {ANTHROPIC_API_URL} | "
        f"client_max_size={MAX_REQUEST_BYTES:,}B | rewrite={cfg['rewrite_enabled']} | "
        f"capture={cfg['capture_dir'] or 'off'}",
        file=sys.stderr,
    )
    # Stated at every start because it is a precondition of correct operation,
    # not an incident: any client pointed here MUST also set this, or it silently
    # runs on the 200K fallback window while displaying 1M.
    print(
        "[proxy:start] clients routed here MUST set "
        "_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1, else their context window "
        f"silently falls back to {CLAMPED_WINDOW:,} (compacts ~167K, still displays 1M).",
        file=sys.stderr,
    )


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


# --------------- Bounded, guarded capture ---------------
#
# Capture was shipped as an unbounded dump: one full request + one full response
# per call, never evicted. Measured at 117 MB / 427 files after a single session
# (up from 73 MB within that same session). It was also UNGUARDED -- the write
# sat outside the handler's try block, so a full disk would have taken the proxy
# down with a 500 rather than degrading to "no capture". A diagnostic that can
# kill the thing it observes is a liability, and an unbounded one eventually
# fills the disk it shares with everything else.
#
# Both properties are fixed here: writes never raise, and total capture size is
# capped with oldest-first eviction (a ring buffer by bytes rather than count,
# since request sizes vary by orders of magnitude).

CAPTURE_MAX_MB = 512
_capture_writes = 0
# Eviction scans the directory, so amortise it rather than paying per write.
_CAPTURE_EVICT_EVERY = 20


def _capture_cap_bytes() -> int:
    """Cap in bytes. MACF_PROXY_CAPTURE_MAX_MB=0 disables the bound entirely."""
    raw = os.environ.get("MACF_PROXY_CAPTURE_MAX_MB")
    try:
        mb = int(raw) if raw is not None and raw.strip() != "" else CAPTURE_MAX_MB
    except ValueError:
        mb = CAPTURE_MAX_MB
    return max(0, mb) * 1024 * 1024


def _capture_evict(cap: Path) -> None:
    """Drop oldest captures until under the cap. Never raises."""
    limit = _capture_cap_bytes()
    if limit <= 0:
        return
    try:
        files = []
        for f in cap.glob("*.json"):
            try:
                files.append((f.stat().st_mtime, f.stat().st_size, f))
            except OSError:
                continue
        total = sum(s for _, s, _ in files)
        if total <= limit:
            return
        files.sort(key=lambda x: x[0])  # oldest first
        freed = removed = 0
        for _, size, f in files:
            if total - freed <= limit:
                break
            try:
                f.unlink()
            except OSError:
                continue
            freed += size
            removed += 1
        if removed:
            print(
                f"[proxy:capture] evicted {removed} file(s), freed "
                f"{freed/1024/1024:.1f} MB (cap {limit/1024/1024:.0f} MB)",
                file=sys.stderr,
            )
    except OSError as e:
        print(f"[proxy:capture] eviction skipped: {e}", file=sys.stderr)


def _capture_write(cap: Path, filename: str, payload) -> bool:
    """Write one capture file (str or bytes). False on failure, never raises.

    Capture is a diagnostic; losing it must never fail the request it is
    observing. Callers log their own success line only if this returns True.
    """
    global _capture_writes
    try:
        cap.mkdir(parents=True, exist_ok=True)
        target = cap / filename
        if isinstance(payload, (bytes, bytearray)):
            target.write_bytes(bytes(payload))
        else:
            target.write_text(payload)
    except OSError as e:
        print(
            f"[proxy:capture] write FAILED, continuing without capture: {e}",
            file=sys.stderr,
        )
        return False
    _capture_writes += 1
    if _capture_writes % _CAPTURE_EVICT_EVERY == 0:
        _capture_evict(cap)
    return True


# --------------- Request metadata extraction ---------------

def _block_byte_census(messages: list) -> dict:
    """Bytes per content-block type across all messages.

    Metadata like `message_count` says how *many* blocks there are, never how
    heavy they are — so when a session walks into the request-size wall, the log
    cannot say what grew. A census names the culprit directly (a tool_result
    that ballooned, images accumulating, system-reminders piling up) instead of
    leaving it to transcript inference after the fact.
    """
    census: dict = {}
    for msg in messages or []:
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str):
            census["text"] = census.get("text", 0) + len(content)
            continue
        for block in content or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "unknown")
            # Serialized size of the block itself: images live in nested
            # source.data, tool_results in nested content, so a top-level
            # len() would undercount exactly the blocks that matter most.
            try:
                size = len(json.dumps(block))
            except (TypeError, ValueError):
                size = len(str(block))
            census[btype] = census.get(btype, 0) + size
    return census


def _extract_request_meta(body: bytes) -> dict:
    """Extract metadata from API request body."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        # Even unparseable bodies get their size recorded: a body too large or
        # malformed to parse is precisely the case worth seeing in the log.
        return {"type": "api_request", "ts": int(time.time()),
                "parse_error": True, "request_bytes": len(body)}

    messages = data.get("messages", [])
    system = data.get("system", "")
    # system can be string or list of content blocks
    if isinstance(system, list):
        system_chars = sum(len(str(b)) for b in system)
    else:
        system_chars = len(str(system))

    request_bytes = len(body)
    meta = {
        "type": "api_request",
        "ts": int(time.time()),
        "model": data.get("model", "unknown"),
        "message_count": len(messages),
        "system_prompt_chars": system_chars,
        "tool_count": len(data.get("tools", [])),
        "stream": data.get("stream", False),
        "max_tokens": data.get("max_tokens", 0),
        # Tier-1 flight-recorder telemetry: the serialized size and what it is
        # made of. The trend across a session predicts the request-size cliff
        # many turns before it becomes fatal.
        "request_bytes": request_bytes,
        "block_bytes": _block_byte_census(messages),
    }

    _warn_if_request_growing(request_bytes)

    # Dump full request to capture dir if enabled
    capture_dir = os.environ.get("MACF_PROXY_CAPTURE_DIR")
    if capture_dir:
        # Bounded + guarded: this call sits OUTSIDE the handler's try block, so
        # an unguarded write here fails the request itself. See _capture_write.
        cap = Path(capture_dir)
        ts = int(time.time())
        model = data.get("model", "unknown").replace("/", "_")
        filename = f"{ts}_{model}_request.json"
        if _capture_write(cap, filename, json.dumps(data, indent=2, default=str)):
            # VERBOSE: Echo captured filename
            print(f"[proxy:capture] → {filename}", file=sys.stderr)

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
    # mkdir happens inside _capture_write, guarded — an unguarded mkdir here
    # would raise on a read-only or full filesystem before any write is tried.
    ts = int(time.time())
    model_safe = model.replace("/", "_")

    if streaming:
        # Reassemble content from SSE chunks — track blocks by type
        current_block_type = None
        current_block_parts = []
        content_blocks = []  # list of {type, text/thinking/json}
        text_parts = []  # flat text for backward compat

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

                if etype == "content_block_start":
                    block = event.get("content_block", {})
                    current_block_type = block.get("type", "unknown")
                    current_block_parts = []

                elif etype == "content_block_delta":
                    delta = event.get("delta", {})
                    dtype = delta.get("type", "")
                    if dtype == "text_delta":
                        chunk = delta.get("text", "")
                        current_block_parts.append(chunk)
                        text_parts.append(chunk)
                    elif dtype == "thinking_delta":
                        current_block_parts.append(delta.get("thinking", ""))
                    elif dtype == "input_json_delta":
                        chunk = delta.get("partial_json", "")
                        current_block_parts.append(chunk)
                        text_parts.append(chunk)

                elif etype == "content_block_stop":
                    assembled = "".join(current_block_parts)
                    if current_block_type and assembled:
                        content_blocks.append({
                            "type": current_block_type,
                            "content": assembled,
                        })
                    current_block_type = None
                    current_block_parts = []

            except json.JSONDecodeError:
                pass

        # Merge ALL fields from resp_meta (usage, stop_reason, model, etc.)
        # plus reassembled content
        captured = dict(resp_meta)  # includes stop_reason, tokens, model, message_id
        captured["content_text"] = "".join(text_parts)  # backward compat
        captured["content_blocks"] = content_blocks  # structured blocks
        captured["ts"] = ts

        filename = f"{ts}_{model_safe}_response.json"
        if _capture_write(cap, filename, json.dumps(captured, indent=2, default=str)):
            # VERBOSE: Echo captured filename
            print(f"[proxy:capture] ← {filename}", file=sys.stderr)
    else:
        # Non-streaming: save raw response
        # The except clause below covers only parse failures; an OSError from the
        # write would previously have escaped and failed the request. Both writes
        # now go through _capture_write, which swallows OSError by contract.
        try:
            resp_data = json.loads(data) if isinstance(data, bytes) else data
            filename = f"{ts}_{model_safe}_response.json"
            payload = json.dumps(resp_data, indent=2, default=str)
        except (json.JSONDecodeError, TypeError):
            filename = f"{ts}_{model_safe}_response.raw"
            payload = data if isinstance(data, bytes) else b""
        if _capture_write(cap, filename, payload):
            print(f"[proxy:capture] ← {filename}", file=sys.stderr)


# --------------- Policy injection state tracking ---------------

def _detect_current_injections(messages: list) -> dict:
    """
    Scan request messages for policy injection content.
    Returns dict of {policy_name: {"bytes": int, "msg_idx": int}} for full
    injection blocks found. Only scans user-role messages to avoid false
    positives from assistant messages that quote/discuss the tag format.
    """
    import re

    FULL_BLOCK_PATTERN = re.compile(
        r'(<macf-policy-nav-guide-injection\s+policy="([^"]+)">.*?</macf-policy-nav-guide-injection>)',
        re.DOTALL
    )

    found = {}
    for i, msg in enumerate(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        texts = []
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
        for text in texts:
            for match in FULL_BLOCK_PATTERN.finditer(text):
                name = match.group(2)
                # Skip template strings from source code (e.g., "{policy_name}")
                if "{" not in name and "}" not in name:
                    block_bytes = len(match.group(1).encode('utf-8'))
                    if name in found:
                        found[name]["bytes"] += block_bytes
                    else:
                        found[name] = {"bytes": block_bytes, "msg_idx": i}
    return found


# --------------- aiohttp handlers ---------------

def _create_app():
    """Create aiohttp application with proxy routes."""
    from aiohttp import web, ClientSession, TCPConnector
    from aiohttp.client_exceptions import ClientConnectionResetError

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
        # Guarded explicitly: this is the call that raises when a request
        # exceeds client_max_size, and it is the FIRST statement in the handler
        # — so an unguarded failure here skips every instrument below it.
        try:
            body = await request.read()
        except web.HTTPRequestEntityTooLarge as exc:
            _log_error_event(
                request, 413, "request_too_large_REJECTED_BY_THIS_PROXY",
                f"body exceeds client_max_size={MAX_REQUEST_BYTES}: {exc}",
            )
            raise

        # Log request metadata
        req_meta = _extract_request_meta(body)
        _log_event(req_meta)

        # Detect policy injections, rewrite if needed, report
        try:
            body_json = json.loads(body)
            messages = body_json.get("messages", [])

            # Skip hook sub-calls: only process main conversation requests.
            # Hook sub-calls don't carry policy injections. The
            # `context_management` key distinguishes main requests.
            is_main_conversation = "context_management" in body_json

            if messages and is_main_conversation:
                n_messages = len(messages)
                ts = int(time.time())

                # 1. Detect injections BEFORE rewrite
                pre_injections = _detect_current_injections(messages)

                # 2. Run stateless rewrite (retract inactive + dedup active),
                #    but ONLY when the gate the banner advertises is actually on.
                # EXPERIMENTAL — gated OFF by default: mutating the message-array
                # prefix can invalidate Anthropic prompt-cache prefix stability,
                # causing cache misses, inflated token burn, and premature forced
                # compaction. Pass-through (observe + report, never mutate) is the
                # safe default; enable mutation explicitly with MACF_PROXY_REWRITE=on
                # for scratch-session experiments only.
                rewrite_stats = None
                if _rewrite_enabled():
                    try:
                        from .message_rewriter import rewrite_messages
                        messages, rewrite_stats = rewrite_messages(messages)
                        if rewrite_stats["replacements_made"] > 0:
                            body_json["messages"] = messages
                            body = json.dumps(body_json).encode("utf-8")
                    except Exception as e:
                        print(f"[proxy:rewrite] ERROR (forwarding original): {e}", file=sys.stderr)

                # 3. Detect injections AFTER rewrite
                post_injections = _detect_current_injections(messages) if rewrite_stats and rewrite_stats["replacements_made"] > 0 else pre_injections

                # 4. Report
                if pre_injections:
                    request_bytes = len(body)
                    request_ktok = round(request_bytes / 4 / 1000)
                    policy_bytes = sum(info["bytes"] for info in pre_injections.values())
                    policy_ktok = round(policy_bytes / 4 / 1000)
                    print(
                        f"[proxy:injection] 📋 {len(pre_injections)} "
                        f"policy injection(s) in request ({n_messages} messages):",
                        file=sys.stderr
                    )
                    for name in sorted(pre_injections):
                        info = pre_injections[name]
                        idx = info["msg_idx"]
                        kb = round(info["bytes"] / 1000, 1)
                        ktok = round(info["bytes"] / 4 / 1000)
                        suffix = ""
                        if name not in post_injections:
                            suffix = f" [retracted_at={idx}]"
                        elif post_injections[name]["msg_idx"] != idx:
                            suffix = f" [replaced_at={post_injections[name]['msg_idx']}]"
                        print(
                            f"  {idx:3d}: {name} ~{ktok}k ({kb} kb){suffix}",
                            file=sys.stderr
                        )
                    print(
                        f"  ─── Policy Injection: ~{policy_ktok}k ({round(policy_bytes / 1000, 1)} kb)",
                        file=sys.stderr
                    )
                    print(
                        f"  ─── Request Total: ~{request_ktok}k ({round(request_bytes / 1000, 1)} kb)",
                        file=sys.stderr
                    )
                    if rewrite_stats and rewrite_stats["replacements_made"] > 0:
                        saved_ktok = round(rewrite_stats["bytes_saved"] / 4 / 1000)
                        parts = []
                        if rewrite_stats["retracted"]:
                            parts.append(f"retracted: {', '.join(rewrite_stats['retracted'])}")
                        if rewrite_stats["deduplicated"]:
                            parts.append(f"deduped: {', '.join(rewrite_stats['deduplicated'])}")
                        print(
                            f"  ─── Rewrite: {rewrite_stats['replacements_made']} replacement(s), "
                            f"~{saved_ktok}k saved | {' | '.join(parts)}",
                            file=sys.stderr
                        )
        except Exception as e:
            print(f"[proxy:injection] ERROR: {e}", file=sys.stderr)

        headers = _forward_headers(request)
        # path_qs, NOT path: the client sends /v1/messages?beta=true, and dropping
        # that query string changes what upstream grants. A rejected/limited beta
        # request can come back 429, which the client treats as a permanent
        # entitlement clamp for the life of the process. (Diagnosed 2026-07-29.)
        target_url = f"{ANTHROPIC_API_URL}{request.path_qs}"
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
                client_disconnected = False
                async for chunk in upstream.content.iter_any():
                    if not client_disconnected:
                        try:
                            await resp.write(chunk)
                        except (ConnectionResetError, ConnectionError,
                                ClientConnectionResetError):
                            client_disconnected = True
                            print(
                                f"[proxy] Client disconnected during stream "
                                f"(model={req_meta.get('model', '?')}), "
                                f"continuing capture",
                                file=sys.stderr
                            )
                    sse_chunks.append(chunk)
                    _parse_sse_chunk(chunk, resp_meta)

                if not client_disconnected:
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
        target_url = f"{ANTHROPIC_API_URL}{request.path_qs}"  # see handle_messages

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

    app = web.Application(
        client_max_size=MAX_REQUEST_BYTES,
        middlewares=[_make_error_middleware()],
    )
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

    print(f"[proxy] listening on {host}:{port}", file=sys.stderr)
    print(f"[proxy] Log: {get_log_path()}", file=sys.stderr)
    print(f"[proxy] Activate: ANTHROPIC_BASE_URL=http://{host}:{port} claude", file=sys.stderr)

    # aiohttp's access logger is enabled by default but emits at INFO, and
    # nothing here ever configured logging — so every access record, including
    # the 413s this proxy was issuing, was discarded before reaching the
    # journal. Default-on instrumentation that is never wired up is worse than
    # none: it looks like coverage. Wire it to stderr, which systemd captures.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    _log_effective_config(port, host)

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


def _socket_owner_pid(port: int) -> Optional[int]:
    """PID actually listening on `port`, or None if that can't be determined.

    The pidfile records who *we* started; this reports who actually holds the
    socket. They diverge in the split-brain case (an ad-hoc daemon keeps
    answering while a systemd unit crash-loops on EADDRINUSE), which is exactly
    when the pidfile alone is misleading.
    """
    import re
    import shutil
    import subprocess as _sp

    if shutil.which("ss"):
        cmd = ["ss", "-tlnp"]
    elif shutil.which("lsof"):
        cmd = ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"]
    else:
        return None

    try:
        out = _sp.run(cmd, capture_output=True, text=True, timeout=5)
    except (OSError, _sp.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None

    for line in out.stdout.splitlines():
        if f":{port}" not in line:
            continue
        # ss:   users:(("python3",pid=1234,fd=7))
        m = re.search(r'pid=(\d+)', line)
        if m:
            return int(m.group(1))
        # lsof: python3 1234 user ...
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
    return None


def get_proxy_status() -> dict:
    """Get proxy status information.

    Includes a socket-owner cross-check: "it answers on the port" is not the
    same as "the process we think is running owns the port".
    """
    running = is_proxy_running()
    pid = _read_pid() if running else None
    owner = _socket_owner_pid(DEFAULT_PORT)
    result = {
        "running": running,
        "pid": pid,
        "port": DEFAULT_PORT,
        "socket_owner_pid": owner,
        # True when something else holds the socket — the split-brain signature.
        "socket_owner_mismatch": bool(owner and pid and owner != pid),
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
