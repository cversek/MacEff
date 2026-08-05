"""Per-correspondent authorship signing.

amail v1.0 §8 deferred this, and gave the right reason: "signing without key
custody and rotation is ceremony, and key management deserves its own decision
rather than being smuggled in beneath a mail spec." This module is that
decision, made deliberately rather than assumed.

WHY NOT DKIM. DKIM is already public-key authentication, already deployed, and
already understood — and it authenticates the wrong thing. Its `d=` tag names a
SIGNING DOMAIN. Every agent under one mail domain shares that domain's key, so
a DKIM signature proves a message passed through some infrastructure, not which
correspondent composed it. A contact book that names CORRESPONDENTS cannot be
enforced by a mechanism that authenticates domains. §5.3 already says this in
prose; this module is what it looks like when acted on.

WHO HOLDS WHAT, which is the decision that carries the design:

    Agents hold their own PRIVATE signing keys, mode 600, in their own homes.
    The broker holds only PUBLIC keys, in the contact book.

That looks like it contradicts "a compromised agent holds no credential" and
does not. A signing key is not a TRANSPORT credential. Holding one lets an agent
prove it is itself; it does not let the agent reach the internet, does not let
it reach an unlisted recipient, and does not let it sign as anyone else — the
signature would fail against that correspondent's public key, and the broker
refuses a sender that disagrees with SO_PEERCRED long before it gets there. A
compromised agent can strip its own signature, which makes its own mail
unverified. That is self-harm, not an attack.

What this buys over broker-held keys: a signature proves authorship EVEN TO A
PARTY THAT DOES NOT TRUST THE BROKER. If the broker held private keys it could
forge any agent's mail, and §7.2 already concedes a compromised broker is
undefended. This narrows that concession for authorship specifically, which is
the one place it is cheap to narrow.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

#: The only algorithm this version accepts. An algorithm field that accepts
#: several is an algorithm field an attacker gets to choose from — including
#: "none", which is how JWT implementations were broken for years. One
#: algorithm, named in the key, and anything else is refused.
ALGORITHM = "ed25519"


class SigningError(ValueError):
    """Raised when a key cannot be used. Never degrade to sending unsigned."""


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def signing_payload(message: Any) -> bytes:
    """The exact bytes a signature covers.

    Canonical JSON — sorted keys, no insignificant whitespace — so that two
    implementations that agree on the FIELDS cannot disagree on the BYTES. A
    signature scheme whose payload depends on dict ordering verifies on the
    machine that produced it and nowhere else.

    The body is covered BY HASH rather than by value. Two reasons, and the
    second is the one that matters: a signature can then be checked without
    re-transmitting the body, and — because the broker truncates an oversize
    body at MAX_BODY — a truncated body produces a hash mismatch instead of
    silently verifying against text the sender never wrote.

    Transport headers are deliberately excluded. §5.3: they belong to the
    journey, not the message, and a signature over them would break the moment
    a relay touched anything.

    MESSAGE_ID AND DATE ARE DELIBERATELY NOT COVERED, and the reason is a
    conflict between two rules that both have to hold. The broker RE-MINTS both
    on inbound, because a remote-chosen message_id shadows a real message in
    find() and a remote-chosen date controls the reader's ordering. Covering
    them would therefore mean every inbound signature verified once at ingress
    and never again — the stored message could not be re-checked by anyone,
    because the fields it committed to had been replaced by the time it landed.
    That would make the broker the sole and unrepeatable verifier, and the point
    of end-to-end signing is precisely to not need that.

    So the payload covers what the message IS — who wrote it, who it is for,
    what it says — and not the identifiers assigned to it in transit. The stored
    message remains verifiable by anyone holding the correspondent's public key.

    The cost, stated plainly rather than hidden: a captured message can be
    re-delivered and will still verify. That is replay, not forgery — the
    content is genuinely from that correspondent — and it is recorded as
    undefended in the threat model rather than papered over here.
    """
    return json.dumps({
        "alg": ALGORITHM,
        "sender": message.sender,
        "to": list(message.to),
        "subject": message.subject or "",
        "body_sha256": hashlib.sha256((message.body or "").encode("utf-8")).hexdigest(),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_private_key(path: Path) -> Ed25519PrivateKey:
    """Load an agent's own signing key, refusing one anyone else can read.

    The same custody argument the transport credential gets, for the same
    reason: a private key another uid can read is a private key another uid
    can sign with, and every guarantee downstream of the signature becomes a
    guarantee about who could read a file.
    """
    p = Path(path)
    if not p.exists():
        raise SigningError(f"no signing key at {p}")
    mode = p.stat().st_mode
    if mode & (stat.S_IRGRP | stat.S_IROTH):
        raise SigningError(
            f"signing key {p} is readable by group or other. Anyone who can read "
            "it can sign as this agent. Refusing to use it; chmod 600 and retry."
        )
    if p.stat().st_uid != os.getuid():
        raise SigningError(
            f"signing key {p} is owned by uid {p.stat().st_uid}, not by this "
            f"process (uid {os.getuid()}). Refusing to use it."
        )
    try:
        key = serialization.load_pem_private_key(p.read_bytes(), password=None)
    except Exception as e:  # noqa: BLE001 - any parse failure is a refusal
        raise SigningError(f"signing key {p} could not be read: {e}") from e
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningError(
            f"signing key {p} is not Ed25519. This version signs with {ALGORITHM} "
            "only; accepting several algorithms means an attacker picks one."
        )
    return key


def parse_public_key(declared: str) -> Ed25519PublicKey:
    """Parse an `ed25519:<base64>` public key from a contact entry."""
    text = (declared or "").strip()
    prefix = f"{ALGORITHM}:"
    if not text.startswith(prefix):
        raise SigningError(
            f"contact key must begin with '{prefix}' — got {text[:16]!r}. The "
            "algorithm is named in the key so a message can never choose it."
        )
    try:
        raw = _unb64(text[len(prefix):])
    except Exception as e:  # noqa: BLE001
        raise SigningError(f"contact key is not valid base64: {e}") from e
    try:
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception as e:  # noqa: BLE001
        raise SigningError(f"contact key is not a valid Ed25519 public key: {e}") from e


def public_key_line(private: Ed25519PrivateKey) -> str:
    """The contact-entry form of a private key's public half."""
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    return f"{ALGORITHM}:{_b64(raw)}"


