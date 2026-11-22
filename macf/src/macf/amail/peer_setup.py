"""Setting up a rung-2 peer link (MIS-0004 R56 to R65) from a card instead of by hand.

A broker's card is everything a peer's operator needs to declare it: the mail domain, the one
private address and port its listener is declared on, and for each agent it speaks for, the calling
card, the public signing key and the account that holds it. It carries no secret: a public key proves
authorship and reaches nothing.

The card is read from the operator's own files, through the same loader the broker runs on, so a card
cannot describe a broker the files don't declare. The registry is root's to write; the card prints
the line its operator runs and never runs it.
"""
import copy
import difflib
import json
import os
import pwd
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

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
    if not isinstance(agents, dict) or not agents or not isinstance(card.get("domain"), str) or not card["domain"]:
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


def fingerprint(key: str) -> str:
    """A short fingerprint of a public key line, to read aloud or compare on a second channel: a key
    that arrives on a card is a claim (amail policy 6b.5) until its operator confirms it."""
    import base64
    import hashlib
    raw = base64.b64decode(key.split(":", 1)[-1])
    digest = hashlib.sha256(raw).hexdigest()[:20]
    return ":".join(digest[i:i + 4] for i in range(0, 20, 4))


def registry_steps(card: Dict) -> List[str]:
    """The registry declarations the receiving operator runs, one at a time: each stages the change
    and prints its own root install step, and a second declare staged before the first is installed
    would overwrite it. Each key's fingerprint is to be confirmed with the card's operator first."""
    keyed = [(box, held) for box, held in sorted(card["agents"].items()) if held.get("key")]
    if not keyed:
        return []
    lines = ["Confirm each key's fingerprint with this card's operator on another channel before declaring it.",
             ("Then, one at a time: run the line, run the install step it prints, run "
              "`macf_tools amail registry check`, then the next line.")]
    for _box, held in keyed:
        lines.append(f"  # {held['card']}: fingerprint {fingerprint(held['key'])}")
        lines.append(f"  macf_tools amail registry declare --card {held['card']} --key {held['key']} "
                     f"--account {held.get('account') or '<account>'}")
    return lines


def describe(card: Dict) -> List[str]:
    """The card for a person: what it says, what the peer's operator runs, and its notes."""
    lines = [f"amail peer card for {card['domain']}, listening on {card['host']}:{card['port']}"]
    for box, held in sorted(card["agents"].items()):
        key = held.get("key")
        lines.append(f"  {box}@{card['domain']}  card {held['card']}  "
                     + (f"key {key}  fingerprint {fingerprint(key)}" if key else "key (none declared)"))
    lines.append("")
    lines.append("For the peer's operator, on the peer's host:")
    lines.append("  macf_tools amail peer add '<this card>'      # the peer link and contact entries, shown first")
    lines.extend(registry_steps(card))
    for note in card.get("notes", []):
        lines.append(f"⚠️ {note}")
    lines.append("")
    lines.append(render_card(card))
    return lines


# ---- adding a peer from its card -------------------------------------------------------------------
#
# The operator's files are edited as text, one entry at a time, so their comments and every line the
# change does not own survive. Each edit is then held to two checks before it is shown: parsed, the new
# text must equal the old data with exactly the intended change made, and the pair of candidate files
# must load through the broker's own loader. An edit that can't meet the first is refused with the
# entry to write by hand, never approximated.

_PLAIN_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _yaml_key(key: str) -> str:
    return key if _PLAIN_KEY.fullmatch(key) else json.dumps(key)


