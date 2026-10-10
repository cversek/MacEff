"""Who is on the other end of a local socket, as the kernel recorded it.

One implementation for every component that authenticates a local peer: the mail
broker identifies submitters by it, and the MacEff channel checks that the process
it connected to is its own primal daemon. Two components reading peer credentials
two ways would eventually disagree about who is calling, which is the one question
neither may get wrong.

Linux supplies SO_PEERCRED (pid, uid, gid). macOS and the BSDs supply
LOCAL_PEERCRED (a ``struct xucred``, which carries no pid) and LOCAL_PEERPID. All of
them are set by the kernel at connect time and none can be influenced by the peer.
Any other platform raises, and every caller fails closed.
"""
import socket
import struct
import sys
from typing import NamedTuple

#: Usable bytes of ``sun_path``: the array is 104 on macOS/BSD and 108 on Linux,
#: and the last byte is the terminator. A path one byte too long fails at bind or
#: connect with a message that does not mention length, so check before either.
SUN_PATH_MAX = 103 if (sys.platform == "darwin" or sys.platform.endswith("bsd")) else 107

# macOS / BSD constants, absent from Python's socket module on every platform.
_SOL_LOCAL = 0
_LOCAL_PEERCRED = 0x0001
_LOCAL_PEERPID = 0x0002
_XUCRED_SIZE = 76
_XUCRED_VERSION = 0


class PeerCredentials(NamedTuple):
    pid: int
    uid: int


def _is_bsd_like() -> bool:
    return sys.platform == "darwin" or sys.platform.endswith("bsd")


def peer_credentials(conn: socket.socket) -> PeerCredentials:
    """The pid and uid the kernel recorded for the connected peer.

    Works on either end of a connected AF_UNIX stream socket: an accepting server
    learns its client, and a connecting client learns the server that accepted it.
    Raises OSError where the platform offers no kernel source.
    """
    if hasattr(socket, "SO_PEERCRED"):
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3I"))
        # ucred fields are unsigned; reading them signed turns a high uid negative.
        pid, uid, _gid = struct.unpack("3I", raw)
        return PeerCredentials(pid=pid, uid=uid)
    if _is_bsd_like():
        raw = conn.getsockopt(_SOL_LOCAL, _LOCAL_PEERCRED, _XUCRED_SIZE)
        version, uid = struct.unpack_from("II", raw)
        if version != _XUCRED_VERSION:
            raise OSError(f"unexpected xucred version {version} from LOCAL_PEERCRED")
        pid = struct.unpack("i", conn.getsockopt(_SOL_LOCAL, _LOCAL_PEERPID, 4))[0]
        return PeerCredentials(pid=pid, uid=uid)
    raise OSError(f"no kernel peer-credential source on {sys.platform}")


def peer_uid(conn: socket.socket) -> int:
    """The connected peer's uid. See ``peer_credentials``."""
    return peer_credentials(conn).uid
