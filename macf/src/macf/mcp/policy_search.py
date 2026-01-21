#!/usr/bin/env python3
"""
mcp_policy_search.py - MCP server for hybrid policy search

Phase 4 (MISSION): Expose RRF hybrid search as MCP tools following
the three-layer progressive disclosure pattern from claude-mem.

Tools:
  - search: Query policies with optional explanations
  - context: Get CEP navigation context for a policy
  - details: Get full policy content
  - explain: Get detailed explanation of why a policy matched

Usage:
    # Register in Claude Code MCP settings
    python -m macf.mcp.policy_search

Target: Token-efficient progressive disclosure

Breadcrumb: s_77270981/c_356/g_a76f3cd/p_4593c146/t_1768952820
"""

import json
import sys
from pathlib import Path
from typing import Any, Optional

# Graceful fallback if recommend module unavailable
try:
    from macf.utils.recommend import get_recommendations
    RECOMMEND_AVAILABLE = True
except ImportError:
    RECOMMEND_AVAILABLE = False
    get_recommendations = None

# LanceDB search backend
try:
    from macf.hybrid_search.lancedb_search import LanceDBPolicySearch
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False
    LanceDBPolicySearch = None

from macf.utils.paths import find_agent_home


def get_db_path() -> Path:
    """Get policy index path using portable resolution."""
    return find_agent_home() / ".maceff" / "policy_index.lance"


# Configuration
DB_PATH = get_db_path()
_searcher: Optional[Any] = None  # LanceDBPolicySearch instance


def get_searcher():
    """Lazy load LanceDB searcher."""
    global _searcher
    if _searcher is None and LANCEDB_AVAILABLE:
        _searcher = LanceDBPolicySearch(DB_PATH)
    return _searcher


# =============================================================================
# MCP TOOL: search
# =============================================================================

def tool_search(query: str, limit: int = 5, explain: bool = False) -> dict:
    """Search policies using hybrid RRF scoring.

    Args:
        query: Natural language query
        limit: Maximum results (default 5)
        explain: Include retriever breakdown (default False)

    Returns:
        Index of matching policies with scores and optional explanations.
        Use 'context' or 'details' tools for full content.
    """
    if len(query) < 3:
        return {"results": [], "message": "Query too short"}

    if not RECOMMEND_AVAILABLE:
        return {"error": "Recommendation engine not available", "results": []}

    try:
        formatted, explanations = get_recommendations(query)

        if not explanations:
            return {"results": [], "message": "No matches found"}

        # Limit results
        explanations = explanations[:limit]

        # Build response
        results = []
        for exp in explanations:
            result = {
                "policy_name": exp["policy_name"],
                "rrf_score": exp["rrf_score"],
                "confidence_tier": exp["confidence_tier"],
                "num_retrievers": len(exp["retriever_contributions"]),
            }

            # Include explanation if requested
            if explain:
                result["retriever_contributions"] = exp["retriever_contributions"]
                result["keywords_matched"] = exp["keywords_matched"]
                result["questions_matched"] = exp["questions_matched"][:3]

            results.append(result)

        return {
            "results": results,
            "total": len(results),
            "query": query,
        }

    except Exception as e:
        return {"error": str(e), "results": []}


# =============================================================================
# MCP TOOL: context
# =============================================================================

def tool_context(policy_name: str) -> dict:
    """Get CEP navigation context for a policy.

    Args:
        policy_name: Name of the policy (e.g., 'todo_hygiene')

    Returns:
        Policy metadata and CEP navigation guide for cognitive framing.
    """
    if not DB_PATH.exists():
        return {"error": "Policy index not found"}

    if not LANCEDB_AVAILABLE:
        return {"error": "LanceDB backend not available"}

    try:
        searcher = get_searcher()
        if not searcher:
            return {"error": "Failed to initialize LanceDB searcher"}

        # Search for exact policy name
        table = searcher.table
        results = table.search().where(f"policy_name = '{policy_name}'").limit(1).to_list()

        if not results:
            return {"error": f"Policy '{policy_name}' not found"}

        row = results[0]

        return {
            "policy_name": row["policy_name"],
            "tier": row.get("tier", ""),
            "category": row.get("category", ""),
            "description": row.get("description", ""),
            "cep_guide": row.get("cep_guide", ""),
            "cli_command": f"macf_tools policy navigate {policy_name}",
        }

    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# MCP TOOL: details
# =============================================================================

