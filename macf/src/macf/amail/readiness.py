"""What an agent's mail still needs, piece by piece, each with the command that supplies it.

`amail status` says whether mail works now. This says why not, or what would make it better:
the address, the signing key and its declaration, the registry, how the broker is supervised, and
each peer link with what waits for it. Each piece is read from where the broker and the client read
it, and nothing here writes.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


@dataclass(frozen=True, kw_only=True)
class Piece:
    """One piece of an agent's mail: ok (True), missing (False), or not applicable or unknown (None)."""
    name: str
    ok: Optional[bool]
    detail: str
    fix: str = ""
    #: A short value a tool can compare, where the piece has one (the broker's supervision).
    kind: str = ""


def outbox_dir(handoff: Path, domain: str) -> Path:
    """Where the broker keeps what waits for *domain*: named by the lowercased domain, as
    ``Broker._outbox`` names it, whatever case the operator declared the peer in."""
    return Path(handoff) / "_outbox" / domain.strip().lower()


def _count(directory: Path) -> int:
    return len(list(directory.glob("*.amsg"))) if directory.is_dir() else 0


def pieces(cfg: dict, *, registry=None, daemon_installed: Callable[[str, Path], bool] = lambda c, h: False,
           interim_jobs: Callable[[], List[Path]] = list) -> List[Piece]:
    """The pieces of the mail of the agent *cfg* describes (the client's resolved ``amail.json``)."""
    from macf.amail.crypto import key_custody
    from macf.amail.registry import RegistryError
    out: List[Piece] = []
    if not (cfg.get("agent") and cfg.get("domain")):
        return [Piece(name="address", ok=False, detail="no agent name and mail domain are configured",
                      fix="write .maceff/amail.json with agent, domain, socket and broker_config")]
    out.append(Piece(name="address", ok=True, detail=f"{cfg['agent']}@{cfg['domain']}"))

    key_path = Path(cfg["signing_key"]) if cfg.get("signing_key") else None
    custody = key_custody(key_path) if key_path else {"exists": False, "usable": False, "public": ""}
    if not custody["usable"]:
        out.append(Piece(name="signing key", ok=False,
                         detail=f"no usable signing key at {key_path}" if key_path else "no signing key is named",
                         fix="macf_tools amail keygen  (or agent init, whose mail step makes one)"))
    else:
        out.append(Piece(name="signing key", ok=True, detail=str(key_path)))
    out.append(Piece(name="signing declared", ok=bool(cfg.get("signing_required")),
                     detail="every message is signed, and an unsigned send is refused" if cfg.get("signing_required")
                     else "a send with no key would go out unsigned",
                     fix="" if cfg.get("signing_required") else
                     "agent init (its mail step), or set signing_required in .maceff/amail.json"))

    broker_config = Path(cfg["broker_config"]) if cfg.get("broker_config") else None
    card = None
    deploy = addressing = None
    if broker_config is not None:
        from macf.amail.peer_setup import CardError, _load
        try:
            deploy, addressing = _load(broker_config)
            binding = addressing.agents.get(cfg["agent"])
            card = binding.card if binding else None
        except CardError as e:
            out.append(Piece(name="broker config", ok=False, detail=str(e), fix="fix the broker config"))
    if card and custody["usable"]:
        try:
            declared = registry.signing_keys(card) if registry is not None else []
        except RegistryError as e:
            out.append(Piece(name="registry", ok=None, detail=f"the registry can't be read: {e}"))
        else:
            mine = custody["public"] in declared
            account = registry.account_of(card) if registry is not None and declared else None
            out.append(Piece(name="registry", ok=mine,
                             detail=f"{card}'s key is declared" if mine else
                             f"{card}'s key is {'another one' if declared else 'not declared'} in the registry, "
                             f"so peers read this agent's mail as unverified",
                             fix="" if mine else f"macf_tools amail registry declare --card {card} "
                                                 f"--key {custody['public']} --account {account or '<account>'}"))

    if broker_config is not None and deploy is not None:
        from macf.amail import host_daemon
        broker_card = host_daemon.card_for(addressing.domain)
        home = broker_config.resolve().parent
        interim = interim_jobs()
        declared = host_daemon.declared_broker(broker_config, [home] + [b.home for b in addressing.agents.values()
                                                                        if b.home])
        if declared is not None and daemon_installed(declared.card, declared.home):
            out.append(Piece(name="broker supervision", ok=True, kind="supervised",
                             detail=f"unit {declared.unit!r} of {declared.card}'s primal daemon"))
        elif declared is None and daemon_installed(broker_card, home):
            out.append(Piece(name="broker supervision", ok=True, kind="supervised",
                             detail=f"a declared unit of {broker_card}'s primal daemon"))
        elif declared is not None:
            out.append(Piece(name="broker supervision", ok=False, kind="declared, daemon not installed",
                             detail=f"declared as unit {declared.unit!r} of {declared.card}'s daemon, which isn't "
                                    f"installed", fix=f"MACEFF_AGENT_HOME_DIR={declared.home} macf_tools pd install"))
        elif interim:
            out.append(Piece(name="broker supervision", ok=None, kind="launchd job",
                             detail=f"a launchd job of its own ({', '.join(p.stem for p in interim)}), outside any "
                                    f"declaration", fix="macf_tools amail broker-unit"))
        else:
            out.append(Piece(name="broker supervision", ok=False, kind="agent-launched",
                             detail="agent-launched: the broker runs only while an agent starts it",
                             fix="macf_tools amail broker-unit"))
        if deploy.peer_listen is not None:
            out.append(Piece(name="listener", ok=True,
                             detail=f"{deploy.peer_listen.host}:{deploy.peer_listen.port}, a crossing of this system's "
                                    f"boundary (R47 of the MIS-0007 draft)"))
        handoff = deploy.inbound_handoff
        for dom, link in sorted(deploy.peer_links.items()):
            box = outbox_dir(handoff, dom) if handoff else None
            waiting = _count(box) if box else 0
            refused = _count(box / "refused") if box else 0
            agents = ", ".join(f"{b}={c}" for b, c in sorted(link.agents.items())) or "no agents declared"
            out.append(Piece(name=f"peer {dom}", ok=False if (refused or not link.agents) else (None if waiting else True),
                             detail=f"{link.host}:{link.port}, {agents}; {waiting} waiting, {refused} refused",
                             fix=f"macf_tools amail peer check {dom}" if (waiting or refused or not link.agents) else ""))
    return out


