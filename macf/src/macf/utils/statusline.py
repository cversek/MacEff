"""
Statusline formatting utilities for Claude Code integration.

Provides formatted statusline output for display in Claude Code's UI.
"""

import os
import sys
import json
from typing import Dict, Any, Optional
from pathlib import Path

from .tokens import get_token_info, CC2_TOTAL_CONTEXT
from .environment import detect_execution_environment
from ..config import ConsciousnessConfig


def format_tokens(value: int) -> str:
    """
    Format token count with 'k' suffix for values >= 10,000.

    Args:
        value: Token count

    Returns:
        Formatted string (e.g., "60k" for 60000, "9500" for 9500)
    """
    if value >= 10000:
        return f"{value // 1000}k"
    return str(value)


def detect_project(workspace_path: Optional[str] = None) -> Optional[str]:
    """
    Detect project name from workspace context.

    Priority:
    1. MACF_PROJECT env var (explicit override)
    2. Directory name containing .claude/

    Args:
        workspace_path: Optional workspace path to search from (defaults to cwd)

    Returns:
        Project name or None if not detected
    """
    # 1. Check env var
    if project := os.getenv("MACF_PROJECT"):
        return project

    # 2. Find directory with .claude/
    cwd = Path(workspace_path) if workspace_path else Path.cwd()
    current = cwd
    while current != current.parent:
        if (current / ".claude").exists():
            return current.name
        current = current.parent

    return None


def format_statusline(
    agent_name: str,
    project: Optional[str],
    environment: str,
    tokens_used: int,
    tokens_total: int,
    cluac: int
) -> str:
    """
    Format statusline string for Claude Code display.

    Args:
        agent_name: Agent identifier
        project: Project name (optional - omit field if None)
        environment: Execution environment string
        tokens_used: Current token usage
        tokens_total: Maximum token capacity
        cluac: CLUAC level (percentage remaining)

    Returns:
        Formatted statusline: "agent | project | env | tokens CLUAC level"

    Example:
        "manny | NeuroVEP | Container Linux | 60k/200k CLUAC 70"
    """
    # Format tokens
    tokens_str = f"{format_tokens(tokens_used)}/{format_tokens(tokens_total)}"

    # Build fields list
    fields = [agent_name]

    if project:
        fields.append(project)

    fields.append(environment)
    fields.append(f"{tokens_str} CLUAC {cluac}")

    return " | ".join(fields)


def get_statusline_data(cc_json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Gather all statusline data from available sources.

    Merges Claude Code JSON input (if provided) with MACF-sourced data.
    CC JSON takes priority for token counts when available.

    Args:
        cc_json: Optional Claude Code JSON dict from stdin

    Returns:
        Dictionary with keys:
        - agent_name: str
        - project: Optional[str]
        - environment: str
        - tokens_used: int
        - tokens_total: int
        - cluac: int
    """
    # Get MACF-sourced data
    try:
        config = ConsciousnessConfig()
        agent_name = config.agent_id
    except Exception as e:
        print(f"⚠️ MACF: Agent name detection failed: {e}", file=sys.stderr)
        agent_name = "unknown"

    # Project detection (env var or workspace detection)
    project = detect_project()

    # Environment detection
    try:
        environment = detect_execution_environment()
    except Exception as e:
        print(f"⚠️ MACF: Environment detection failed: {e}", file=sys.stderr)
        environment = "Unknown"

    # Token info - prefer CC JSON, fallback to MACF
    if cc_json:
        tokens_used = cc_json.get("tokens_used", 0)
        tokens_total = cc_json.get("tokens_total", CC2_TOTAL_CONTEXT)
        # Calculate CLUAC from CC data if not provided
        if "cluac" in cc_json:
            cluac = cc_json["cluac"]
        else:
            tokens_remaining = tokens_total - tokens_used
            cluac = round((tokens_remaining / tokens_total) * 100) if tokens_total > 0 else 100
    else:
        try:
            token_info = get_token_info()
            tokens_used = token_info.get("tokens_used", 0)
            tokens_total = CC2_TOTAL_CONTEXT
            cluac = token_info.get("cluac_level", 100)
        except Exception as e:
            print(f"⚠️ MACF: Token info failed: {e}", file=sys.stderr)
            tokens_used = 0
            tokens_total = CC2_TOTAL_CONTEXT
            cluac = 100

    return {
        "agent_name": agent_name,
        "project": project,
        "environment": environment,
        "tokens_used": tokens_used,
        "tokens_total": tokens_total,
        "cluac": cluac
    }
