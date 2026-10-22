"""A notice receiver that is the real delivery path, for the tests of the daemon's notice
producers (#734).

A test that hands a producer's notice to a stand-in receiver proves the producer called it,
not that the notice arrives. The scheduler's two notices passed such tests while the MacEff
channel refused every record they made, because their ids carried a ``+``. This receiver owes
each notice through a real ``Notifier``, writes it to a socket, and reads it back through the
channel's own ``parse_record``. A notice the channel would refuse never reaches ``received``,
and the call returns False, as the daemon's ``raise_notice`` does for a notice it doesn't owe.
"""
from __future__ import annotations

import socket
from pathlib import Path
from typing import List, Tuple

from macf.channels.maceff_channel import TAKES, parse_record
from macf.pd import notifier as nt


class ChannelReceiver:
    """Pass it as a producer's ``on_notice``. ``received`` holds each (source, id) the channel
    parsed, in order."""

    def __init__(self, home: Path):
        self._notifier = nt.Notifier(Path(home), {source: "agent" for source in nt.INTERNAL_SOURCES},
                                     append=lambda event, data: True, events=lambda: [])
        self._ours, self._theirs = socket.socketpair()
        self._theirs.settimeout(2)
        self._notifier.attach(self._ours, takes=TAKES)
        self.received: List[Tuple[str, str]] = []

    def __call__(self, source: str, notice_id: str) -> bool:
        if not self._notifier.raise_notice(source, notice_id):
            return False
        assert self._notifier.flush() == 1, "an owed notice wasn't written to the channel"
        line = b""
        while not line.endswith(b"\n"):
            chunk = self._theirs.recv(65536)
            assert chunk, "the channel's end closed before the record arrived"
            line += chunk
        record = parse_record(line.decode())
        if record is None:
            return False
        self.received.append((record.source, record.arrival_id))
        return True
