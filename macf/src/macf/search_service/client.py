"""
Lightweight search service client - STDLIB ONLY.

This module has ZERO heavy imports - safe for hook subprocess use.
Uses socket + json only (both in stdlib).

Architecture:
- Hooks use get_policy_injection() for formatted recommendations
- Direct queries use query_search_service() for full results
- Graceful degradation: returns empty result if service unavailable

Protocol (newline-delimited JSON over TCP):
    Request:  {"namespace": "policy", "query": "...", "limit": 5}
    Response: {"formatted": "...", "explanations": [...], "search_time_ms": 45.2}
"""

import json
import socket
from typing import Any, Optional

DEFAULT_PORT = 9001
DEFAULT_HOST = "127.0.0.1"
DEFAULT_TIMEOUT = 0.5  # 500ms


def query_search_service(
    namespace: str,
    query: str,
    port: int = DEFAULT_PORT,
    host: str = DEFAULT_HOST,
    timeout_s: float = DEFAULT_TIMEOUT,
    limit: int = 5,
) -> dict[str, Any]:
    """Query the search service via TCP socket.

    Returns dict with 'formatted' key on success, error dict on failure.
    Graceful degradation: returns empty formatted string if service unavailable.

    Args:
        namespace: Retriever namespace (e.g., "policy")
        query: Search query string
        port: Service port (default: 9001)
        host: Service host (default: 127.0.0.1)
        timeout_s: Socket timeout in seconds (default: 0.5)
        limit: Maximum results to return (default: 5)

    Returns:
        dict with keys:
            formatted: str (human-readable output)
            explanations: list[dict] (detailed breakdown)
            search_time_ms: float (timing)
            error: str (if failed)

    Example:
        >>> result = query_search_service("policy", "How do I backup TODOs?")
        >>> print(result["formatted"])
    """
    # Build request
    request = {
        "namespace": namespace,
        "query": query,
        "limit": limit,
    }

    try:
        # Create socket with timeout
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_s)

        # Connect to service
        sock.connect((host, port))

        # Send request (newline-delimited JSON)
        request_json = json.dumps(request) + "\n"
        sock.sendall(request_json.encode("utf-8"))

        # Receive response
        response_data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_data += chunk
            if b"\n" in response_data:
                break

        sock.close()

        # Parse response
        response_text = response_data.decode("utf-8").split("\n")[0]
        response = json.loads(response_text)

        return response

    except socket.timeout:
        return {
            "formatted": "",
            "explanations": [],
            "search_time_ms": 0.0,
            "error": "timeout",
        }

    except ConnectionRefusedError:
        return {
            "formatted": "",
            "explanations": [],
            "search_time_ms": 0.0,
            "error": "connection_refused",
        }

    except Exception as e:
        return {
            "formatted": "",
            "explanations": [],
            "search_time_ms": 0.0,
            "error": f"client_error: {e}",
        }


def get_policy_injection(
    prompt: str,
    timeout_s: float = DEFAULT_TIMEOUT,
    port: int = DEFAULT_PORT,
) -> str:
    """Get policy injection for hook use.

    Convenience wrapper that queries 'policy' namespace and returns formatted string.
    Returns empty string if service unavailable or query too short.

    This is the primary function used by hooks (e.g., UserPromptSubmit).

    Args:
        prompt: User prompt text
        timeout_s: Socket timeout in seconds (default: 0.5)
        port: Service port (default: 9001)

    Returns:
        Formatted policy recommendation string (empty if unavailable)

    Example:
        >>> injection = get_policy_injection("I need to backup my TODOs")
        >>> if injection:
        ...     print(injection)
    """
    # Skip very short prompts
    if len(prompt) < 10:
        return ""

    result = query_search_service(
        namespace="policy",
        query=prompt,
        timeout_s=timeout_s,
        port=port,
    )

    return result.get("formatted", "")
