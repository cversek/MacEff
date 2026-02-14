"""
Message rewriter for proxy request body modification.

Implements stateless policy injection management — on each request:
1. Determine which policies should be active (from event log)
2. Retract injections for policies that are no longer active
3. Deduplicate any policies that appear more than once

Marker formats:
  replaced_at  — earlier copy superseded by a later injection
  retracted_at — policy no longer active, content removed
"""

import json
import os
import re
import sys
from typing import Any

# Regex to match full policy injection tags (multiline content)
FULL_INJECTION_PATTERN = re.compile(
    r'<macf-policy-injection\s+policy="([^"]+)">'
    r'(.*?)'
    r'</macf-policy-injection>',
    re.DOTALL
)

# Regex to match self-closing marker (already replaced/retracted)
MARKER_PATTERN = re.compile(
    r'<macf-policy-injection\s+policy="[^"]+"\s+(?:replaced|retracted)_at="\d+"\s*/>'
)


def make_marker(policy_name: str, marker_type: str, msg_idx: int) -> str:
    """Create replacement marker with message index for linked-list traversal.

    Args:
        policy_name: Name of the policy being marked
        marker_type: "replaced_at" (points to next occurrence) or
                     "retracted_at" (chain terminator, self-referential)
        msg_idx: Message index this marker points to
    """
    return f'<macf-policy-injection policy="{policy_name}" {marker_type}="{msg_idx}" />'


