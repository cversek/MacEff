"""Each daemon's own MQTT broker: its configuration and access rules, rendered from the declaration.

PROTOTYPE (mission B, phase B2). Every daemon runs its own broker as a unit, and its stream lives
there. This module renders what that broker runs with; it starts nothing.

WHY EXPLICIT USER LINES. mosquitto's ``pattern`` rules "apply to all users", so a pattern would
admit any certificate the CA ever issued. Each certificate the declaration names gets its own
``user`` block instead, and a certificate it doesn't name can connect but reads and writes nothing.

WHY THE CERTIFICATE'S NAME IS THE CARD LOWERCASED. With ``use_identity_as_username`` the
certificate's Common Name is the user the rules name. Several system daemons share the account
``maceff_system``, so the account can't identify a daemon; the card can, and a certificate name
takes it lowercased (MIS-0002-R161).

WHAT EACH CERTIFICATE MAY DO.
- The daemon itself: ``readwrite <card>/#``, its own stream and status.
- An association daemon: ``read members/#``.
- Each declared member: ``write members/<member card>/#`` and nothing else, so it can't write as
  a sibling or read one.
- Each granted reader: ``read <card>/events/<source>`` for each source granted.
"""
from typing import Dict, Iterable, List, Optional, Sequence

from macf import calling_card

LISTEN = {"loopback": "127.0.0.1"}


class BrokerRefused(ValueError):
    """A broker declaration that can't be rendered, with the reason."""


def cert_name(card: str) -> str:
    """The Common Name a daemon's certificate carries: its card lowercased."""
    calling_card.split(card)          # refuses anything that isn't a card
    return calling_card.lowercase(card)


def source_topic(card: str, source: str) -> str:
    """The topic a source's events publish on: its name split on ``_`` into levels, so a family
    of sources is one filter (``pd_entry_due`` -> ``<card>/events/pd/entry/due``)."""
    if not source or any(c in source for c in "#+/") or source.startswith("_") or "__" in source:
        raise BrokerRefused(f"not a source name: {source!r}")
    return f"{card}/events/" + source.replace("_", "/")


def grant_filters(card: str, grant: str, known: Iterable[str]) -> List[str]:
    """The topic filters a granted source or glob becomes. A glob ending ``_*`` on a level boundary
    is one ``#`` filter; any other glob is expanded against the sources the code defines, since
    MQTT filters match whole levels only."""
    import fnmatch
    if not any(c in grant for c in "*?["):
        return [source_topic(card, grant)]
    prefix = grant[:-2]
    if grant.endswith("_*") and prefix and not any(c in prefix for c in "*?["):
        return [source_topic(card, prefix) + "/#"]
    return sorted(source_topic(card, s) for s in set(known) if fnmatch.fnmatchcase(s, grant))


class GapTracker:
    """A subscriber's view of gaps (R154). Each message carries its log position and the position
    of the previous record of the same source; a subscriber that filters by source sees global
    positions skip by design, so it compares per source."""

    def __init__(self) -> None:
        self.last: Dict[str, int] = {}

    def observe(self, source: str, position: int, previous: Optional[int]) -> bool:
        """Record a message; True when records of this source were missed before it."""
        seen = self.last.get(source)
        self.last[source] = position
        return seen is not None and previous != seen


def render_acl(card: str, *, members: Sequence[str] = (), association: bool = False,
               readers: Optional[Dict[str, Iterable[str]]] = None,
               known_sources: Iterable[str] = ()) -> str:
    """The broker's access rules: one ``user`` block per certificate the declaration names."""
    if members and not association:
        raise BrokerRefused("only an association admits members")
    blocks: List[str] = [f"user {cert_name(card)}\ntopic readwrite {card}/#"]
    if association:
        blocks[0] += "\ntopic read members/#"
    for member in members:
        blocks.append(f"user {cert_name(member)}\ntopic write members/{member}/#")
    for reader, sources in sorted((readers or {}).items()):
        lines = [f"user {cert_name(reader)}"]
        filters = sorted({f for s in sources for f in grant_filters(card, s, known_sources)})
        lines += [f"topic read {f}" for f in filters]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def render_conf(*, port: int, listen: str, cafile: str, certfile: str, keyfile: str,
                acl_file: str, association: bool = False, crlfile: Optional[str] = None,
                lan_address: Optional[str] = None) -> str:
    """mosquitto.conf for one daemon's broker: one TLS listener, certificates required, the
    certificate's name as the user, and the rendered access rules."""
    if not 1024 <= port <= 65535:
        raise BrokerRefused(f"the broker's port must be 1024 to 65535, not {port}")
    if listen == "lan":
        if not association:
            raise BrokerRefused("only an association listens on the LAN; a daemon's own broker "
                                "listens on loopback")
        if not lan_address:
            raise BrokerRefused("a LAN listener names the address it binds")
        bind = lan_address
    elif listen in LISTEN:
        bind = LISTEN[listen]
    else:
        raise BrokerRefused(f"listen is loopback or lan, not {listen!r}")
    lines = [
        "per_listener_settings false",
        "allow_anonymous false",
        f"listener {port} {bind}",
        f"cafile {cafile}",
        f"certfile {certfile}",
        f"keyfile {keyfile}",
        "require_certificate true",
        "use_identity_as_username true",
        f"acl_file {acl_file}",
    ]
    if crlfile:
        lines.append(f"crlfile {crlfile}")
    return "\n".join(lines) + "\n"
