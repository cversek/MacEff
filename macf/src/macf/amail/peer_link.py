"""Rung 2 of the delivery ladder: a broker hands mail to a peer broker over a private network.

The sender connects to the receiver's listener and sends one request line; the receiver
checks who is calling before it reads, reads only up to a bound, writes the pair into its
own peer intake, and answers only then (MIS-0004 R56 to R64). From the intake the pair
takes the path a rung 1s pair does: the receiver's contacts, its keys, its quarantine, its
audit, its hand-off into the agent's box.

The protocol is one JSON line each way:

    request  {"v": 1, "op": "hand_off", "from": <sender's domain>, "stem": ..., "sidecar": {...},
              "payload_b64": ...}
             {"v": 1, "op": "ping", "from": <sender's domain>}
    reply    {"v": 1, "ok": true, "message_id": ...}
             {"v": 1, "ok": true, "op": "ping", "domain": ..., "you_are": ..., "build": ...,
              "protocol": 1, "your_agents": {...}, "your_keys_declared": {card: true|false|null}}
             {"v": 1, "ok": false, "refused": true, "reason": ...}     the peer will not take it
             {"v": 1, "ok": false, "reason": ...}                      it could not be stored; retry
"""
from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import socket
import sys
import threading
import time

from .broker import PairRefused
from typing import Any, Dict, Optional, Tuple

PROTOCOL_VERSION = 1
#: The requests a listener answers. ``ping`` is additive within version 1: a peer whose build has
#: no ping refuses it as unknown, which `amail peer check` reports as an older build.
OPS = ("hand_off", "ping")
#: The most one request line may hold. Reading stops here, before anything is parsed, so no
#: caller can make the broker hold more however long it keeps sending (R62).
MAX_REQUEST_BYTES = 16 * 1024 * 1024
#: How long a connection may take to deliver its request, and the sender to wait for a reply.
CONNECTION_TIMEOUT_S = 15.0
#: The most time one request may take to arrive in full, however it dribbles in (R65). A bound on
#: the bytes alone lets a slow sender hold a connection, and so a slot, for as long as it likes.
REQUEST_DEADLINE_S = 30.0
#: Connections the listener serves at once; past it a new one is closed unread.
MAX_CONNECTIONS = 16

#: Spellings of "every interface": a peer listener never binds one (R58).
_EVERY_INTERFACE = {"", "0.0.0.0", "::", "0:0:0:0:0:0:0:0"}


class RequestTooLarge(Exception):
    """A request line ran past its bound without ending."""


class RequestTimedOut(Exception):
    """A request did not arrive in full within its deadline."""


class ClosedUnread(ConnectionError):
    """The peer accepted the connection and closed it with no reply, which is what a listener does
    to an address it does not declare (R59); a ConnectionError, so a sender keeps its copy."""


class Deferred(Exception):
    """The peer did not acknowledge: it is down, slow, or could not store the pair. The sender
    keeps its copy and tries again."""


def read_request_line(conn, limit: Optional[int] = None, deadline_s: Optional[float] = None) -> bytes:
    """One line from *conn*, read up to its newline, or RequestTooLarge at the bound, or
    RequestTimedOut when the whole line has not arrived within the deadline.

    Collected in place, so reading a line of n bytes takes time proportional to n; joining
    bytes on every chunk copies the buffer each time and made an 80 MB line take 109 seconds
    where this takes milliseconds."""
    bound = MAX_REQUEST_BYTES if limit is None else limit
    deadline = time.monotonic() + (REQUEST_DEADLINE_S if deadline_s is None else deadline_s)
    data = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RequestTimedOut(f"the request did not arrive in full within {REQUEST_DEADLINE_S if deadline_s is None else deadline_s:g} seconds")
        if hasattr(conn, "settimeout"):
            conn.settimeout(remaining)
        try:
            chunk = conn.recv(4096)
        except socket.timeout as e:
            raise RequestTimedOut("the request stopped arriving before its deadline") from e
        if not chunk:
            break
        data += chunk
        if len(data) > bound:
            raise RequestTooLarge(f"the request is over {bound} bytes")
        if b"\n" in chunk:
            break
    return bytes(data)


