"""
macf.search_service - Persistent daemon for warm policy search

This module provides a socket-based service that keeps the sentence-transformers
model warm, enabling 89x faster policy recommendations (45ms vs 4000ms).

Architecture:
- Daemon loads heavy dependencies ONCE at startup
- Clients query via lightweight socket protocol (stdlib only)
- Graceful degradation when service unavailable

Usage:
    # Start service (CLI)
    macf_tools search-service start

    # Query from hook (stdlib only)
    from macf.search_service import get_policy_injection
    injection = get_policy_injection(user_prompt)

Source: EXPERIMENT 003_MCP_Warm_Cache_Hook_Optimization
Validated: 89x speedup (s_77270981/c_349/g_a76f3cd/p_7dd7f580/t_1768798157)
"""

from .daemon import (
    SearchService,
    DEFAULT_PORT,
    is_service_running,
    stop_service,
    get_service_status,
)
from .client import query_search_service, get_policy_injection
from .retrievers import AbstractRetriever, SearchResult
from .retrievers.policy_retriever import PolicyRetriever

__all__ = [
    "SearchService",
    "DEFAULT_PORT",
    "is_service_running",
    "stop_service",
    "get_service_status",
    "query_search_service",
    "get_policy_injection",
    "AbstractRetriever",
    "SearchResult",
    "PolicyRetriever",
]
