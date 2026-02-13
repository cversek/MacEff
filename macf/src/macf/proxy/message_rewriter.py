"""
Message rewriter for proxy request body modification.

Implements the first "feedback loop" — replaces stale policy injections with
minimal archaeological markers, reclaiming context window space.

Architecture:
    1. Deduplicate mode: Replace earlier occurrences of same policy (keep last)
    2. Cleanup_all mode: Replace ALL policy injections after task_completed

Marker format: <macf-policy-injection name="policy_name" replaced_at="BREADCRUMB" />
"""

import json
import os
import re
import sys
from typing import Any

from ..utils.breadcrumbs import get_breadcrumb


# Regex to match full policy injection tags (multiline content)
FULL_INJECTION_PATTERN = re.compile(
    r'<macf-policy-injection\s+policy="([^"]+)">'
    r'(.*?)'
    r'</macf-policy-injection>',
    re.DOTALL
)

# Regex to match self-closing marker (already replaced)
MARKER_PATTERN = re.compile(
    r'<macf-policy-injection\s+name="[^"]+"\s+replaced_at="[^"]+"\s*/>'
)


def make_marker(policy_name: str) -> str:
    """Create replacement marker with archaeological breadcrumb."""
    breadcrumb = get_breadcrumb()
    return f'<macf-policy-injection name="{policy_name}" replaced_at="{breadcrumb}" />'


def _find_injections(messages: list[dict[str, Any]]) -> list[tuple]:
    """
    First pass: find ALL full injection positions in the messages array.

    Returns list of (msg_idx, block_idx_or_None, policy_name, full_match, start, end).
    """
    injections = []

    for msg_idx, msg in enumerate(messages):
        content = msg.get("content", "")

        if isinstance(content, str):
            for match in FULL_INJECTION_PATTERN.finditer(content):
                injections.append((
                    msg_idx, None, match.group(1), match.group(0),
                    match.start(), match.end()
                ))

        elif isinstance(content, list):
            for block_idx, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    for match in FULL_INJECTION_PATTERN.finditer(text):
                        injections.append((
                            msg_idx, block_idx, match.group(1), match.group(0),
                            match.start(), match.end()
                        ))

    return injections


def _select_replacements(injections: list[tuple], mode: str) -> tuple[set, list[str]]:
    """
    Determine which injections to replace based on mode.

    Returns (to_replace set of position keys, policies_replaced list).
    """
    to_replace = set()
    policies_replaced = []

    if mode == "cleanup_all":
        to_replace = {(inj[0], inj[1], inj[4], inj[5]) for inj in injections}
        policies_replaced = list(set(inj[2] for inj in injections))

    else:  # deduplicate
        policy_groups: dict[str, list] = {}
        for inj in injections:
            policy_groups.setdefault(inj[2], []).append(inj)

        for policy_name, group in policy_groups.items():
            if len(group) > 1:
                for inj in group[:-1]:  # replace all but last
                    to_replace.add((inj[0], inj[1], inj[4], inj[5]))
                policies_replaced.append(policy_name)

    return to_replace, policies_replaced


def _apply_replacements(
    messages: list[dict[str, Any]],
    injections: list[tuple],
    to_replace: set,
) -> dict:
    """
    Apply marker replacements to messages in-place.

    Returns stats dict with replacements_made and bytes_saved.
    """
    stats = {"replacements_made": 0, "bytes_saved": 0}

    # Build position-to-policy mapping
    position_to_policy = {}
    for inj in injections:
        key = (inj[0], inj[1], inj[4], inj[5])
        if key in to_replace:
            position_to_policy[key] = inj[2]

    # Group by message index
    replacements_by_msg: dict[int, list] = {}
    for msg_idx, block_idx, start, end in to_replace:
        replacements_by_msg.setdefault(msg_idx, []).append((block_idx, start, end))

    for msg_idx in sorted(replacements_by_msg.keys()):
        content = messages[msg_idx].get("content", "")

        if isinstance(content, str):
            new_content = content
            for _, start, end in sorted(replacements_by_msg[msg_idx], key=lambda x: x[1], reverse=True):
                policy_name = position_to_policy[(msg_idx, None, start, end)]
                marker = make_marker(policy_name)
                stats["bytes_saved"] += len(new_content[start:end]) - len(marker)
                stats["replacements_made"] += 1
                new_content = new_content[:start] + marker + new_content[end:]
            messages[msg_idx]["content"] = new_content

        elif isinstance(content, list):
            blocks_to_modify: dict[int, list] = {}
            for block_idx, start, end in replacements_by_msg[msg_idx]:
                if block_idx is not None:
                    blocks_to_modify.setdefault(block_idx, []).append((start, end))

            for block_idx in sorted(blocks_to_modify.keys(), reverse=True):
                block = content[block_idx]
                if block.get("type") == "text":
                    new_text = block.get("text", "")
                    for start, end in sorted(blocks_to_modify[block_idx], reverse=True):
                        policy_name = position_to_policy[(msg_idx, block_idx, start, end)]
                        marker = make_marker(policy_name)
                        stats["bytes_saved"] += len(new_text[start:end]) - len(marker)
                        stats["replacements_made"] += 1
                        new_text = new_text[:start] + marker + new_text[end:]
                    content[block_idx]["text"] = new_text

    return stats


def rewrite_messages(
    messages: list[dict[str, Any]], mode: str = "deduplicate"
) -> tuple[list[dict[str, Any]], dict]:
    """
    Scan messages array and replace stale policy injections with markers.

    Args:
        messages: The messages array from the API request body
        mode: "deduplicate" (keep last of each policy) or "cleanup_all" (replace all)

    Returns:
        (modified_messages, stats) where stats contains replacement counts
    """
    stats = {"replacements_made": 0, "bytes_saved": 0, "policies_replaced": []}

    if not messages:
        return messages, stats

    injections = _find_injections(messages)
    if not injections:
        return messages, stats

    to_replace, policies_replaced = _select_replacements(injections, mode)
    if not to_replace:
        return messages, stats

    replacement_stats = _apply_replacements(messages, injections, to_replace)
    stats["replacements_made"] = replacement_stats["replacements_made"]
    stats["bytes_saved"] = replacement_stats["bytes_saved"]
    stats["policies_replaced"] = policies_replaced

    return messages, stats


def detect_replacement_mode(event_log_path: str, since_ts: float) -> str:
    """
    Check event log for task_completed events since timestamp.
    Returns "cleanup_all" if found, else "deduplicate".
    """
    if not event_log_path:
        print("[message_rewriter] WARNING: empty event_log_path", file=sys.stderr)
        return "deduplicate"

    if not os.path.exists(event_log_path):
        print(f"[message_rewriter] WARNING: event log not found: {event_log_path}", file=sys.stderr)
        return "deduplicate"

    try:
        with open(event_log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"[message_rewriter] WARNING: malformed event log line: {e}", file=sys.stderr)
                    continue
                ts = event.get("timestamp", 0)
                if ts > since_ts and event.get("event") == "task_completed":
                    return "cleanup_all"
    except (OSError, IOError) as e:
        print(f"[message_rewriter] ERROR: failed to read event log: {e}", file=sys.stderr)

    return "deduplicate"


def get_event_log_path() -> str:
    """Get the event log path for mode detection."""
    agent_home = os.environ.get("MACEFF_AGENT_HOME_DIR", os.getcwd())
    return os.path.join(agent_home, ".maceff", "agent_events_log.jsonl")
