"""Zone addresses (MIS-0004 R06): an agent's address under the shared mail zone.

The local part is the calling card from the agent's identity file, ``name_shortid``, lower-cased:
``WrenTuba_3c9d1e`` is ``wrentuba_3c9d1e@<zone>``. It is never taken from
``MACEFF_AGENT_NAME``, because a seat may set that variable to its short name, and an address built
from it would name a mailbox no broker holds.

Where the broker's account cannot read the home (a container, R05), the card is declared per agent
in the addressing file, written at provisioning from the same identity file. The zone itself comes
from deployment configuration and never appears in this repository.
"""
import re
from pathlib import Path
from typing import Any, Mapping, Optional

from .. import calling_card
from ..pd.names import agent_card


TOKEN_RE = re.compile(r"[0-9a-f]{12,}")


def check_token(token: str) -> str:
    """*token* when it is a zone token: twelve or more lowercase hex characters; ValueError otherwise."""
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise ValueError("a zone token is twelve or more lowercase hex characters")
    return token


#: A zone local part: the lowercased card (``name_shortid``) and then ``_token``.
_ZONE_LOCAL_RE = re.compile(r"^(?P<card>[a-z0-9]+(?:_[a-z0-9]+)*_[0-9a-f]{6})_[0-9a-f]{12,}$")


def redact_address(address: str) -> str:
    """*address* with its zone token masked, for any log line or reason (MIS-0004 R49): the card
    part still says whose address it was, and the token that makes it reachable is never written.
    An address with no token is returned as it is."""
    local, at, domain = str(address).partition("@")
    m = _ZONE_LOCAL_RE.match(local)
    return f"{m.group('card')}_<token>{at}{domain}" if m else str(address)


def card_for_address(address: str, *, domain: Optional[str] = None, zone: Optional[str] = None,
                     agent_cards: Optional[Mapping[str, str]] = None,
                     peers: Optional[Mapping[str, Mapping[str, Any]]] = None) -> Optional[str]:
    """The calling card an address names, or None (MIS-0004 R44). Each rule holds only at the
    domain it belongs to, because an address outside the deployment and its declared peers is
    outside mail and stays unverified: a stranger who picks one of our cards as a local part is
    not using our agent's address, and must not be judged against its keys.

    - Under *zone*: a zone address, ``name_shortid_token``, with its token removed.
    - Under *domain* (this deployment): an agent's name declared in *agent_cards*, since an
      agent's configured name need not be its card (MIS-0002 R161 covers only names derived from
      one), else a local part that is itself a card.
    - Under a declared peer's domain in *peers* (domain -> box -> card, or ``(card, token)``):
      that box's declared card, else a local part that is itself a card.

    The broker resolves the sender once with this and writes the card into the hand-off
    sidecar, so the recipient judges by the same card and never parses an address itself."""
    local, at, dom = str(address or "").strip().rpartition("@")
    if not at or not local:
        return None
    dom, low = dom.strip().lower(), local.lower()
    if zone and dom == zone.strip().lower():
        m = _ZONE_LOCAL_RE.match(low)
        return m.group("card") if m else None
    if domain and dom == domain.strip().lower():
        names = agent_cards or {}
    else:
        declared = {d.strip().lower(): agents for d, agents in (peers or {}).items()}
        if dom not in declared:
            return None
        names = {box: (v[0] if isinstance(v, (tuple, list)) and v else v)
                 for box, v in (declared[dom] or {}).items()}
    named = {str(n).lower(): str(c) for n, c in names.items() if c}
    if low in named:
        return named[low]
    try:
        return calling_card.read_declared(local)
    except calling_card.CardError:
        return None  # noqa: MACEFF003 - None is the stated answer: the address names no card, so its mail is unverified


def local_part_from_card(card: str, token: Optional[str] = None) -> str:
    """The calling card lowercased, the mail local part MIS-0002-R161 gives it, then ``_token``
    when one is declared; ValueError on a malformed card or token. The token is a random value
    provisioned per agent and never derived from its identity, so an exposed one can be revoked
    and replaced."""
    base = calling_card.lowercase("_".join(calling_card.split(card.strip())))
    return f"{base}_{check_token(token)}" if token is not None else base


def zone_local_part(home: Path) -> str:
    """``name_shortid`` for the agent whose home is *home*; IdentityError when the home names none."""
    return local_part_from_card(agent_card(Path(home)))


def zone_address(home: Path, zone: str) -> str:
    """The agent's full address under *zone*."""
    return f"{zone_local_part(home)}@{zone.strip().lower()}"
