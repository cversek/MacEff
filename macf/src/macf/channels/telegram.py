"""Telegram notification via Bot API. Stdlib only (no external deps).

Config resolution (first match wins):
1. {project_root}/.claude/channels/telegram/  (project-specific)
2. ~/.claude/channels/telegram/               (user-level fallback)

Required files in config dir:
- .env: contains TELEGRAM_BOT_TOKEN=...
- access.json: contains allowFrom list with chat IDs
"""

import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple


def _read_token(config_dir: Path) -> Optional[str]:
    """Read TELEGRAM_BOT_TOKEN from .env file."""
    env_file = config_dir / '.env'
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        if line.startswith('TELEGRAM_BOT_TOKEN='):
            return line.split('=', 1)[1].strip()
    return None


def _read_chat_id(config_dir: Path) -> Optional[str]:
    """Read first allowFrom entry from access.json."""
    access_file = config_dir / 'access.json'
    if not access_file.exists():
        return None
    try:
        access = json.loads(access_file.read_text())
        allow = access.get('allowFrom', [])
        return allow[0] if allow else None
    except (json.JSONDecodeError, IndexError):
        return None


def resolve_telegram_config() -> Optional[Tuple[str, str]]:
    """Resolve Telegram bot token and chat ID with multi-tier fallback.

    Resolution order:
    1. Project-level: {project_root}/.claude/channels/telegram/
    2. User-level: ~/.claude/channels/telegram/

    Returns:
        Tuple of (token, chat_id) if configured, None otherwise.
    """
    # Tier 1: Project-level
    try:
        from macf.utils.paths import find_project_root
        project_root = find_project_root()
        if project_root:
            project_dir = project_root / '.claude' / 'channels' / 'telegram'
            token = _read_token(project_dir)
            chat_id = _read_chat_id(project_dir)
            if token and chat_id:
                return (token, chat_id)
    except Exception:
        pass

    # Tier 2: User-level fallback
    user_dir = Path.home() / '.claude' / 'channels' / 'telegram'
    token = _read_token(user_dir)
    chat_id = _read_chat_id(user_dir)
    if token and chat_id:
        return (token, chat_id)

    return None


def send_telegram_notification(text: str, max_length: int = 4000) -> bool:
    """Send a message to the configured Telegram chat.

    Returns False silently if Telegram is not configured.
    Logs to stderr on API errors (visible but non-fatal).

    Args:
        text: Message text (truncated to max_length)
        max_length: Telegram limit is 4096, we use 4000 for safety

    Returns:
        True if sent successfully, False if not configured or failed.
    """
    config = resolve_telegram_config()
    if not config:
        return False

    token, chat_id = config
    truncated = text[:max_length] + ('...' if len(text) > max_length else '')

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        'chat_id': chat_id,
        'text': truncated
    }).encode()

    try:
        urllib.request.urlopen(url, data, timeout=5)
        return True
    except Exception as e:
        print(f"MACF: Telegram notification failed: {e}", file=sys.stderr)
        return False
