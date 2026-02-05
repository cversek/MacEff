"""
Transcript forensics for breadcrumb-targeted search with context windows.

Enables post-compaction archaeology by locating exact messages in JSONL transcripts
using breadcrumb coordinates and extracting surrounding context.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json


@dataclass
class TranscriptMessage:
    """Single message from transcript."""
    index: int
    role: str  # 'user' or 'assistant'
    content: str
    uuid: Optional[str] = None
    timestamp: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TranscriptWindow:
    """Window of messages around a target breadcrumb."""
    target_index: int
    target_message: TranscriptMessage
    before: List[TranscriptMessage]
    after: List[TranscriptMessage]
    transcript_path: str
    breadcrumb: str
    total_messages: int

    def all_messages(self) -> List[TranscriptMessage]:
        """Return all messages in order: before + target + after."""
        return self.before + [self.target_message] + self.after


def find_message_by_breadcrumb(
    breadcrumb: str,
    transcript_path: Optional[str] = None
) -> Optional[tuple[int, TranscriptMessage, str]]:
    """
    Find message in transcript matching breadcrumb's prompt_uuid.

    Args:
        breadcrumb: Breadcrumb string like "s_abc123/c_42/g_xyz/p_def456/t_123"
        transcript_path: Optional explicit path to JSONL. If None, derives from breadcrumb.

    Returns:
        Tuple of (message_index, TranscriptMessage, transcript_path) or None if not found.
    """
    from ..utils.breadcrumbs import parse_breadcrumb
    from ..utils.paths import get_session_transcript_path

    parsed = parse_breadcrumb(breadcrumb)
    if not parsed:
        return None

    prompt_uuid = parsed.get('prompt_uuid')
    session_id = parsed.get('session_id')

    if not prompt_uuid:
        return None

    # Find transcript path - breadcrumbs use truncated session IDs, so prefix match
    if not transcript_path:
        if not session_id:
            return None
        transcript_path = _find_transcript_by_prefix(session_id)
        if not transcript_path:
            return None

    # Search transcript for matching message
    path = Path(transcript_path)
    if not path.exists():
        return None

    with open(path, 'r') as f:
        for idx, line in enumerate(f):
            try:
                entry = json.loads(line.strip())
                # Check for uuid match in message
                entry_uuid = entry.get('uuid', '')
                if entry_uuid and prompt_uuid in entry_uuid:
                    msg = _entry_to_message(idx, entry)
                    return (idx, msg, str(path))
            except json.JSONDecodeError:
                continue

    return None


def extract_window(
    transcript_path: str,
    target_index: int,
    before: int = 3,
    after: int = 3
) -> Optional[TranscriptWindow]:
    """
    Extract window of messages around target index.

    Args:
        transcript_path: Path to JSONL transcript
        target_index: Index of target message
        before: Number of messages before target to include
        after: Number of messages after target to include

    Returns:
        TranscriptWindow with messages, or None if error.
    """
    path = Path(transcript_path)
    if not path.exists():
        return None

    messages = []
    with open(path, 'r') as f:
        for idx, line in enumerate(f):
            try:
                entry = json.loads(line.strip())
                messages.append(_entry_to_message(idx, entry))
            except json.JSONDecodeError:
                continue

    if target_index < 0 or target_index >= len(messages):
        return None

    target_msg = messages[target_index]

    # Extract before window
    start_before = max(0, target_index - before)
    before_msgs = messages[start_before:target_index]

    # Extract after window
    end_after = min(len(messages), target_index + after + 1)
    after_msgs = messages[target_index + 1:end_after]

    return TranscriptWindow(
        target_index=target_index,
        target_message=target_msg,
        before=before_msgs,
        after=after_msgs,
        transcript_path=transcript_path,
        breadcrumb="",  # Caller should set
        total_messages=len(messages)
    )


def search_by_breadcrumb(
    breadcrumb: str,
    before: int = 3,
    after: int = 3,
    transcript_path: Optional[str] = None
) -> Optional[TranscriptWindow]:
    """
    High-level function: find breadcrumb and extract context window.

    Args:
        breadcrumb: Breadcrumb string
        before: Messages before target
        after: Messages after target
        transcript_path: Optional explicit transcript path

    Returns:
        TranscriptWindow or None if breadcrumb not found.
    """
    result = find_message_by_breadcrumb(breadcrumb, transcript_path)
    if not result:
        return None

    idx, msg, path = result
    window = extract_window(path, idx, before, after)
    if window:
        window.breadcrumb = breadcrumb
    return window


def list_all_transcripts() -> List[str]:
    """
    List all transcript JSONL files in the Claude projects directory.

    Returns:
        List of absolute paths to JSONL files.
    """
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return []

    transcripts = []
    for jsonl_file in projects_dir.glob("**/*.jsonl"):
        transcripts.append(str(jsonl_file))

    return sorted(transcripts)


def search_all_transcripts(
    breadcrumb: str,
    before: int = 3,
    after: int = 3
) -> Optional[TranscriptWindow]:
    """
    Search all transcripts for breadcrumb.

    Args:
        breadcrumb: Breadcrumb string
        before: Messages before target
        after: Messages after target

    Returns:
        TranscriptWindow or None if not found in any transcript.
    """
    for transcript_path in list_all_transcripts():
        result = find_message_by_breadcrumb(breadcrumb, transcript_path)
        if result:
            idx, msg, path = result
            window = extract_window(path, idx, before, after)
            if window:
                window.breadcrumb = breadcrumb
                return window
    return None


def _find_transcript_by_prefix(session_id_prefix: str) -> Optional[str]:
    """Find transcript JSONL file by session ID prefix match."""
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return None

    # Search for JSONL files starting with the prefix
    for jsonl_file in projects_dir.glob("**/*.jsonl"):
        if jsonl_file.stem.startswith(session_id_prefix):
            return str(jsonl_file)

    return None


def _entry_to_message(idx: int, entry: Dict[str, Any]) -> TranscriptMessage:
    """Convert JSONL entry to TranscriptMessage."""
    role = entry.get('type', 'unknown')
    if role == 'human':
        role = 'user'

    # Extract content - handle different message formats
    content = ""
    message = entry.get('message', {})
    if isinstance(message, dict):
        msg_content = message.get('content', [])
        if isinstance(msg_content, list):
            # Claude API format: list of content blocks
            text_parts = []
            for block in msg_content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    text_parts.append(block.get('text', ''))
            content = '\n'.join(text_parts)
        elif isinstance(msg_content, str):
            content = msg_content
    elif isinstance(message, str):
        content = message

    # Fallback to raw entry content
    if not content and 'content' in entry:
        content = str(entry['content'])

    return TranscriptMessage(
        index=idx,
        role=role,
        content=content[:2000] if len(content) > 2000 else content,  # Truncate for display
        uuid=entry.get('uuid'),
        timestamp=entry.get('timestamp'),
        raw=entry
    )
