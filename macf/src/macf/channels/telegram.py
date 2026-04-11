"""Telegram notification via Bot API. Stdlib only (no external deps).

Config resolution (first match wins):
1. {project_root}/.claude/channels/telegram/  (project-specific)
2. ~/.claude/channels/telegram/               (user-level fallback)

Required files in config dir:
- .env: contains TELEGRAM_BOT_TOKEN=...
- access.json: contains allowFrom list with chat IDs
"""

import io
import json
import os
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple


def _html_escape(text: str) -> str:
    """Escape text for Telegram HTML parse_mode (only <, >, & need escaping)."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


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
    except (OSError, ImportError) as e:
        print(f"⚠️ MACF: telegram config discovery failed at project level: {e}", file=sys.stderr)

    # Tier 2: User-level fallback
    user_dir = Path.home() / '.claude' / 'channels' / 'telegram'
    token = _read_token(user_dir)
    chat_id = _read_chat_id(user_dir)
    if token and chat_id:
        return (token, chat_id)

    return None


def send_telegram_notification(text: str, prefix: str = "",
                               page_size: int = 4000,
                               parse_mode: Optional[str] = None) -> bool:
    """Send a message to the configured Telegram chat, paginating if needed.

    Returns False silently if Telegram is not configured.
    Logs to stderr on API errors (visible but non-fatal).

    Long messages are split into multiple pages. When paginated, the prefix
    is augmented with (page/total) on each message.

    Args:
        text: Message body text.
        prefix: Optional prefix line (e.g. emoji + "Agent stopped").
            Placed before body on each page.
        page_size: Max chars per Telegram message (API limit 4096, default 4000 for safety).
        parse_mode: Optional Telegram parse mode ("HTML" or "MarkdownV2").
            Default None sends plain text. When using HTML, caller must
            escape content with _html_escape().

    Returns:
        True if all pages sent successfully, False if not configured or failed.
    """
    config = resolve_telegram_config()
    if not config:
        return False

    token, chat_id = config

    # Calculate available body space per page (prefix + newlines overhead)
    prefix_base_len = len(prefix) + 2 if prefix else 0  # +2 for \n\n
    page_tag_reserve = 10  # " (NN/NN)" max
    body_budget = page_size - prefix_base_len - page_tag_reserve

    # Split text into pages
    if body_budget <= 0:
        body_budget = page_size  # Fallback: skip prefix if too long
    pages = []
    remaining = text
    while remaining:
        pages.append(remaining[:body_budget])
        remaining = remaining[body_budget:]

    total = len(pages)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    success = True

    for i, page_body in enumerate(pages, 1):
        if prefix:
            if total > 1:
                header = f"{prefix} ({i}/{total})"
            else:
                header = prefix
            message = f"{header}\n\n{page_body}"
        else:
            if total > 1:
                message = f"({i}/{total})\n\n{page_body}"
            else:
                message = page_body

        params = {
            'chat_id': chat_id,
            'text': message
        }
        if parse_mode:
            params['parse_mode'] = parse_mode

        data = urllib.parse.urlencode(params).encode()

        try:
            urllib.request.urlopen(url, data, timeout=5)
        except Exception as e:
            print(f"MACF: Telegram notification failed (page {i}/{total}): {e}",
                  file=sys.stderr)
            success = False

    return success


def send_telegram_document(content: str, filename: str,
                           caption: str = "") -> bool:
    """Send a text file as a Telegram document attachment.

    Uses multipart/form-data encoding (required by sendDocument API).

    Args:
        content: File content as string.
        filename: Display filename (e.g. "file.py", "diff.txt").
        caption: Optional caption text (max 1024 chars).

    Returns:
        True if sent successfully, False if not configured or failed.
    """
    config = resolve_telegram_config()
    if not config:
        return False

    token, chat_id = config
    url = f"https://api.telegram.org/bot{token}/sendDocument"

    # Build multipart/form-data manually (stdlib only, no requests)
    boundary = '----MacfTelegramBoundary'
    body = io.BytesIO()

    # chat_id field
    body.write(f'--{boundary}\r\n'.encode())
    body.write(b'Content-Disposition: form-data; name="chat_id"\r\n\r\n')
    body.write(f'{chat_id}\r\n'.encode())

    # caption field (if provided)
    if caption:
        body.write(f'--{boundary}\r\n'.encode())
        body.write(b'Content-Disposition: form-data; name="caption"\r\n\r\n')
        body.write(f'{caption[:1024]}\r\n'.encode())

    # document field (file upload)
    body.write(f'--{boundary}\r\n'.encode())
    body.write(f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode())
    body.write(b'Content-Type: application/octet-stream\r\n\r\n')
    body.write(content.encode('utf-8'))
    body.write(b'\r\n')

    # Closing boundary
    body.write(f'--{boundary}--\r\n'.encode())

    req = urllib.request.Request(
        url,
        data=body.getvalue(),
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )

    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"MACF: Telegram document send failed: {e}", file=sys.stderr)
        return False
