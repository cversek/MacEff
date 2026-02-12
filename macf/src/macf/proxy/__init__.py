"""
macf.proxy - Streaming API proxy for Claude Code call interception.

Intercepts Claude Code API calls via ANTHROPIC_BASE_URL, logs request/response
metadata to JSONL, and provides CLI commands for daemon management and analytics.

Usage:
    macf_tools proxy start [--daemon] [--port PORT]
    macf_tools proxy stop
    macf_tools proxy status
    macf_tools proxy stats
    macf_tools proxy log [--limit N]

Activation:
    ANTHROPIC_BASE_URL=http://localhost:8019 claude
"""

from .server import (
    is_proxy_running,
    stop_proxy,
    get_proxy_status,
    get_proxy_stats,
    get_recent_log,
    get_log_path,
    DEFAULT_PORT,
)

__all__ = [
    "is_proxy_running",
    "stop_proxy",
    "get_proxy_status",
    "get_proxy_stats",
    "get_recent_log",
    "get_log_path",
    "DEFAULT_PORT",
]
