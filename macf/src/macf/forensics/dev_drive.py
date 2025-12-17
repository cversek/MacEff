"""
DEV_DRV Forensics - Extract and reconstruct complete conversation work units.

A DEV_DRV (Development Drive) spans from UserPromptSubmit to Stop event,
representing a complete unit of work with user request, thinking, tool calls, and outcomes.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils import get_session_transcript_path, parse_breadcrumb


@dataclass
class DevelopmentDrive:
    """
    Complete conversation work unit extracted from JSONL.

    Represents chronological message flow from user prompt through completion.
    """
    # Metadata from breadcrumb
    cycle: int
    session_id: str
    prompt_uuid: Optional[str]
    timestamp: Optional[float]
    git_hash: Optional[str]

    # Extracted messages in chronological order
    messages: List[Dict[str, Any]] = field(default_factory=list)

    # Drive boundaries
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration: Optional[float] = None

    # Statistics
    tool_call_count: int = 0
    thinking_block_count: int = 0
    assistant_message_count: int = 0
    user_message_count: int = 0


def extract_dev_drive(
    session_id: str,
    prompt_uuid: str,
    breadcrumb_data: Optional[Dict[str, Any]] = None
) -> Optional[DevelopmentDrive]:
    """
    Extract complete DEV_DRV from JSONL by following parentUuid chain.

    Args:
        session_id: Session identifier (can be short form like "4107604e")
        prompt_uuid: User prompt UUID that started the drive
        breadcrumb_data: Optional parsed breadcrumb with metadata

    Returns:
        DevelopmentDrive object or None if extraction fails

    Algorithm:
        1. Find JSONL file for session
        2. Locate user prompt by UUID
        3. Follow parentUuid chain until Stop event
        4. Extract all messages preserving chronological order
        5. Calculate statistics
    """
    try:
        # Get full session ID if short form provided
        jsonl_path_str = get_session_transcript_path(session_id)
        if not jsonl_path_str:
            return None

        jsonl_path = Path(jsonl_path_str)
        if not jsonl_path.exists():
            return None

        # Load all JSONL entries
        entries = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # Build UUID lookup for fast parentUuid chain following
        uuid_lookup = {entry.get('uuid'): entry for entry in entries if entry.get('uuid')}

        # Find user prompt that started this drive
        start_entry = None
        for entry in entries:
            if entry.get('uuid') == prompt_uuid:
                start_entry = entry
                break

        if not start_entry:
            return None

        # Follow parentUuid chain forward to collect all messages
        messages = []
        current_uuid = start_entry.get('uuid')
        started_at = start_entry.get('timestamp')
        ended_at = None

        # Track statistics
        tool_calls = 0
        thinking_blocks = 0
        assistant_msgs = 0
        user_msgs = 0

        # Follow chain until we hit Stop event or run out of messages
        seen_uuids = set()
        while current_uuid:
            # Prevent infinite loops
            if current_uuid in seen_uuids:
                break
            seen_uuids.add(current_uuid)

            # Find all entries with this UUID as parent
            children = [e for e in entries if e.get('parentUuid') == current_uuid]

            if not children:
                break

            # Take first child (chronological)
            child = children[0]
            messages.append(child)

            # Update statistics
            msg_type = child.get('type')
            if msg_type == 'assistant':
                assistant_msgs += 1
                content = child.get('message', {}).get('content', [])
                for item in content:
                    if isinstance(item, dict):
                        if item.get('type') == 'thinking':
                            thinking_blocks += 1
                        elif item.get('type') == 'tool_use':
                            tool_calls += 1
            elif msg_type == 'user':
                user_msgs += 1
            elif msg_type == 'system':
                content = child.get('content', '')
                if 'DEV_DRV Complete' in content:
                    ended_at = child.get('timestamp')
                    messages.append(child)  # Include Stop event
                    break

            current_uuid = child.get('uuid')

        # Calculate duration if we have both timestamps
        duration = None
        if started_at and ended_at:
            try:
                from datetime import datetime
                start_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(ended_at.replace('Z', '+00:00'))
                duration = (end_dt - start_dt).total_seconds()
            except (ValueError, TypeError) as e:
                print(f"⚠️ MACF: DateTime parsing failed: {e}", file=sys.stderr)

        # Build DevelopmentDrive object
        drive = DevelopmentDrive(
            cycle=breadcrumb_data.get('cycle', 0) if breadcrumb_data else 0,
            session_id=session_id,
            prompt_uuid=prompt_uuid,
            timestamp=breadcrumb_data.get('timestamp') if breadcrumb_data else None,
            git_hash=breadcrumb_data.get('git_hash') if breadcrumb_data else None,
            messages=messages,
            started_at=started_at,
            ended_at=ended_at,
            duration=duration,
            tool_call_count=tool_calls,
            thinking_block_count=thinking_blocks,
            assistant_message_count=assistant_msgs,
            user_message_count=user_msgs
        )

        return drive

    except Exception:
        return None


def render_markdown_summary(drive: DevelopmentDrive) -> str:
    """
    Render DEV_DRV as human-readable markdown summary.

    Args:
        drive: DevelopmentDrive object

    Returns:
        Formatted markdown string
    """
    from ..utils import format_breadcrumb

    # Build breadcrumb for header
    breadcrumb = format_breadcrumb(
        drive.cycle,
        drive.session_id,
        drive.prompt_uuid,
        drive.timestamp
    )

    if drive.git_hash:
        breadcrumb += f"/g_{drive.git_hash}"

    lines = [
        f"# DEV_DRV Summary: {breadcrumb}",
        "",
        "## Metadata",
        f"- **Cycle**: {drive.cycle}",
        f"- **Session**: {drive.session_id}",
        f"- **Prompt UUID**: {drive.prompt_uuid or 'unknown'}",
    ]

    if drive.git_hash:
        lines.append(f"- **Git Commit**: {drive.git_hash}")

    if drive.started_at:
        lines.append(f"- **Started**: {drive.started_at}")
    if drive.ended_at:
        lines.append(f"- **Completed**: {drive.ended_at}")
    if drive.duration:
        lines.append(f"- **Duration**: {drive.duration:.1f}s")

    lines.extend([
        "",
        "## Statistics",
        f"- **Messages**: {len(drive.messages)}",
        f"- **Tool Calls**: {drive.tool_call_count}",
        f"- **Thinking Blocks**: {drive.thinking_block_count}",
        f"- **Assistant Messages**: {drive.assistant_message_count}",
        f"- **User Messages**: {drive.user_message_count}",
        "",
        "## Conversation Flow",
        ""
    ])

    # Render chronological message flow
    for i, msg in enumerate(drive.messages, 1):
        msg_type = msg.get('type', 'unknown')
        timestamp = msg.get('timestamp', 'unknown')

        lines.append(f"### [{i}] {timestamp}")

        if msg_type == 'user':
            content = msg.get('message', {}).get('content', [])
            if isinstance(content, list) and len(content) > 0:
                first = content[0]
                if isinstance(first, dict):
                    if 'tool_use_id' in first:
                        lines.append(f"**Tool Result**: {first.get('tool_use_id', 'unknown')[:12]}")
                    elif first.get('type') == 'text':
                        text = first.get('text', '')[:200]
                        lines.append(f"**User**: {text}...")
            elif isinstance(content, str):
                if 'user-prompt-submit-hook' in content:
                    lines.append("**Hook**: UserPromptSubmit")
                elif 'post-tool-use-hook' in content:
                    lines.append("**Hook**: PostToolUse")
                else:
                    lines.append(f"**User**: {content[:200]}...")

        elif msg_type == 'assistant':
            content = msg.get('message', {}).get('content', [])
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get('type')
                    if item_type == 'thinking':
                        thinking = item.get('thinking', '')[:200]
                        lines.append(f"**Thinking**: {thinking}...")
                    elif item_type == 'text':
                        text = item.get('text', '')[:200]
                        lines.append(f"**Response**: {text}...")
                    elif item_type == 'tool_use':
                        tool_name = item.get('name', 'unknown')
                        lines.append(f"**Tool Call**: {tool_name}")

        elif msg_type == 'system':
            content = msg.get('content', '')[:100]
            lines.append(f"**System**: {content}")

        lines.append("")

    return "\n".join(lines)


def render_raw_jsonl(drive: DevelopmentDrive) -> str:
    """
    Render DEV_DRV as raw JSONL (intact records).

    Args:
        drive: DevelopmentDrive object

    Returns:
        JSONL string with one record per line
    """
    lines = []
    for msg in drive.messages:
        lines.append(json.dumps(msg, ensure_ascii=False))
    return "\n".join(lines)
