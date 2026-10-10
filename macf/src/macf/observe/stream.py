"""The observation stream: what an admitted onlooker sees, from the invitation on, and
nothing it can type.

MIS-0002-R84 (stream_MUST_start_at_invitation): the stream reads the transcript from the
byte offset recorded with the invitation, so nothing from before it can appear.
MIS-0002-R85 (stream_MUST_stop_at_end): the observation's state is read before every
send, so an ending, or a lease that runs out, stops the stream before the next frame.
MIS-0002-R93 (onlooker_MUST_see_pause): while paused, the onlooker gets one frame saying
the owner paused it, and nothing else until the owner resumes.
MIS-0002-R83 (onlooker_MUST-NOT_type): after the one line that admits it, the stream
never reads from the onlooker again. There is no input path to close.

What a person would see. A frame carries what someone watching the terminal sees, and
less where the more would be data the onlooker was not invited to: a typed prompt, a
channel message's text with its source (never the chat's identifiers), the agent's own
text, and each tool call by name with its stated purpose. A tool's result is a marker
saying whether it failed, never its body; the agent's thinking, hook output, skill text,
peer messages and the client's housekeeping rows are not sent at all.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Dict, Iterator, Optional, Tuple

from .acts import ACTIVE, ENDED, PAUSED, Observation, admit, lapsed

#: The handshake is one short line; anything longer is refused unread.
MAX_HANDSHAKE = 4096

_CHANNEL_TAG = re.compile(r'^<channel\s+source="([^"]+)"[^>]*>(.*)</channel>\s*$', re.S)


def _tool_purpose(block: dict) -> str:
    """The one line a tool call shows: its stated description, else nothing."""
    args = block.get("input") or {}
    if isinstance(args, dict) and isinstance(args.get("description"), str):
        return args["description"][:200]
    return ""


def visible(entry: dict) -> list:
    """The frames a transcript row becomes for an onlooker; often none."""
    kind = entry.get("type")
    message = entry.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    ts = entry.get("timestamp", "")
    if kind == "user":
        origin = entry.get("origin") or {}
        if isinstance(content, list):
            results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
            if results:
                return [{"t": ts, "kind": "result", "failed": bool(b.get("is_error"))} for b in results]
            if any(isinstance(b, dict) and "[Request interrupted" in str(b.get("text", "")) for b in content):
                return [{"t": ts, "kind": "interrupted"}]
            return []
        if not isinstance(content, str):
            return []
        if origin.get("kind") == "human" and not entry.get("isMeta"):
            return [{"t": ts, "kind": "prompt", "text": content}]
        if origin.get("kind") == "channel":
            m = _CHANNEL_TAG.match(content.strip())
            if m:
                return [{"t": ts, "kind": "channel", "source": m.group(1), "text": m.group(2).strip()}]
            return []
        if content.startswith("This session is being continued from a previous conversation"):
            return [{"t": ts, "kind": "compacted"}]
        return []
    if kind == "assistant" and isinstance(content, list):
        frames = []
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and b.get("text"):
                frames.append({"t": ts, "kind": "agent", "text": b["text"]})
            elif b.get("type") == "tool_use":
                frames.append({"t": ts, "kind": "tool", "name": b.get("name", ""), "purpose": _tool_purpose(b)})
        return frames
    return []


def rows_from(path, offset: int) -> Iterator[Tuple[int, dict]]:
    """Complete transcript rows after byte ``offset``, each with the offset after it.

    A last line without its newline is still being written, so it waits for the next read.
    """
    with open(path, "rb") as fh:
        fh.seek(offset)
        pos = offset
        for raw in fh:
            if not raw.endswith(b"\n"):
                break
            pos += len(raw)
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield pos, row


def handshake(line: bytes, state: Dict[str, Observation], now: float) -> Tuple[Optional[Observation], str]:
    """Admit the onlooker the first line names, with the secret it presents, or say why not."""
    if len(line) > MAX_HANDSHAKE:
        return None, "handshake too long"
    try:
        hello = json.loads(line)
        card, secret = hello["onlooker"], hello["secret"]
    except (ValueError, KeyError, TypeError):
        return None, "handshake must be {\"onlooker\": <card>, \"secret\": <secret>}"
    o = admit(card, secret, state, now=now)
    return (o, "") if o is not None else (None, "not admitted")


def serve(send: Callable[[dict], None], onlooker: str, read_state: Callable[[], Dict[str, Observation]],
          read_rows: Callable[[int], Iterator[Tuple[int, dict]]], now: Callable[[], float],
          wait: Callable[[], None], start: int, rounds: Optional[int] = None) -> str:
    """Send frames to one admitted onlooker until its observation ends. Returns why it stopped.

    Takes no input from the onlooker: ``send`` is its only contact. The state is read
    again before every frame, so an end or a lapsed lease stops the stream at once.
    """
    offset = start
    paused_said = False
    n = 0
    while rounds is None or n < rounds:
        n += 1
        o = read_state().get(onlooker)
        if o is None or o.status == ENDED or lapsed(o, now()):
            send({"kind": "ended"})
            return "ended"
        if o.status == PAUSED:
            if not paused_said:
                send({"kind": "paused", "by": "the observed agent"})
                paused_said = True
            wait()
            continue
        if paused_said:
            send({"kind": "resumed"})
            paused_said = False
        for nxt, row in read_rows(offset):
            o = read_state().get(onlooker)
            if o is None or o.status != ACTIVE or lapsed(o, now()):
                break
            for frame in visible(row):
                send(frame)
            offset = nxt
        wait()
    return "rounds"


def serve_connection(sock, state_reader, rows, clock, wait, poll_rounds=None) -> str:
    """One onlooker on one socket: read the handshake line, then only write.

    The socket is never read again after the handshake (R83). Refusals say why and close.
    """
    data = b""
    while not data.endswith(b"\n") and len(data) <= MAX_HANDSHAKE:
        chunk = sock.recv(512)
        if not chunk:
            break
        data += chunk
    o, why = handshake(data.strip(), state_reader(), clock())
    if o is None:
        sock.sendall(json.dumps({"kind": "refused", "reason": why}).encode() + b"\n")
        return why

    def send(frame):
        sock.sendall(json.dumps(frame).encode() + b"\n")

    return serve(send, o.onlooker, state_reader, rows, clock, wait, o.stream_from, poll_rounds)
