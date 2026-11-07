"""Zone addresses (MIS-0004 R06): an agent's address under the shared mail zone.

The local part is the calling card from the agent's home and the first six characters of its
identity file, ``name_shortid``, lower-cased: ``RustyTrombone@15b944`` is
``rustytrombone_15b944@<zone>``. It is read only from the home (``pd.names.agent_card``), never from
``MACEFF_AGENT_NAME``, because a seat may set that variable to its short name, and an address taken
from it would name a mailbox no broker holds. The zone itself comes from deployment configuration and
never appears in this repository.
"""
from pathlib import Path

from ..pd.names import agent_card


def zone_local_part(home: Path) -> str:
    """``name_shortid`` for the agent whose home is *home*; IdentityError when the home names none."""
    name, _, shortid = agent_card(Path(home)).partition("@")  # noqa: MACEFF005 - agent_card returns "Name@shortid", fixed in pd.names
    return f"{name}_{shortid}".lower()


def zone_address(home: Path, zone: str) -> str:
    """The agent's full address under *zone*."""
    return f"{zone_local_part(home)}@{zone.strip().lower()}"