def _flow(value) -> str:
    return yaml.safe_dump(value, default_flow_style=True, sort_keys=False, width=10 ** 6).strip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_content(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith("#")


def _block(lines: List[str], start: int) -> int:
    """The index one past the block that the key on *start* opens: every following line that is blank,
    a comment, or indented deeper than it."""
    base = _indent(lines[start])
    end = start + 1
    last = start + 1
    while end < len(lines):
        if _is_content(lines[end]):
            if _indent(lines[end]) <= base:
                break
            last = end + 1
        end += 1
    return last


def _key_line(lines: List[str], key: str, indent: int, lo: int, hi: int, *, fold: bool = False) -> Optional[int]:
    pattern = re.compile(r"^ {%d}[\"']?%s[\"']?\s*:" % (indent, re.escape(key)), re.IGNORECASE if fold else 0)
    for i in range(lo, hi):
        if pattern.match(lines[i]):
            return i
    return None


def _child_indent(lines: List[str], lo: int, hi: int, default: int) -> int:
    for i in range(lo, hi):
        if _is_content(lines[i]):
            return _indent(lines[i])
    return default


def _hand(entry: str, where: str) -> CardError:
    return CardError(f"{where} is written in a shape this command can't change one line at a time; "
                     f"write this by hand, then run the command again to check it:\n  {entry}")


def set_mapping_entry(text: str, top: str, key: str, value) -> str:
    """*text* with ``top.key`` set to *value* on one line, every other line untouched."""
    lines = text.splitlines(True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    entry = f"{_yaml_key(key)}: {_flow(value)}\n"
    at = _key_line(lines, top, 0, 0, len(lines))
    if at is None:
        return "".join(lines) + f"{top}:\n  {entry}"
    inline = lines[at].split(":", 1)[1].split("#", 1)[0].strip()
    if inline:
        if yaml.safe_load(inline) not in ({}, None):
            raise _hand(f"{top}: {{{entry.strip()}}}", f"{top}")
        lines[at] = f"{top}:\n"
        lines.insert(at + 1, f"  {entry}")
        return "".join(lines)
    end = _block(lines, at)
    ind = _child_indent(lines, at + 1, end, 2)
    found = _key_line(lines, key, ind, at + 1, end, fold=True)    # a domain is one peer whatever its case
    if found is not None:
        lines[found:_block(lines, found)] = [" " * ind + entry]
    else:
        lines.insert(end, " " * ind + entry)
    return "".join(lines)


def add_list_item(text: str, path: List[str], item) -> str:
    """*text* with *item* appended to the block list at the mapping *path*, every other line untouched."""
    lines = text.splitlines(True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lo, hi, ind = 0, len(lines), 0
    for depth, key in enumerate(path):
        at = _key_line(lines, key, ind, lo, hi)
        where = ".".join(path[:depth + 1])
        if at is None:
            if depth != len(path) - 1:
                raise _hand(f"{where}: ...", where)
            ins = hi
            while ins > lo and not _is_content(lines[ins - 1]):
                ins -= 1
            lines[ins:ins] = [" " * ind + f"{key}:\n", " " * (ind + 2) + f"- {_flow(item)}\n"]
            return "".join(lines)
        inline = lines[at].split(":", 1)[1].split("#", 1)[0].strip()
        if depth == len(path) - 1:
            if inline:
                if yaml.safe_load(inline) not in ([], None):
                    raise _hand(f"- {_flow(item)}", where)
                lines[at] = " " * ind + f"{key}:\n"
                lines.insert(at + 1, " " * (ind + 2) + f"- {_flow(item)}\n")
                return "".join(lines)
            end = _block(lines, at)
            item_ind = _child_indent(lines, at + 1, end, ind + 2)
            lines.insert(end, " " * item_ind + f"- {_flow(item)}\n")
            return "".join(lines)
        if inline:
            raise _hand(f"{where}: ...", where)
        lo, hi = at + 1, _block(lines, at)
        ind = _child_indent(lines, lo, hi, ind + 2)
    return "".join(lines)


@dataclass
class AddPlan:
    """The two files' current and new texts, and the operator's root steps, for one card."""
    broker_path: Path
    broker_now: str
    broker_new: str
    addressing_path: Path
    addressing_now: str
    addressing_new: str
    registry_lines: List[str]

    @property
    def changed(self) -> bool:
        return self.broker_new != self.broker_now or self.addressing_new != self.addressing_now

    def diff(self) -> str:
        out = []
        for path, now, new in ((self.broker_path, self.broker_now, self.broker_new),
                               (self.addressing_path, self.addressing_now, self.addressing_new)):
            out.extend(difflib.unified_diff(now.splitlines(True), new.splitlines(True),
                                            fromfile=f"{path} (now)", tofile=f"{path} (after)"))
        return "".join(out)

    def write(self, backup_suffix: Optional[str] = None) -> List[Path]:
        """Write each changed file beside itself and rename it into place, keeping its mode; with
        *backup_suffix*, the old text is kept beside it first. Returns the files written."""
        written = []
        for path, now, new in ((self.broker_path, self.broker_now, self.broker_new),
                               (self.addressing_path, self.addressing_now, self.addressing_new)):
            if new == now:
                continue
            if path.read_text() != now:
                raise CardError(f"{path} changed since the plan was made; run the command again")
            if backup_suffix:
                shutil.copy2(path, path.with_name(path.name + backup_suffix))
            beside = path.with_name(f".{path.name}.new")
            beside.write_text(new)
            shutil.copymode(path, beside)
            os.replace(beside, path)
            written.append(path)
        return written


def _expect(now_text: str, new_text: str, change, where: Path) -> None:
    """Refuse *new_text* unless, parsed, it is *now_text* parsed with exactly *change* made."""
    expected = copy.deepcopy(yaml.safe_load(now_text) or {})
    change(expected)
    if yaml.safe_load(new_text) != expected:
        raise CardError(f"the edit to {where} would change more than the entry it means to; "
                        f"nothing was written. Write the entry by hand.")


def plan_add(broker_config: Path, card: Dict, *, local_agents: Iterable[str], note: str = "") -> AddPlan:
    """What adding the peer on *card* would make of the operator's broker config and addressing file:
    its peer link with its agents map, and a contact for each of *local_agents*. Checked through the
    broker's own loader on the candidate files before it is returned; nothing is written."""
    from pydantic import ValidationError

    from macf.amail.deploy_config import BrokerDeployConfig, ConfigError
    card = parse_card(render_card(card))
    broker_config = Path(broker_config)
    deploy, addressing = _load(broker_config)
    addressing_path = Path(deploy.addressing_path)
    dom = card["domain"].strip().lower()
    declared = (yaml.safe_load(broker_config.read_text()) or {}).get("peer_links") or {}
    existing = next((v for k, v in declared.items() if str(k).strip().lower() == dom), None) or {}
    link = {"host": card["host"], "port": card["port"]}
    note = note or existing.get("note", "")         # the operator's note survives a new card
    if note:
        link["note"] = note
    link["agents"] = {box: held["card"] for box, held in sorted(card["agents"].items())}

    broker_now = broker_config.read_text()
    broker_new = broker_now if existing == link else set_mapping_entry(broker_now, "peer_links", dom, link)
    def _link(d):
        if not d.get("peer_links"):
            d["peer_links"] = {}
        for k in [k for k in d["peer_links"] if str(k).strip().lower() == dom]:
            del d["peer_links"][k]
        d["peer_links"][dom] = link
    if broker_new != broker_now:
        _expect(broker_now, broker_new, _link, broker_config)

    addressing_now = addressing_path.read_text()
    addressing_new = addressing_now
    wanted = []
    for name in local_agents:
        if name not in addressing.agents:
            raise CardError(f"{name} is not an agent in {addressing_path}")
        have = {(c.get("address") if isinstance(c, dict) else c) for c in addressing.agents[name].contacts}
        for box in sorted(card["agents"]):
            address = f"{box}@{card['domain']}"
            if address not in have:
                entry = {"address": address, "direction": "both"}
                addressing_new = add_list_item(addressing_new, ["agents", name, "contacts"], entry)
                wanted.append((name, entry))

    def _contacts(d):
        for name, entry in wanted:
            agent = d["agents"][name]
            agent["contacts"] = (agent.get("contacts") or []) + [entry]
    _expect(addressing_now, addressing_new, _contacts, addressing_path)

    with tempfile.TemporaryDirectory(prefix="amail-peer-add.") as tmp:
        cand_addressing = Path(tmp) / "addressing.yaml"
        cand_addressing.write_text(addressing_new)
        raw = yaml.safe_load(broker_new)
        raw["addressing_path"] = str(cand_addressing)
        try:
            BrokerDeployConfig.model_validate(raw).to_broker_config()
        except (ConfigError, ValidationError, ValueError) as e:
            raise CardError(f"with this card the broker would not start: {e}") from e

    return AddPlan(broker_config, broker_now, broker_new, addressing_path, addressing_now, addressing_new,
                   registry_lines(card))


def registry_lines(card: Dict) -> List[str]:
    """The registry declarations the receiving operator runs, with the fingerprints to confirm and the
    order to run them in (``registry_steps``)."""
    return registry_steps(card)


# ---- checking a peer link, station by station --------------------------------------------------------
#
# Each station is one place on the path a message takes from this broker's files to the peer's agent:
# the declaration here, the peer's listener, the address it knows this broker by, its build, the cards
# and keys each side declares for the other, and, when asked, one message the peer acknowledges. A
# station that fails says what failed and the command that fixes it, and the stations that depend on it
# are not run, so the first failure is the one to fix.

@dataclass(frozen=True, kw_only=True)
class Station:
    """One station of a peer check: passed (True), failed (False) or not run or unknown (None)."""
    name: str
    ok: Optional[bool]
    detail: str
    fix: str = ""


def check_peer(broker_config: Path, domain: str, *, registry=None, send=None) -> List[Station]:
    """Check the rung-2 link from the broker *broker_config* declares to the peer *domain*.

    *send*, when given, is called with no arguments to send one test message to the peer and returns
    the broker's submit result; the last station passes only when the peer acknowledged it."""
    from macf.amail import peer_link
    from macf.amail.registry import RegistryError

    out: List[Station] = []
    try:
        deploy, addressing = _load(broker_config)
    except CardError as e:
        return [Station(name="config", ok=False, detail=str(e), fix="fix the broker config, then check again")]
    dom = domain.strip().lower()
    links = {k.strip().lower(): v for k, v in deploy.peer_links.items()}
    link = links.get(dom)
    if link is None:
        return [Station(name="config", ok=False, detail=f"{broker_config} declares no peer link to {domain}",
                        fix=f"get {domain}'s card and run: macf_tools amail peer add '<its card>'")]
    out.append(Station(name="config", ok=True, detail=f"{domain} is declared at {link.host}:{link.port}"))

    if not link.agents:
        out.append(Station(name="our agents map", ok=False,
                           detail=f"the link to {domain} declares none of its agents, so none of its mail can "
                                  f"read attested here (MIS-0004 R44)",
                           fix=f"get {domain}'s card and run: macf_tools amail peer add '<its card>'"))
    else:
        out.append(Station(name="our agents map", ok=True,
                           detail=", ".join(f"{b} = {c}" for b, c in sorted(link.agents.items()))))
    missing = []
    for card in sorted(set(link.agents.values())):
        try:
            if registry is None or not registry.signing_keys(card):
                missing.append(card)
        except RegistryError as e:
            print(f"⚠️ MACF: peer check could not read the registry (counting {card} undeclared): {e}",
                  file=sys.stderr)
            missing.append(card)
    if link.agents:
        out.append(Station(name="our registry", ok=not missing,
                           detail=(f"no key declared here for {', '.join(missing)}, so their mail reads "
                                   f"unverified here") if missing else "a key is declared for each of its agents",
                           fix=("this host's operator declares them from the peer's card, one at a time, "
                                "after confirming each fingerprint (macf_tools amail registry declare ...)")
                           if missing else ""))

    try:
        reply = peer_link.send_request(link.host, link.port, {"op": "ping", "from": addressing.domain})
    except peer_link.ClosedUnread as e:
        out.append(Station(name="address", ok=False,
                           detail=f"{e}: the peer does not declare this host's address as {addressing.domain}",
                           fix=f"send {domain}'s operator this broker's card: macf_tools amail peer card"))
        return out
    except ConnectionError as e:
        out.append(Station(name="listener", ok=False, detail=str(e),
                           fix=f"is {domain}'s broker running, with peer_listen on {link.host}:{link.port}, "
                               f"and does its firewall admit this host?"))
        return out
    out.append(Station(name="listener", ok=True, detail=f"{link.host}:{link.port} answers"))
    if not reply.get("ok"):
        reason = str(reply.get("reason", ""))
        if "unknown request" in reason:
            out.append(Station(name="build", ok=None,
                               detail=f"{domain}'s broker has no ping, an older build; the stations past this "
                                      f"one can't be checked from here",
                               fix=f"{domain}'s operator updates macf and restarts its broker"))
        else:
            out.append(Station(name="address", ok=False, detail=f"the peer refused the check: {reason}",
                               fix=f"send {domain}'s operator this broker's card: macf_tools amail peer card"))
        return out
    out.append(Station(name="address", ok=True,
                       detail=f"the peer knows this host as {reply.get('you_are')}"))
    from macf import __version__
    out.append(Station(name="build", ok=True,
                       detail=f"peer {reply.get('build')}, here {__version__}, protocol {reply.get('protocol')}"))

    declared = reply.get("your_agents") or {}
    ours = {name: b.card for name, b in addressing.agents.items() if b.card}
    wrong = sorted(b for b, c in declared.items() if b in ours and ours[b] != c)
    absent = sorted(b for b in ours if b not in declared)
    if wrong or not declared:
        out.append(Station(name="their agents map", ok=False,
                           detail=(f"the peer declares other cards for {', '.join(wrong)}" if wrong else
                                   "the peer declares none of this broker's agents, so none of their mail can "
                                   "read attested there"),
                           fix=f"send {domain}'s operator this broker's card: macf_tools amail peer card --all"))
    else:
        out.append(Station(name="their agents map", ok=True,
                           detail=", ".join(f"{b} = {c}" for b, c in sorted(declared.items()))
                                  + (f"; not declared there: {', '.join(absent)}" if absent else "")))
    keys = reply.get("your_keys_declared") or {}
    undeclared = sorted(c for c, v in keys.items() if v is False)
    unknown = sorted(c for c, v in keys.items() if v is None)
    if declared:
        out.append(Station(name="their registry", ok=False if undeclared else (None if unknown else True),
                           detail=(f"no key declared there for {', '.join(undeclared)}" if undeclared else
                                   f"the peer could not read its registry for {', '.join(unknown)}" if unknown else
                                   "a key is declared there for each agent it declares"),
                           fix=("the peer's operator runs the registry lines from this broker's card"
                                if undeclared or unknown else "")))

    if send is not None:
        if any(s.ok is False for s in out):
            out.append(Station(name="test message", ok=None, detail="not sent: fix the stations above first"))
            return out
        result = send()
        states = [d for d in result.get("delivered", []) if d.get("rung") == "peer"]
        if result.get("ok") and states and all(d.get("state") == "delivered" for d in states):
            out.append(Station(name="test message", ok=True,
                               detail=f"acknowledged by the peer ({result.get('message_id')}); it reads attested "
                                      f"there when the two stations above pass"))
        else:
            why = ("; ".join(d.get("detail", "") for d in states) or "; ".join(map(str, result.get("refused", [])))
                   or "; ".join(f.get("error", "") for f in result.get("failures", [])) or "no peer delivery")
            out.append(Station(name="test message", ok=False, detail=f"not acknowledged: {why}",
                               fix="the broker keeps it and retries; the peer's audit says why it was not stored"))
    return out