def generate_keypair(path: Path) -> str:
    """Write a new private key at `path` (mode 600); return the public line."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())
    # O_EXCL: never silently overwrite an existing key. Overwriting one
    # invalidates every signature the correspondent has already published, and
    # doing it by accident is indistinguishable from doing it maliciously.
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    return public_key_line(key)


def sign(message: Any, private: Ed25519PrivateKey) -> str:
    return _b64(private.sign(signing_payload(message)))


def verify(message: Any, signature: str, public_keys: List[str]) -> bool:
    """True when `signature` verifies against ANY of the correspondent's keys.

    A list rather than one key so a correspondent can rotate: publish the new
    key alongside the old, let in-flight mail verify, then drop the old one.
    Rotation that requires a flag day is rotation that never happens, and a key
    that is never rotated is the one that eventually leaks.

    Returns False rather than raising on a bad signature. A forged signature is
    an expected input here, not an exceptional one — this function's whole job
    is to be handed them.
    """
    if not signature or not public_keys:
        return False
    try:
        raw = _unb64(signature)
    except Exception:  # noqa: BLE001
        return False
    payload = signing_payload(message)
    for declared in public_keys:
        try:
            parse_public_key(declared).verify(raw, payload)
            return True
        except (InvalidSignature, SigningError):
            continue
        except Exception:  # noqa: BLE001 - a malformed key is not a pass
            continue
    return False
