"""Whether the session's context holds untrusted input (the scheduler design, 5.3).

Taint follows the context, not the turn: what was read in one turn is still in context for the
next, so it runs from the session's start or its last compaction, whichever is later. It's
derived from the session's own tool events in the event log, never from the agent's word.

**It is a heuristic, and is meant to be read as one.** A Bash call can fetch without naming a
host, and nothing in the tool events can prove it didn't. What it counts as untrusted:
- a web fetch or search;
- a tool that reads GitHub or mail, or fetches a channel's attachment;
- a Bash call that names a URL or a host, or runs a client that reads one (``gh``, ``curl``,
  ``ssh``, ``amail`` and the like);
- a message that arrived by a channel, Telegram included. The MacEff channel is the exception:
  its notices are fixed words with an opaque id, which no sender chooses.

It fails closed: a log with no session start or compaction to bound the scan reads tainted.
Pure over the events it's given, newest first; nothing here reads the log or a clock.

**Each session is read back to its own boundary.** An agent's log can hold more than one
session: a fork, a resume, a second terminal. The daemon can't name the asking session without
taking the agent's word for it, so it reads them all, each back to its own start or compaction.
Another session's boundary doesn't end the scan, and another session's untrusted input marks the
entry too: an over-count, failing closed like everything else here.
"""
import re
from typing import Iterable, List

#: The events that begin a context: before the later of these, nothing is still in it.
BOUNDARIES = ("session_started", "compaction_detected")

_WEB_TOOLS = ("WebFetch", "WebSearch")
_READING_TOOL = re.compile(r"^mcp__.*(github|gmail|mail|download_attachment|fetch)", re.IGNORECASE)
_NAMES_A_HOST = re.compile(
    r"https?://"
    r"|\b(gh|curl|wget|ssh|scp|rsync|sftp|nc|telnet|amail)\b"
    r"|\bgit\b[^|;&\n]*\s(fetch|pull|clone|ls-remote)\b"
    r"|\b[a-z0-9-]+(\.[a-z0-9-]+)*\.(com|org|net|io|dev|ai|app|local)\b",
    re.IGNORECASE)
_CHANNEL = re.compile(r'^\s*<channel source="([^"]+)"')
_OWN_CHANNEL = "plugin:maceff-channel:maceff"


def _why(event: dict) -> str:
    """What made this one event untrusted input, or "" when nothing did."""
    kind, data = event.get("event"), event.get("data") or {}
    if kind == "tool_call_started":
        tool = data.get("tool") or ""
        if tool in _WEB_TOOLS:
            return "a web fetch"
        if _READING_TOOL.match(tool):
            return f"a read by {tool}"
        if tool == "Bash":
            command = ((event.get("hook_input") or {}).get("tool_input") or {}).get("command") or ""
            if _NAMES_A_HOST.search(command):
                return "a Bash call that names a host"
    elif kind == "dev_drv_started":
        channel = _CHANNEL.match(data.get("prompt_preview") or "")
        if channel and channel.group(1) != _OWN_CHANNEL:
            return f"a message by {channel.group(1)}"
    return ""


def taint(events_newest_first: Iterable[dict]) -> List[str]:
    """Why the current context holds untrusted input, each kind once, newest first; empty when
    it holds none. Reads each session back to its own context boundary, and stops once every
    session it has seen is bounded. A boundary that names no session bounds them all."""
    reasons: List[str] = []
    seen: set = set()
    bounded: set = set()
    for event in events_newest_first:
        session = (event.get("data") or {}).get("session_id") or ""
        if event.get("event") in BOUNDARIES:
            if not session:
                return reasons
            bounded.add(session)
            if seen <= bounded:
                return reasons
            continue
        if session in bounded:
            continue
        if session:
            seen.add(session)
        why = _why(event)
        if why and why not in reasons:
            reasons.append(why)
    return reasons or ["no session start or compaction bounds the context, so it can't be shown clean"]
