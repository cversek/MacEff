"""Setting up a rung-2 peer link (MIS-0004 R56 to R65) from a card instead of by hand.

A broker's card is everything a peer's operator needs to declare it: the mail domain, the one
private address and port its listener is declared on, and for each agent it speaks for, the calling
card, the public signing key and the account that holds it. It carries no secret: a public key proves
authorship and reaches nothing.

The card is read from the operator's own files, through the same loader the broker runs on, so a card
cannot describe a broker the files don't declare. The registry is root's to write; the card prints
the line its operator runs and never runs it.
"""
import json
import pwd
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

#: The card's format version. A reader refuses one it does not know rather than guessing.
CARD_VERSION = 1

#: The only keys a card may carry, so a card is closed the way the declarations are.
_CARD_KEYS = {"amail_peer_card", "domain", "host", "port", "agents", "notes"}
_AGENT_KEYS = {"card", "key", "account"}


class CardError(ValueError):
    """A card that can't be built or read, with the reason an operator can act on."""


def _load(broker_config: Path):
    """The operator's broker config and its addressing, validated by the broker's own loader."""
    from pydantic import ValidationError

    from macf.amail.deploy_config import BrokerDeployConfig, ConfigError, load_declarative_config
    try:
        deploy = BrokerDeployConfig.model_validate(load_declarative_config(Path(broker_config)))
        return deploy, deploy.load_addressing()
    except (ConfigError, ValidationError, OSError) as e:
        raise CardError(f"the broker config {broker_config} does not load: {e}") from e


@dataclass(frozen=True, kw_only=True)
class _Declared:
    """What the registry says of one card: its current signing key and account, or why it says nothing."""
    key: Optional[str] = None
    account: Optional[str] = None
    why: str = ""


def _registry_entry(registry, card: str) -> _Declared:
    """The registry's current signing key and account for *card*, or the reason there are none."""
    from macf.amail.registry import RegistryError
    if registry is None:
        return _Declared(why="no registry was given")
    try:
        keys = registry.signing_keys(card)
        return _Declared(key=keys[0] if keys else None, account=registry.account_of(card))
    except RegistryError as e:
        return _Declared(why=f"the registry can't be read ({e})")


def _own_key(path: Optional[Path]) -> Optional[str]:
    """The public line of this agent's own signing key, or None when there is no usable one."""
    if not path:
        return None
    from macf.amail.crypto import key_custody
    report = key_custody(Path(path))
    return report["public"] if report["usable"] else None


def _account_of_uid(uid: Optional[int]) -> Optional[str]:
    if uid is None:
        return None
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        print(f"⚠️ MACF: no account has uid {uid} (leaving the card's account empty)", file=sys.stderr)
        return None


def build_card(broker_config: Path, *, agents: Iterable[str], registry=None,
               own_agent: Optional[str] = None, own_key: Optional[Path] = None) -> Dict:
    """The card for *agents* of the broker the operator's *broker_config* declares.

    A key comes from the registry first, since that is what the receiving operator will declare and
    what verification reads; for *own_agent* only, the agent's own key file is the fallback. An agent
    with neither is still on the card, and a note says its mail reads unverified until one is declared.
    """
    deploy, addressing = _load(broker_config)
    if deploy.peer_listen is None:
        raise CardError(f"{broker_config} declares no peer_listen, so no peer can reach this broker; "
                        f"declare the one private address and port it listens on first")
    out: Dict[str, Dict] = {}
    notes: List[str] = []
    for name in agents:
        binding = addressing.agents.get(name)
        if binding is None:
            raise CardError(f"{name} is not an agent in {deploy.addressing_path}; "
                            f"its agents are {', '.join(sorted(addressing.agents))}")
        if not binding.card:
            raise CardError(f"{name} has no calling card in {deploy.addressing_path}; "
                            f"a peer judges its signatures by card, so it can't be on a card without one")
        declared = _registry_entry(registry, binding.card)
        key, account, why = declared.key, declared.account, declared.why
        if key is None and name == own_agent:
            key = _own_key(own_key)
            if key:
                notes.append(f"{name}'s key is from its own key file, not this host's registry "
                             f"({why or 'the registry has none'}); the peer's operator should confirm it "
                             f"with this one before declaring it")
        if key is None:
            notes.append(f"{name} has no declared key, so a peer reads its mail as unverified until one is "
                         f"declared ({why or 'the registry has none'})")
        out[name] = {"card": binding.card, "key": key, "account": account or _account_of_uid(binding.uid)}
    card = {"amail_peer_card": CARD_VERSION, "domain": addressing.domain,
            "host": deploy.peer_listen.host, "port": deploy.peer_listen.port, "agents": out}
    if notes:
        card["notes"] = notes
    return card


def render_card(card: Dict) -> str:
    """The card as one line of JSON, to paste or send."""
    return json.dumps(card, sort_keys=True, separators=(",", ":"))


def parse_card(text: str) -> Dict:
    """A card read back and checked by the rules the operator's declarations enforce."""
    from pydantic import ValidationError

    from macf.amail.crypto import parse_public_key
    from macf.amail.deploy_config import PeerLinkDecl
    try:
        card = json.loads(text)
    except json.JSONDecodeError as e:
        raise CardError(f"not a card: {e}") from e
    if not isinstance(card, dict) or card.get("amail_peer_card") != CARD_VERSION:
        raise CardError(f"not a version {CARD_VERSION} amail peer card")
    extra = set(card) - _CARD_KEYS
    if extra:
        raise CardError(f"the card carries keys no card has: {', '.join(sorted(extra))}")
    agents = card.get("agents")
    if not isinstance(agents, dict) or not isinstance(card.get("domain"), str) or not card["domain"]:
        raise CardError("the card names no domain or no agents")
    try:
        PeerLinkDecl(host=card.get("host", ""), port=card.get("port", 0),
                     agents={box: (held or {}).get("card", "") for box, held in agents.items()})
    except (ValidationError, AttributeError) as e:
        raise CardError(f"the card would not make a valid peer link: {e}") from e
    for box, held in agents.items():
        if set(held) - _AGENT_KEYS:
            raise CardError(f"{box} on the card carries keys no card has: {', '.join(sorted(set(held) - _AGENT_KEYS))}")
        if held.get("key"):
            try:
                parse_public_key(held["key"])
            except ValueError as e:
                raise CardError(f"{box}'s key on the card is not a public key: {e}") from e
    return card


def describe(card: Dict) -> List[str]:
    """The card for a person: what it says, what the peer's operator runs, and its notes."""
    lines = [f"amail peer card for {card['domain']}, listening on {card['host']}:{card['port']}"]
    for box, held in sorted(card["agents"].items()):
        lines.append(f"  {box}@{card['domain']}  card {held['card']}  key {held.get('key') or '(none declared)'}")
    lines.append("")
    lines.append("For the peer's operator, on the peer's host:")
    lines.append("  macf_tools amail peer add '<this card>'      # the peer link and contact entries, shown first")
    for _box, held in sorted(card["agents"].items()):
        if held.get("key"):
            account = held.get("account") or "<account>"
            lines.append(f"  sudo macf_tools amail registry declare --card {held['card']} "
                         f"--key {held['key']} --account {account}")
    for note in card.get("notes", []):
        lines.append(f"⚠️ {note}")
    lines.append("")
    lines.append(render_card(card))
    return lines