def _reply(ok: bool, **fields: Any) -> bytes:
    return json.dumps({"v": PROTOCOL_VERSION, "ok": ok, **fields}).encode("utf-8") + b"\n"


class PeerListener:
    """The receiving half: a listener bound to one declared private address.

    ``broker`` supplies the declared peers (``config.peer_links``) and ``take_over_link``,
    which stores a pair and says whether it did. The listener decides nothing about mail.
    """

    def __init__(self, broker, host: str, port: int):
        if str(host).strip() in _EVERY_INTERFACE:
            raise ValueError("a peer listener binds the one private address the operator declares, "
                             "never every interface (MIS-0004 R58)")
        try:
            address = ipaddress.ip_address(host)
        except ValueError as e:
            raise ValueError(f"a peer listener binds an address, not a name: {host!r}") from e
        if address.is_unspecified:           # every spelling of "every interface", not only the usual ones
            raise ValueError("a peer listener binds the one private address the operator declares, "
                             "never every interface (MIS-0004 R58)")
        self.broker = broker
        self.host, self.requested_port = host, port
        self.port: int = port
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)

    @property
    def address(self) -> Tuple[str, int]:
        return (self.host, self.port)

    def start(self) -> "PeerListener":
        if not self.broker.config.peer_links:
            raise ValueError("this broker declares no peer link, so its listener would accept none "
                             "(MIS-0004 R57)")
        sock = socket.socket(socket.AF_INET6 if ":" in self.host else socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.requested_port))
        sock.listen(MAX_CONNECTIONS)
        sock.settimeout(0.5)
        self._sock, self.port = sock, sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, name="amail-peer-listener", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            self._sock.close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:   # noqa: S112 - the accept loop wakes twice a second to see whether it should stop
                continue
            except OSError:
                break
            if not self._slots.acquire(blocking=False):
                conn.close()
                continue
            threading.Thread(target=self._handle, args=(conn, addr[0]), daemon=True).start()

    def _declared_domain(self, source: str) -> Optional[str]:
        """The peer domain whose declared address is *source*, or None."""
        for domain, link in self.broker.config.peer_links.items():
            try:
                if ipaddress.ip_address(link.host) == ipaddress.ip_address(source):
                    return domain
            except ValueError:   # noqa: S112 - an unparseable declared host matches nothing, and is refused at config load
                continue
        return None

    def _handle(self, conn: socket.socket, source: str) -> None:
        try:
            conn.settimeout(CONNECTION_TIMEOUT_S)
            domain = self._declared_domain(source)
            if domain is None:
                self._audit(f"closed unread: {source} is no declared peer")
                return                               # R59: closed before a byte is read
            try:
                raw = read_request_line(conn, limit=MAX_REQUEST_BYTES)
            except RequestTooLarge as e:
                conn.sendall(_reply(False, refused=True, reason=f"{e} (the bound is {MAX_REQUEST_BYTES})"))
                self._audit(f"{domain}: {e}")
                return
            except RequestTimedOut as e:
                conn.sendall(_reply(False, refused=True, reason=str(e)))
                self._audit(f"{domain}: {e}")
                return
            conn.sendall(self._answer(domain, raw))
        except OSError as e:
            print(f"⚠️ MACF: amail peer link: a connection from {source} failed: {e}", file=sys.stderr)
        finally:
            self._slots.release()
            try:
                conn.close()
            except OSError as e:
                print(f"⚠️ MACF: amail peer link: closing a connection failed: {e}", file=sys.stderr)

    def _answer(self, domain: str, raw: bytes) -> bytes:
        try:
            request = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return _reply(False, refused=True, reason="the request is not JSON")
        if not isinstance(request, dict) or request.get("v") != PROTOCOL_VERSION or request.get("op") not in OPS:
            return _reply(False, refused=True, reason=f"unknown request; this broker speaks version {PROTOCOL_VERSION}")
        if str(request.get("from", "")).lower() != domain.lower():
            return _reply(False, refused=True,
                          reason="the request says it is from another domain than the declared peer at this address")
        if request["op"] == "ping":
            return _reply(True, **self._ping(domain))
        try:
            payload = base64.b64decode(request.get("payload_b64", ""), validate=True)
        except (binascii.Error, ValueError):
            return _reply(False, refused=True, reason="the payload is not base64")
        try:
            result = self.broker.take_over_link(domain, str(request.get("stem", "")),
                                                request.get("sidecar"), payload)
        except PairRefused as e:
            self._audit(f"{domain}: refused a pair: {e}")
            return _reply(False, refused=True, reason=str(e))
        except Exception as e:  # noqa: BLE001 - whatever failed, the sender keeps its copy and the reason goes in the audit
            self._audit(f"{domain}: could not store a pair: {type(e).__name__}: {e}")
            return _reply(False, reason=f"the peer could not store it ({type(e).__name__})")
        return _reply(True, **result)

    def _ping(self, domain: str) -> Dict[str, Any]:
        """What a declared peer needs to check its link to this broker: who this broker is, which
        domain it sees at the caller's address, its build, the agents it declares for the caller, and
        whether its registry holds a key for each of their cards. A message from one of those agents
        reads attested here exactly when its card is declared and its key is (MIS-0004 R44, R63).
        Nothing in it is a secret, and only a declared peer is ever answered."""
        from macf import __version__
        from .registry import RegistryError
        link = self.broker.config.peer_links[domain]
        keys: Dict[str, Any] = {}
        registry = getattr(self.broker, "registry", None)
        for card in sorted(set(link.agents.values())):
            try:
                keys[card] = bool(registry.signing_keys(card)) if registry is not None else None
            except RegistryError as e:
                print(f"⚠️ MACF: amail peer link: ping could not read the registry (reporting unknown): {e}",
                      file=sys.stderr)
                keys[card] = None
        return {"op": "ping", "domain": self.broker.config.domain, "you_are": domain, "build": __version__,
                "protocol": PROTOCOL_VERSION, "your_agents": dict(link.agents), "your_keys_declared": keys}

    def _audit(self, detail: str) -> None:
        audit = getattr(self.broker, "audit", None)
        if audit:
            audit.error(context="peer-link", detail=detail)


