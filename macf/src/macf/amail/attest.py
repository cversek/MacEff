"""What a signature attests, read against the operator's registry (MIS-0004 R45, R46).

Two decisions the broker and the receiver share, kept apart from both so each calls the same
rule: whether a key may sign now, and what a verified signature proves about a message.

WHEN A KEY COUNTS (R45). A retired key still verifies what was accepted while it was valid, so old
mail stays readable after a rotation, and it never signs again. "While it was valid" is judged on
the broker's acceptance time, because a thief holding a retired key can date a message any way he
likes. The time must be the RECEIVING broker's own record of acceptance, which the sender can't
reach: the ``handed_off_at`` its sidecar carries when it wrote the message to the agent's box. A
message id carries a time too, but a well-formed peer id is kept across a shared hand-off, so the
time inside it may be another system's mint or anyone's who can get mail into a hand-off. It is
never read here. With no record of our own, only the keys that may sign now count, and a retired
key verifies nothing.

WHAT A SIGNATURE ATTESTS (R46). A key file sits in the account that holds it, and every process
of that account can read it. Where the operator declared two agents' keys on one account, a
signature proves the login, not the agent, and the verdict says so and names who shares it.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from macf import calling_card

from .crypto import verify
from .registry import Registry, RegistryError
from .trust import TrustClass


def acceptance_time(sidecar: Dict[str, Any], own_domain: str) -> Optional[datetime.datetime]:
    """When the receiving broker accepted the message, from the sidecar it wrote at hand-off.

    None unless the sidecar is this broker's own (rung ``local``, written under *own_domain*) and
    its time is a timezone-aware ISO time: a peer broker's sidecar is that broker's word."""
    if sidecar.get("rung") != "local" or sidecar.get("origin_domain") != own_domain:
        return None
    try:
        when = datetime.datetime.fromisoformat(str(sidecar.get("handed_off_at")))
    except ValueError:
        return None  # noqa: MACEFF003 - an unreadable time is no record, so only current keys count (R45)
    return when if when.tzinfo is not None else None


def read_acceptance_time(sidecar_path: Path, own_domain: str, broker_uid: int, *,
                         payload: bytes, message_id: str) -> Optional[datetime.datetime]:
    """:func:`acceptance_time` from the sidecar file at *sidecar_path*, for the message whose
    delivered bytes are *payload* and whose id is *message_id*. None unless the broker's uid owns
    the file and the sidecar was written for exactly that message.

    A box is group-writable (2770) with no sticky bit. A sidecar another member of the group wrote
    is no record, and a genuine old one renamed to sit beside a new message would lend it an old
    hand-off time; the ``raw_sha256`` and ``message_id`` the broker wrote into it bind it to its own
    message."""
    try:
        if os.stat(sidecar_path, follow_symlinks=False).st_uid != broker_uid:
            return None
        sidecar = json.loads(Path(sidecar_path).read_text())
    except (OSError, ValueError):
        return None  # noqa: MACEFF003 - an unreadable sidecar is no record, so only current keys count (R45)
    if not isinstance(sidecar, dict):
        return None
    if (sidecar.get("raw_sha256") != hashlib.sha256(payload).hexdigest()
            or sidecar.get("message_id") != message_id):
        return None
    return acceptance_time(sidecar, own_domain)


def may_sign(card: str, public_key: str, registry: Registry,
             now: Optional[datetime.datetime] = None) -> bool:
    """Whether *public_key* may sign for *card* now: declared, valid now and not retired (R45).

    A registry that can't be trusted raises :class:`RegistryError` rather than answering; the
    caller treats that as a refusal, never as permission."""
    return public_key in registry.signing_keys(card, at=now)


def registry_verdict(message: Any, card: str, registry: Registry,
                     accepted_at: Optional[datetime.datetime]) -> Dict[str, Any]:
    """The receiver's verdict on *message* from *card*, against the operator's registry.

    *accepted_at* is the receiving broker's own acceptance time (:func:`acceptance_time`), or None.
    The result carries ``trust``, ``reason``, ``keys_declared``, and for a verified message what it
    ``attests`` (``agent`` or ``login``) and who it is ``shared_with``. Nothing here falls back to
    keys an agent declared for itself."""
    verdict: Dict[str, Any] = {"attests": None, "shared_with": [],
                               "accepted_at": accepted_at.isoformat() if accepted_at else None}
    # One read, and every lookup below answered from it: a file that changes or turns
    # untrustworthy between reads can neither raise into ingest nor mix two versions.
    try:
        loaded = registry.load()
    except RegistryError as e:
        return {**verdict, "trust": TrustClass.UNVERIFIED.value, "keys_declared": None,
                "reason": f"the operator's registry can't be trusted ({e}); nothing verified"}
    entry = next((e for c, e in loaded.agents.items() if calling_card.same(c, card)), None)
    declared = list(entry.keys) if entry else []
    when_t = accepted_at or datetime.datetime.now(datetime.timezone.utc)
    keys = [k.key for k in declared
            if k.valid_at(when_t) and (accepted_at is not None or not k.retired)]
    if not declared:
        return {**verdict, "trust": TrustClass.UNVERIFIED.value, "keys_declared": 0,
                "reason": f"{card} is not in the operator's registry; nothing can be concluded"}
    if not message.signature:
        return {**verdict, "trust": TrustClass.SUSPECT.value, "keys_declared": len(declared),
                "reason": f"{card} is registered and this message is unsigned"}
    when = ("at the broker's acceptance" if accepted_at is not None
            else "now (no record of acceptance, so no retired key counts)")
    if not verify(message, message.signature, keys):
        return {**verdict, "trust": TrustClass.SUSPECT.value, "keys_declared": len(declared),
                "reason": f"the signature verifies against no key valid for {card} {when}"}
    others = sorted(c for c, e in loaded.agents.items()
                    if e.account == entry.account and not calling_card.same(c, card))
    account = entry.account
    if others:
        return {**verdict, "trust": TrustClass.ATTESTED.value, "keys_declared": len(declared),
                "attests": "login", "shared_with": others,
                "reason": (f"attested on a shared login: account {account} also holds the keys of "
                           f"{', '.join(others)}, so any of them could have signed")}
    return {**verdict, "trust": TrustClass.ATTESTED.value, "keys_declared": len(declared),
            "attests": "agent", "reason": f"signature verified against a key valid for {card} {when}"}
