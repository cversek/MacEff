"""Telegram notification via Bot API. Stdlib only (no external deps).

Config resolution (first match wins):
1. {project_root}/.claude/channels/telegram/  (project-specific)
2. ~/.claude/channels/telegram/               (user-level fallback)

Required files in config dir:
- .env: contains TELEGRAM_BOT_TOKEN=...
- access.json: contains allowFrom list with chat IDs

Failure model: network-family exceptions during send are caught and
translated into a structured :class:`~macf.observability.Warning`. The
helper returns a :class:`NotifyResult` whose ``__bool__`` preserves the
``True``/``False`` semantics existing callers depend on, while
``result.warning`` carries the structured diagnostic for hooks that want
to emit it via :func:`macf.observability.emit_warning`.
"""

import io
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from ..observability import Warning, emit_warning


# Network exception family that maps to recoverable / user-actionable
# warnings. Anything outside this family is a logic error and is allowed
# to propagate so the caller's exception handler sees it as a real bug.
NETWORK_EXCEPTIONS = (
    urllib.error.URLError,
    ssl.SSLError,
    OSError,
    TimeoutError,
)


@dataclass(frozen=True)
class NotifyResult:
    """Return type for :func:`send_telegram_notification`.

    Attributes:
        success: True if the message was delivered (or no network attempt
            was made because Telegram is not configured — see note below).
        warning: Structured :class:`Warning` when a network failure
            translated cleanly; ``None`` otherwise. Existence of a
            ``warning`` implies ``success is False``, but ``success is
            False`` does NOT imply a warning (e.g. Telegram not
            configured produces ``success=False, warning=None`` for
            backward compatibility with the previous ``bool`` API).

    Truthiness mirrors ``success`` so existing callers that did
    ``if send_telegram_notification(...)`` continue to work unchanged.
    """

    success: bool
    warning: Optional[Warning] = None

    def __bool__(self) -> bool:  # noqa: D401
        return self.success


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
        emit_warning(Warning(source="telegram", kind="config_discovery_failed", detail=f"telegram config discovery failed at project level: {e}"))

    # Tier 2: User-level fallback
    user_dir = Path.home() / '.claude' / 'channels' / 'telegram'
    token = _read_token(user_dir)
    chat_id = _read_chat_id(user_dir)
    if token and chat_id:
        return (token, chat_id)

    return None


def _classify_network_exception(e: BaseException) -> Tuple[str, str, str]:
    """Classify a network exception into (kind, likely_cause, user_remediation).

    Falls back to a generic ``"network_error"`` kind when the exception
    doesn't match a more specific case.
    """
    # HTTPError is the most informative — has .code with HTTP status.
    if isinstance(e, urllib.error.HTTPError):
        code = e.code
        if code == 401:
            return (
                "auth_failed",
                "bot token rejected by Telegram API",
                "verify TELEGRAM_BOT_TOKEN in .env and that the bot is not revoked",
            )
        if code == 403:
            return (
                "forbidden",
                "bot was blocked by the chat or kicked from the group",
                "re-add the bot to the chat or check chat_id in access.json",
            )
        if 500 <= code < 600:
            return (
                "telegram_api_5xx",
                f"Telegram API returned HTTP {code}",
                "transient server-side issue — retry later; check api.telegram.org status",
            )
        return (
            f"http_{code}",
            f"unexpected HTTP {code} from Telegram API",
            "inspect the response body for details",
        )

    if isinstance(e, ssl.SSLError):
        return (
            "ssl_handshake_failed",
            "TLS handshake to api.telegram.org failed",
            "check system trust store, proxy interception, or network filtering",
        )

    if isinstance(e, TimeoutError):
        return (
            "request_timeout",
            "request to api.telegram.org timed out",
            "network is slow or unreachable — retry; check connectivity",
        )

    if isinstance(e, urllib.error.URLError):
        # Bare URLError (DNS failure, connection refused, etc.)
        reason = getattr(e, "reason", e)
        return (
            "api_unreachable",
            f"could not reach api.telegram.org ({reason})",
            "check internet connectivity and DNS",
        )

    # Generic OSError fallback (broken pipe, network down, etc.)
    return (
        "network_error",
        type(e).__name__,
        "transient network issue — retry; check connectivity",
    )


def _build_network_warning(e: BaseException, page: int, total: int) -> Warning:
    """Translate a caught network exception into a structured Warning."""
    kind, likely_cause, user_remediation = _classify_network_exception(e)
    page_tag = f" (page {page}/{total})" if total > 1 else ""
    return Warning(
        source="telegram",
        kind=kind,
        detail=f"{type(e).__name__}: {e}{page_tag}",
        likely_cause=likely_cause,
        user_remediation=user_remediation,
    )


def send_telegram_notification(text: str, prefix: str = "",
                               page_size: int = 4000,
                               parse_mode: Optional[str] = None) -> NotifyResult:
    """Send a message to the configured Telegram chat, paginating if needed.

    Long messages are split into multiple pages. When paginated, the prefix
    is augmented with (page/total) on each message. On the first network
    failure the function bails — subsequent pages are skipped and the
    structured warning for the failed page is returned.

    Args:
        text: Message body text.
        prefix: Optional prefix line (e.g. emoji + "Agent stopped").
            Placed before body on each page.
        page_size: Max chars per Telegram message (API limit 4096, default
            4000 for safety).
        parse_mode: Optional Telegram parse mode ("HTML" or "MarkdownV2").
            Default None sends plain text. When using HTML, caller must
            escape content with _html_escape().

    Returns:
        :class:`NotifyResult`. ``result.success`` mirrors the original
        ``bool`` semantics (``if send_telegram_notification(...):`` still
        works via ``__bool__``). ``result.warning`` carries the structured
        diagnostic when delivery fails on a recognized network exception
        — callers should merge it into their hook return dict via
        ``return {**emit_warning(result.warning), ...}``.
    """
    config = resolve_telegram_config()
    if not config:
        # Not-configured is neither success nor a warning — it's an
        # absence. Preserve the historical "silently False" behavior for
        # callers that treat Telegram as opt-in.
        return NotifyResult(success=False)

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
        except NETWORK_EXCEPTIONS as e:
            return NotifyResult(
                success=False,
                warning=_build_network_warning(e, page=i, total=total),
            )

    return NotifyResult(success=True)


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
    except NETWORK_EXCEPTIONS as e:
        emit_warning(Warning(
            source="telegram",
            kind="document_send_failed",
            detail=f"Telegram document send failed: {e}",
            likely_cause=_classify_network_exception(e)[1],
            user_remediation=_classify_network_exception(e)[2],
        ))
        return False
