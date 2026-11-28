"""The broker socket's protocol version (MIS-0004 R35, broker_socket_MUST_carry_version).

One broker serves seats on different builds of macf, so a change to what the socket says must not
strand the clients still on the old one. Each request carries ``v``, and the broker answers with
its own. A request in a superseded version is still served until the last day its window
declares, with a note saying when it ends; after that it is refused with the versions this broker
speaks, never misread as the current one.

A request with no ``v`` is version 1: every client written before the field existed spoke
version 1, so it keeps working, and it falls under version 1's window like any other once version
1 is superseded.

**How to change the protocol.** Raise ``VERSION`` and add the old number to ``SUPERSEDED`` with
the last day (UTC, ``YYYY-MM-DD``) it is accepted, in the same pull request as the change. An
addition an old client never sends, such as a new operation, is not a change: version 1 grew
``status``, ``contacts`` and ``state`` that way.
"""
from __future__ import annotations

import datetime
from typing import Dict, Optional, Tuple

#: The version this build speaks and answers with.
VERSION = 1

#: Superseded versions still served, each with the last UTC day it is accepted.
SUPERSEDED: Dict[int, str] = {}

#: The version a request with no ``v`` is read as.
UNVERSIONED = 1


def check(requested: object, today: Optional[datetime.date] = None) -> Tuple[bool, str]:
    """``(accepted, note)`` for a request's ``v``.

    Accepted with an empty note in the current version. Accepted with a note naming the window's
    end in a superseded version still inside it. Refused with a reason otherwise: an unknown
    version, a window that has closed, or a ``v`` that is not a whole number.
    """
    if requested is None:
        requested = UNVERSIONED
    if isinstance(requested, bool) or not isinstance(requested, int):
        return False, f"the request's version {requested!r} is not a whole number; {_speaks()}"
    if requested == VERSION:
        return True, ""
    until = SUPERSEDED.get(requested)
    if until is None:
        return False, f"this broker does not speak version {requested}; {_speaks()}"
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    if today.isoformat() <= until:
        return True, (f"version {requested} is superseded by {VERSION} and accepted through {until}; "
                      f"update this client's macf before then")
    return False, f"version {requested} was accepted through {until} and is no longer; {_speaks()}"


def _speaks() -> str:
    older = ", ".join(f"{v} through {d}" for v, d in sorted(SUPERSEDED.items()))
    return f"it speaks version {VERSION}" + (f", and accepts {older}" if older else "")