def as_json(found: List[Piece]) -> str:
    return json.dumps([{"name": p.name, "ok": p.ok, "detail": p.detail, "fix": p.fix} for p in found], indent=2)


# ---- the outbox: what waits for a peer, and what a peer refused ----------------------------------------

@dataclass(frozen=True, kw_only=True)
class Held:
    """One message the broker holds for a peer: waiting for a retry, or refused by the peer."""
    peer: str
    state: str
    message_id: str
    sender: str
    recipient: str
    handed_off_at: str
    age_s: Optional[float]
    reason: str = ""


def outbox(broker_config: Path, *, sender: Optional[str] = None) -> List[Held]:
    """The messages the broker *broker_config* declares holds for its peers, oldest first; only
    *sender*'s when given. A waiting message keeps no reason (the next attempt finds the current one,
    and `amail peer check` shows it); a refused one keeps the peer's."""
    import datetime
    from macf.amail.peer_setup import _load
    deploy, _ = _load(Path(broker_config))
    root = deploy.inbound_handoff
    if root is None:
        return []
    now = datetime.datetime.now(datetime.timezone.utc)
    held: List[Held] = []
    for dom in sorted(deploy.peer_links):
        for state, box in (("waiting", outbox_dir(root, dom)), ("refused", outbox_dir(root, dom) / "refused")):
            if not box.is_dir():
                continue
            for amsg in sorted(box.glob("*.amsg")):
                try:
                    side = json.loads(amsg.with_suffix(".json").read_text())
                except (OSError, ValueError) as e:
                    side = {"message_id": amsg.stem, "unreadable": f"{type(e).__name__}: {e}"}
                if sender and str(side.get("sender", "")).lower() != sender.lower():
                    continue
                at = str(side.get("handed_off_at", ""))
                try:
                    age = (now - datetime.datetime.fromisoformat(at.replace("Z", "+00:00"))).total_seconds()
                except ValueError:
                    age = None
                reason = (side.get("refused") or {}).get("reason", "") if state == "refused" else ""
                held.append(Held(peer=dom, state=state, message_id=str(side.get("message_id", amsg.stem)),
                                 sender=str(side.get("sender", "")), recipient=str(side.get("recipient", "")),
                                 handed_off_at=at, age_s=age, reason=reason or side.get("unreadable", "")))
    return sorted(held, key=lambda h: h.handed_off_at)
