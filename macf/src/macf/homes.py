"""Agent homes and new agents: the homes volume's marker, and minting an agent ahead (MIS-0002-R162).

R162 names a new agent's account with its card lowercased. Provisioning can know the card only if
the short id exists before the account does, so a new agent is MINTED AHEAD: ``agent mint`` draws
its short id and zone token, and agents.yaml declares the short id. Start never draws one.

WHY A MARKER. At a container start ``/etc/passwd`` is new and only the persisted home tells an
existing agent from a new one. A homes volume that failed to mount, mounted empty or mounted late
looks exactly like a deployment of new agents, and creating homes there would give every agent a
fresh home, unseen. So a home is created only on a root carrying the marker this module writes.

WHY THE MARKER IS WRITTEN BY A DELIBERATE ACT. A marker that start wrote "at the volume's first use"
would be written on the empty directory a failed mount leaves, and the guard would pass in the one
case it exists for. ``agent homes-init`` writes it; start only reads it.

WHY THE MARKER NAMES ITS VOLUME. A marked volume that is the wrong one (another deployment's homes,
a stale snapshot) would pass a bare marker. The marker holds a random id, agents.yaml declares it
as ``homes_volume``, and start compares the two at every start.
"""
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from macf import calling_card

#: The marker's name in the root of the homes volume.
MARKER = ".maceff_homes"
#: A homes volume's id: sixteen lowercase hexadecimal characters.
VOLUME_ID_RE = re.compile(r"[0-9a-f]{16}")
#: Bytes of randomness in a minted zone token (twice as many hexadecimal characters).
ZONE_TOKEN_BYTES = 12


class HomesRefused(RuntimeError):
    """Start can't use this homes root, or can't create this home; the message says what to do."""


def read_volume(root: Path) -> Optional[str]:
    """The id the marker in *root* holds; None when there is no marker. A marker that holds no
    valid id is refused, since it can't be compared."""
    marker = Path(root) / MARKER
    if not marker.exists():
        return None
    value = marker.read_text().strip()
    if not VOLUME_ID_RE.fullmatch(value):
        raise HomesRefused(f"{marker} holds {value[:40]!r}, not a homes volume id "
                           f"(sixteen lowercase hexadecimal characters)")
    return value


def init_volume(root: Path) -> str:
    """Mark *root* as a deployment's homes volume and return its id. A root already marked keeps
    its id, so running it twice is harmless."""
    root = Path(root)
    existing = read_volume(root)
    if existing is not None:
        return existing
    if not root.is_dir():
        raise HomesRefused(f"{root} is not a directory; mount the homes volume first")
    volume = secrets.token_hex(8)
    marker = root / MARKER
    marker.write_text(volume + "\n")
    marker.chmod(0o444)
    return volume


def check_volume(root: Path, declared: Optional[str]) -> None:
    """Refuse a homes root that isn't the volume agents.yaml declares. Nothing is checked when
    nothing is declared, so a deployment that hasn't run ``homes-init`` keeps starting."""
    if declared is None:
        return
    found = read_volume(root)
    if found is None:
        raise HomesRefused(
            f"agents.yaml declares homes_volume {declared}, but {root} carries no marker: this "
            f"is not the deployment's homes volume. A volume that failed to mount leaves an empty "
            f"directory like this one. Mount the volume and start again")
    if found != declared:
        raise HomesRefused(
            f"agents.yaml declares homes_volume {declared}, but {root} is volume {found}: another "
            f"deployment's homes, or a stale copy. Mount the declared volume, or correct "
            f"homes_volume if this volume is the right one")


def may_create_home(root: Path, home: Path, *, declared: Optional[str], short_id: Optional[str]) -> None:
    """Refuse to create *home* unless the agent was minted ahead and the root is the declared,
    marked volume (MIS-0002-R162)."""
    if short_id is None:
        raise HomesRefused(
            f"{home} does not exist, and its agent declares no short_id. An existing agent's home "
            f"is missing only when the homes volume isn't the one expected, so start won't create "
            f"it. For a new agent, run `macf_tools agent mint <Name>` and declare the short_id it "
            f"prints in agents.yaml")
    if declared is None:
        raise HomesRefused(
            f"{home} does not exist, and agents.yaml declares no homes_volume, so start can't tell "
            f"the deployment's homes volume from an empty mount point. Run "
            f"`macf_tools agent homes-init {root}` on the volume and declare the id it prints as "
            f"homes_volume")
    check_volume(root, declared)


#: The identity file a container agent's home holds: its short id, six hexadecimal characters.
IDENTITY_FILE = ".maceff_primary_agent.id"


def check_identity(home: Path, short_id: str) -> None:
    """Refuse a home whose identity file holds another short id than agents.yaml declares, so an
    edit to the declaration can't relabel a home. A home with no identity file passes."""
    identity = Path(home) / IDENTITY_FILE
    if not identity.exists():
        return
    held = identity.read_text().strip()
    if held != short_id:
        raise HomesRefused(
            f"agents.yaml declares short_id {short_id}, but {identity} holds {held}: the "
            f"declaration names another agent than this home's. Correct short_id, or mount the "
            f"home that belongs to it")


@dataclass(frozen=True, kw_only=True)
class Minted:
    """A new agent's identity, drawn before its account exists."""
    name: str
    short_id: str
    zone_token: str

    @property
    def card(self) -> str:
        return calling_card.build(self.name, self.short_id)

    @property
    def account(self) -> str:
        return calling_card.lowercase(self.card)


def render_minted(minted: Minted, key: str) -> str:
    """What ``agent mint`` prints: the lines agents.yaml and the addressing file take for the new
    agent, so the edge, contacts and apps can be set up before its first start. Every hexadecimal
    value is quoted: YAML reads ``873633`` as an integer and ``0e1234`` as the float 0.0."""
    return (
        f"Minted {minted.card} (account {minted.account})\n"
        f"\n"
        f"agents.yaml, under agents (no username: it is the account above):\n"
        f"  {key}:\n"
        f"    calling_card: {minted.name}\n"
        f"    short_id: \"{minted.short_id}\"\n"
        f"\n"
        f"The addressing file, under agents:\n"
        f"  {minted.account}:\n"
        f"    account: {minted.account}\n"
        f"    card: {minted.card}\n"
        f"    zone_token: \"{minted.zone_token}\"\n"
        f"\n"
        f"The zone token is half of the agent's public address: keep it in the deployment's files.\n"
    )


def mint(name: str) -> Minted:
    """Draw a new agent's short id and zone token. The name is checked as a card's name (R158)."""
    problem = calling_card.name_problem(name)
    if problem:
        raise calling_card.CardError(problem)
    return Minted(name=name, short_id=secrets.token_hex(calling_card.SHORTID_LEN // 2),
                  zone_token=secrets.token_hex(ZONE_TOKEN_BYTES))