def send_request(host: str, port: int, request: Dict[str, Any],
                 timeout: float = CONNECTION_TIMEOUT_S) -> Dict[str, Any]:
    """Send one request to a peer's listener and return its reply.

    Raises ConnectionError for anything that is not a well-formed reply, so a caller treats a
    peer that is down, slow or speaking nonsense the same way: the message is kept."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as e:
        raise ConnectionError(f"the peer at {host}:{port} could not be reached: {e}") from e
    try:
        with sock:
            sock.settimeout(timeout)
            sock.sendall(json.dumps({"v": PROTOCOL_VERSION, **request}).encode("utf-8") + b"\n")
            raw = read_request_line(sock)
    except (RequestTooLarge, RequestTimedOut) as e:
        raise ConnectionError(f"the peer's reply was not usable: {e}") from e
    except (ConnectionResetError, BrokenPipeError) as e:
        # Connected, then closed before any reply: a listener closing an undeclared address unread
        # (R59) is seen as a reset or as an empty read, depending on timing.
        raise ClosedUnread(f"the peer at {host}:{port} closed the connection without a reply ({e})") from e
    except OSError as e:
        raise ConnectionError(f"the connection to the peer at {host}:{port} failed: {e}") from e
    if not raw:
        raise ClosedUnread(f"the peer at {host}:{port} closed the connection without a reply")
    try:
        reply = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise ConnectionError("the peer sent a reply that is not JSON") from e
    if not isinstance(reply, dict):
        raise ConnectionError("the peer sent a reply that is not an object")
    return reply