def get_active_policies(event_log_path: str) -> set[str]:
    """
    Scan event log to determine which policies should currently be active.

    Stateless: scans full log, returns set of policy names whose most recent
    event is 'policy_injection_activated' (not 'cleared').
    """
    if not event_log_path or not os.path.exists(event_log_path):
        return set()

    policy_states: dict[str, str] = {}

    try:
        with open(event_log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                evt_type = event.get("event", "")
                data = event.get("data", {})
                policy_name = data.get("policy_name", "")

                if not policy_name:
                    continue

                if evt_type == "policy_injection_activated":
                    policy_states[policy_name] = "activated"
                elif evt_type == "policy_injection_cleared":
                    policy_states[policy_name] = "cleared"
    except (OSError, IOError) as e:
        print(f"[message_rewriter] ERROR reading event log: {e}", file=sys.stderr)

    return {name for name, state in policy_states.items() if state == "activated"}


def _find_injections(messages: list[dict[str, Any]]) -> list[tuple]:
    """
    Find ALL full injection positions in the messages array.

    Returns list of (msg_idx, block_idx_or_None, policy_name, full_match, start, end).
    Only scans user-role messages to avoid false positives from assistant
    messages that quote/discuss the tag format.
    """
    injections = []

    for msg_idx, msg in enumerate(messages):
        if msg.get("role") != "user":
            continue

        content = msg.get("content", "")

        if isinstance(content, str):
            for match in FULL_INJECTION_PATTERN.finditer(content):
                name = match.group(1)
                if "{" not in name and "}" not in name:
                    injections.append((
                        msg_idx, None, name, match.group(0),
                        match.start(), match.end()
                    ))

        elif isinstance(content, list):
            for block_idx, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    for match in FULL_INJECTION_PATTERN.finditer(text):
                        name = match.group(1)
                        if "{" not in name and "}" not in name:
                            injections.append((
                                msg_idx, block_idx, name, match.group(0),
                                match.start(), match.end()
                            ))

    return injections


def _select_replacements(
    injections: list[tuple],
    retract_policies: set[str],
) -> dict[tuple, tuple[str, int]]:
    """
    Determine which injections to replace and with which marker type.

    Returns dict mapping position keys to (marker_type, target_msg_idx):
        - ("replaced_at", N) for earlier copies — N is msg_idx of next occurrence
        - ("retracted_at", N) for final copies — N is own msg_idx (chain terminator)

    The target_msg_idx values form a forward-linked list through the conversation:
        msg[50] replaced_at=94 → msg[94] retracted_at=94 (end of chain)

    Logic:
        - Policies in retract_policies: ALL copies replaced.
          Earlier copies get replaced_at pointing forward, final gets retracted_at.
        - Active policies (not in retract_policies): deduplicate only.
          Earlier copies get replaced_at pointing to latest, latest preserved.
    """
    to_replace: dict[tuple, tuple[str, int]] = {}

    # Group by policy name
    policy_groups: dict[str, list] = {}
    for inj in injections:
        policy_groups.setdefault(inj[2], []).append(inj)

    for policy_name, group in policy_groups.items():
        if policy_name in retract_policies:
            # Retract: replace ALL copies with linked-list markers
            for i, inj in enumerate(group[:-1]):
                key = (inj[0], inj[1], inj[4], inj[5])
                next_msg_idx = group[i + 1][0]  # msg_idx of next occurrence
                to_replace[key] = ("replaced_at", next_msg_idx)
            last = group[-1]
            key = (last[0], last[1], last[4], last[5])
            to_replace[key] = ("retracted_at", last[0])  # self-referential
        else:
            # Active: deduplicate only (keep latest)
            if len(group) > 1:
                for i, inj in enumerate(group[:-1]):
                    key = (inj[0], inj[1], inj[4], inj[5])
                    next_msg_idx = group[i + 1][0] if i + 1 < len(group) - 1 else group[-1][0]
                    to_replace[key] = ("replaced_at", next_msg_idx)

    return to_replace


def _apply_replacements(
    messages: list[dict[str, Any]],
    injections: list[tuple],
    to_replace: dict[tuple, tuple[str, int]],
) -> dict:
    """
    Apply marker replacements to messages in-place.

    Args:
        to_replace: dict mapping (msg_idx, block_idx, start, end) -> (marker_type, target_msg_idx)

    Returns stats dict with replacements_made, bytes_saved, retracted, deduplicated.
    """
    stats = {"replacements_made": 0, "bytes_saved": 0, "retracted": [], "deduplicated": []}

    # Build position-to-policy mapping
    position_to_policy = {}
    for inj in injections:
        key = (inj[0], inj[1], inj[4], inj[5])
        if key in to_replace:
            position_to_policy[key] = inj[2]

    # Group by message index
    replacements_by_msg: dict[int, list] = {}
    for (msg_idx, block_idx, start, end), (marker_type, target_idx) in to_replace.items():
        replacements_by_msg.setdefault(msg_idx, []).append(
            (block_idx, start, end, marker_type, target_idx)
        )

    for msg_idx in sorted(replacements_by_msg.keys()):
        content = messages[msg_idx].get("content", "")

        if isinstance(content, str):
            new_content = content
            for _, start, end, marker_type, target_idx in sorted(
                replacements_by_msg[msg_idx], key=lambda x: x[1], reverse=True
            ):
                policy_name = position_to_policy[(msg_idx, None, start, end)]
                marker = make_marker(policy_name, marker_type, target_idx)
                stats["bytes_saved"] += len(new_content[start:end]) - len(marker)
                stats["replacements_made"] += 1
                if marker_type == "retracted_at":
                    if policy_name not in stats["retracted"]:
                        stats["retracted"].append(policy_name)
                else:
                    if policy_name not in stats["deduplicated"]:
                        stats["deduplicated"].append(policy_name)
                new_content = new_content[:start] + marker + new_content[end:]
            messages[msg_idx]["content"] = new_content

        elif isinstance(content, list):
            blocks_to_modify: dict[int, list] = {}
            for block_idx, start, end, marker_type, target_idx in replacements_by_msg[msg_idx]:
                if block_idx is not None:
                    blocks_to_modify.setdefault(block_idx, []).append(
                        (start, end, marker_type, target_idx)
                    )

            for block_idx in sorted(blocks_to_modify.keys(), reverse=True):
                block = content[block_idx]
                if block.get("type") == "text":
                    new_text = block.get("text", "")
                    for start, end, marker_type, target_idx in sorted(
                        blocks_to_modify[block_idx], reverse=True
                    ):
                        policy_name = position_to_policy[
                            (msg_idx, block_idx, start, end)
                        ]
                        marker = make_marker(policy_name, marker_type, target_idx)
                        stats["bytes_saved"] += len(new_text[start:end]) - len(marker)
                        stats["replacements_made"] += 1
                        if marker_type == "retracted_at":
                            if policy_name not in stats["retracted"]:
                                stats["retracted"].append(policy_name)
                        else:
                            if policy_name not in stats["deduplicated"]:
                                stats["deduplicated"].append(policy_name)
                        new_text = new_text[:start] + marker + new_text[end:]
                    content[block_idx]["text"] = new_text

    return stats


def rewrite_messages(
    messages: list[dict[str, Any]],
    event_log_path: str,
) -> tuple[list[dict[str, Any]], dict]:
    """
    Stateless policy injection rewriter.

    On each call:
    1. Find all policy injections in messages
    2. Determine which policies are currently active (from event log)
    3. Retract inactive policies, deduplicate active ones

    Args:
        messages: The messages array from the API request body
        event_log_path: Path to the MACF event log

    Returns:
        (modified_messages, stats)
    """
    stats = {
        "replacements_made": 0, "bytes_saved": 0,
        "retracted": [], "deduplicated": [],
    }

    if not messages:
        return messages, stats

    injections = _find_injections(messages)
    if not injections:
        return messages, stats

    # Stateless: determine what should be active RIGHT NOW
    active_policies = get_active_policies(event_log_path)
    found_policies = {inj[2] for inj in injections}
    retract_policies = found_policies - active_policies

    to_replace = _select_replacements(injections, retract_policies)
    if not to_replace:
        return messages, stats

    replacement_stats = _apply_replacements(messages, injections, to_replace)
    stats.update(replacement_stats)

    return messages, stats