def tool_details(policy_names: list[str]) -> dict:
    """Get metadata and CLI commands for specified policies.

    Args:
        policy_names: List of policy names to fetch

    Returns:
        Policy metadata with CLI commands for full content retrieval.

    Note: Full policy content should be read via CLI for efficiency:
        macf_tools policy read <name>
        macf_tools policy read <name> --section N
    """
    if not DB_PATH.exists():
        return {"error": "Policy index not found"}

    if not policy_names:
        return {"error": "No policy names provided"}

    if not LANCEDB_AVAILABLE:
        return {"error": "LanceDB backend not available"}

    try:
        searcher = get_searcher()
        if not searcher:
            return {"error": "Failed to initialize LanceDB searcher"}

        table = searcher.table
        results = {}

        for name in policy_names[:5]:  # Limit to 5
            rows = table.search().where(f"policy_name = '{name}'").limit(1).to_list()

            if rows:
                row = rows[0]
                results[name] = {
                    "file_path": row.get("file_path", ""),
                    "cli_commands": {
                        "full": f"macf_tools policy read {name}",
                        "navigate": f"macf_tools policy navigate {name}",
                        "section": f"macf_tools policy read {name} --section N",
                    },
                }

        return {
            "policies": results,
            "fetched": len(results),
            "requested": len(policy_names),
            "note": "Use CLI commands for full content (cached, line numbers)",
        }

    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# MCP TOOL: explain
# =============================================================================

def tool_explain(query: str, policy_name: str) -> dict:
    """Get detailed explanation of why a policy matched a query.

    Args:
        query: The original search query
        policy_name: Policy to explain

    Returns:
        Full retriever breakdown showing WHY this policy matched.
    """
    if not RECOMMEND_AVAILABLE:
        return {"error": "Recommendation engine not available"}

    try:
        _, explanations = get_recommendations(query)

        # Find the specific policy
        for exp in explanations:
            if exp["policy_name"] == policy_name:
                return {
                    "policy_name": policy_name,
                    "query": query,
                    "rrf_score": exp["rrf_score"],
                    "confidence_tier": exp["confidence_tier"],
                    "retriever_contributions": exp["retriever_contributions"],
                    "keywords_matched": exp["keywords_matched"],
                    "questions_matched": exp["questions_matched"],
                    "interpretation": _interpret_match(exp),
                }

        return {"error": f"Policy '{policy_name}' not in results for query"}

    except Exception as e:
        return {"error": str(e)}


def _interpret_match(exp: dict) -> str:
    """Generate human-readable interpretation of match."""
    contribs = exp.get("retriever_contributions", {})
    num_retrievers = len(contribs)

    interpretations = []

    if num_retrievers == 4:
        interpretations.append("All 4 retrievers agree - high confidence match")
    elif num_retrievers >= 3:
        interpretations.append(f"{num_retrievers} retrievers found this policy")

    # Check which retrievers contributed most
    if "questions_fts" in contribs:
        q = contribs["questions_fts"]
        if q.get("rank", 99) <= 3:
            interpretations.append(f"Strong question match: '{q.get('matched_text', '')[:50]}'")

    if "policy_embeddings" in contribs:
        p = contribs["policy_embeddings"]
        if p.get("rank", 99) <= 3:
            interpretations.append("Semantically similar to query meaning")

    questions = exp.get("questions_matched", [])
    if questions:
        interpretations.append(f"Relevant sections: {questions[0][:60]}")

    return " | ".join(interpretations) if interpretations else "Standard match"


# =============================================================================
# MCP SERVER PROTOCOL
# =============================================================================

MCP_TOOLS = {
    "search": {
        "description": "Search policies using hybrid RRF scoring. Returns index with scores. Use 'explain=true' for retriever breakdown.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query"},
                "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
                "explain": {"type": "boolean", "description": "Include retriever breakdown", "default": False},
            },
            "required": ["query"],
        },
        "handler": tool_search,
    },
    "context": {
        "description": "Get CEP navigation context for a policy. Shows metadata and navigation guide without full content.",
        "parameters": {
            "type": "object",
            "properties": {
                "policy_name": {"type": "string", "description": "Policy name (e.g., 'todo_hygiene')"},
            },
            "required": ["policy_name"],
        },
        "handler": tool_context,
    },
    "details": {
        "description": "Get metadata and CLI commands for policies. Use CLI tools for full content retrieval (cached, with line numbers).",
        "parameters": {
            "type": "object",
            "properties": {
                "policy_names": {"type": "array", "items": {"type": "string"}, "description": "List of policy names"},
            },
            "required": ["policy_names"],
        },
        "handler": tool_details,
    },
    "explain": {
        "description": "Get detailed explanation of why a policy matched a query. Shows per-retriever breakdown.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "policy_name": {"type": "string", "description": "Policy to explain"},
            },
            "required": ["query", "policy_name"],
        },
        "handler": tool_explain,
    },
}


def handle_mcp_request(request: dict) -> dict:
    """Handle incoming MCP request."""
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "tools/list":
        tools = []
        for name, spec in MCP_TOOLS.items():
            tools.append({
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["parameters"],
            })
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in MCP_TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }

        handler = MCP_TOOLS[tool_name]["handler"]
        result = handler(**arguments)

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
        }

    elif method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "macf-policy-search", "version": "0.2.0"},
            },
        }

    return {"jsonrpc": "2.0", "id": req_id, "result": {}}


def main():
    """Run MCP server over stdio."""
    # Read JSON-RPC requests from stdin, write responses to stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = handle_mcp_request(request)
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }), flush=True)


if __name__ == "__main__":
    main()
