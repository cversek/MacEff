"""Zone addresses (MIS-0004 R06): an agent's address under the shared mail zone.

The local part is the calling card from the agent's identity file, ``name_shortid``, lower-cased:
``WrenTuba@3c9d1e`` is ``wrentuba_3c9d1e@<zone>``. It is never taken from
``MACEFF_AGENT_NAME``, because a seat may set that variable to its short name, and an address built
from it would name a mailbox no broker holds.

Where the broker's account cannot read the home (a container, R05), the card is declared per agent
in the addressing file, written at provisioning from the same identity file. The zone itself comes
from deployment configuration and never appears in this repository.
"""
from pathlib import Path

from ..pd.names import agent_card


def local_part_from_card(card: str) -> str:
    """``name_shortid``, lower-cased, from a calling card ``Name@shortid``; ValueError otherwise."""
    name, sep, shortid = card.strip().partition("@")  # noqa: MACEFF005 - a calling card is "Name@shortid", fixed in pd.names
    if not sep or not name or len(shortid) != 6:
        raise ValueError(f"'{card}' is not a calling card (Name@shortid)")
    return f"{name}_{shortid}".lower()


def zone_local_part(home: Path) -> str:
    """``name_shortid`` for the agent whose home is *home*; IdentityError when the home names none."""
    return local_part_from_card(agent_card(Path(home)))


def zone_address(home: Path, zone: str) -> str:
    """The agent's full address under *zone*."""
    return f"{zone_local_part(home)}@{zone.strip().lower()}"
