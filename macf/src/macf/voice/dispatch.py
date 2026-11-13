"""Utterances a system's capture unit sends down to a member agent (MIS-0008 R46 to R50).

One capture unit on a system daemon serves every member agent that declares voice. An utterance it
takes for a member goes down the association to that member's primal daemon, which is the only
thing that ever travels down one. MIS-0007 allows exactly this: the operator's own input, signed,
on a route declared for it, and verified by the primal daemon where it acts (MIS-0007 R29, R52 to
R57). This module is that input's signed form, and the member's check of it.

WHO SIGNS. The system daemon runs as an account no agent runs as, so its key is out of every
agent's reach (MIS-0007 R53). Its public key is declared in the operator's registry, the root-owned
file only the operator writes, under the system daemon's card. A member verifies against the keys
the registry holds for the card its own declaration names as its dispatcher, so no agent can make
itself a dispatcher, and no dispatcher a member didn't name can reach it.

WHAT THE SIGNATURE COVERS. Everything but the signature: the target member, the signer, when it was
issued and when it expires, a nonce, the closed metadata and the words. A field outside the
signature would be a field a door or broker could rewrite, and the target and freshness are what
stop a captured utterance being replayed later or to another agent (MIS-0007 R55).

WHAT THE MEMBER CHECKS, in this order, each a refusal it records:
  1. a retained message is dropped before anything else is read: a retained message on a down
     path is redelivered on every reconnect (MIS-0007 R67's reasoning);
  2. the shape, closed: an unknown field or value is refused whole;
  3. the signer is the dispatcher the member declared, and the registry holds a key for it;
  4. the signature verifies against one of those keys;
  5. the target is this member;
  6. it hasn't expired, compared as an instant with a declared clock allowance (MIS-0007 R57);
  7. its expiry is no further off than the member accepts, or the nonce record would have to keep
     its nonce for as long as a sender chose;
  8. its nonce wasn't accepted before (MIS-0007 R55). The record of accepted nonces survives the
     member daemon's restart, kept in its log until each expiry passes (MIS-0007 R56).
The signature is checked before anything else decides, so a refusal's reason is only ever read
from a message the dispatcher signed, except for the shape and the signer it claims.
"""
from __future__ import annotations

import base64
import binascii
import json
import secrets
from dataclasses import dataclass
from typing import Annotated, Callable, Dict, Iterable, List, Literal, Optional, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

from macf import calling_card
from macf.amail.crypto import SigningError, parse_public_key
from macf.pd import association as assoc
from macf.pd import broker as b
from macf.pd.interface import (CAPTURE_UNIT_NAME, MAX_UTTERANCE_TEXT, UtteranceScreen, UtteranceTrigger,
                               UtteranceVoiceLock)

ALGORITHM = "ed25519"
#: How long a dispatched utterance stays valid unless the system declaration says otherwise. Short:
#: dictation is about now, and a member that was down past it shows the utterance as expired.
DEFAULT_LIFETIME_S = 30.0
#: The longest expiry a member accepts unless its voice section says otherwise.
DEFAULT_MAX_LIFETIME_S = 120.0
#: How far apart the signer's and the member's clocks may be, unless declared (MIS-0007 R57).
DEFAULT_CLOCK_ALLOWANCE_S = 5.0
#: The largest message a member reads. An utterance's text is bounded, so anything past this is
#: not an utterance.
MAX_PAYLOAD = 4 * MAX_UTTERANCE_TEXT + 4096

Verdict = Literal["accepted", "retained", "malformed", "unknown_signer", "bad_signature", "wrong_target",
                  "expired", "expiry_too_far", "replayed"]


def voice_topic(card: str) -> str:
    """The topic a member's dispatched utterances arrive on, on its system daemon's broker. Only the
    system daemon writes it and only that member reads it (R49)."""
    return f"voice/{b.topic_name(card)}/in"


def receipt_topic(card: str) -> str:
    """Where a member says how each dispatched utterance ended: its own subtree, which only it may
    write, carrying no words (MIS-0007 R60)."""
    return assoc.member_topic(card, "voice/receipt")


def new_nonce() -> str:
    return secrets.token_hex(16)


class _Signed(BaseModel):
    """What every message down to a member carries: who signed it, who it is for, when it was
    issued and expires, and its nonce. Closed: a field nobody declared is refused rather than
    ignored, since it would be one the signature didn't cover in a reader that skipped it. Each
    kind signs its own fields, so one kind's signature doesn't verify as another's; the ``type`` it
    adds is signed too, so that stays true if two kinds ever share every field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    v: Literal[1] = 1
    alg: Literal["ed25519"] = ALGORITHM
    signer: str
    target: str
    issued_at: float = Field(allow_inf_nan=False)
    expires_at: float = Field(allow_inf_nan=False)
    nonce: str = Field(pattern=r"^[0-9a-f]{32}$")
    signature: str = ""

    @field_validator("signer", "target")
    @classmethod
    def _a_card(cls, v: str) -> str:
        try:
            return calling_card.read_declared(v)
        except calling_card.CardError as e:
            raise ValueError(str(e)) from e

    @model_validator(mode="after")
    def _expires_after_issue(self) -> "_Signed":
        if self.expires_at <= self.issued_at:
            raise ValueError("a dispatched message must expire after it was issued")
        return self


class DispatchedUtterance(_Signed):
    """One utterance, signed, on its way down to the member it is for (R48)."""

    type: Literal["utterance"] = "utterance"
    trigger: UtteranceTrigger
    spoken_at: float = Field(allow_inf_nan=False)
    screen: UtteranceScreen
    voice_lock: UtteranceVoiceLock
    capture_unit: str = Field(pattern=CAPTURE_UNIT_NAME)
    text: str = Field(min_length=1, max_length=MAX_UTTERANCE_TEXT)


class DispatchedVoiceEvent(_Signed):
    """The system's capture unit telling a member its voice lock failed, or locked voice contact
    with it out (R37, R39), by the same route as an utterance: counts and a time, never anything
    that was said."""

    type: Literal["voice_event"] = "voice_event"
    kind: Literal["unmatched", "lockout"]
    attempts: Optional[int] = Field(default=None, ge=1, le=1000)
    of: Optional[int] = Field(default=None, ge=1, le=1000)
    until: Optional[float] = Field(default=None, allow_inf_nan=False)


Dispatched = Union[DispatchedUtterance, DispatchedVoiceEvent]
_DISPATCHED = TypeAdapter(Annotated[Dispatched, Field(discriminator="type")])


def signing_payload(envelope: Dispatched) -> bytes:
    """The exact bytes the signature covers: every field but the signature, as canonical JSON, so
    two builds that agree on the fields can't disagree on the bytes."""
    fields = envelope.model_dump(mode="json", exclude={"signature"})
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_utterance(*, signer: str, target: str, private: Ed25519PrivateKey, now: float, lifetime_s: float,
                   trigger: str, spoken_at: float, screen: str, voice_lock: str, capture_unit: str, text: str,
                   nonce: Optional[str] = None) -> DispatchedUtterance:
    """An utterance for ``target``, signed by ``signer``'s key, valid for ``lifetime_s`` from ``now``."""
    unsigned = DispatchedUtterance(signer=signer, target=target, issued_at=now, expires_at=now + lifetime_s,
                                   nonce=nonce or new_nonce(), trigger=trigger, spoken_at=spoken_at,
                                   screen=screen, voice_lock=voice_lock, capture_unit=capture_unit, text=text)
    return _signed(unsigned, private)


def sign_voice_event(*, signer: str, target: str, private: Ed25519PrivateKey, now: float, lifetime_s: float,
                     kind: str, attempts: Optional[int] = None, of: Optional[int] = None,
                     until: Optional[float] = None, nonce: Optional[str] = None) -> DispatchedVoiceEvent:
    """A voice-lock event for ``target``, signed like an utterance."""
    unsigned = DispatchedVoiceEvent(signer=signer, target=target, issued_at=now, expires_at=now + lifetime_s,
                                    nonce=nonce or new_nonce(), kind=kind, attempts=attempts, of=of, until=until)
    return _signed(unsigned, private)


def _signed(unsigned, private: Ed25519PrivateKey):
    signature = base64.b64encode(private.sign(signing_payload(unsigned))).decode("ascii")
    return unsigned.model_copy(update={"signature": signature})


def signature_verifies(envelope: Dispatched, keys: Iterable[str]) -> bool:
    """True when the signature verifies against any of ``keys``; a key that won't parse verifies
    nothing. Never raises: a forged signature is an expected input here."""
    try:
        raw = base64.b64decode(envelope.signature.encode("ascii"), validate=True)
    except (binascii.Error, ValueError):
        return False
    payload = signing_payload(envelope)
    for key in keys:
        try:
            parse_public_key(key).verify(raw, payload)
            return True
        except (SigningError, InvalidSignature, ValueError):
            continue  # noqa: MACEFF003 - one key not verifying is why the next is tried; none verifying is the False below
    return False


class NonceRecord:
    """The nonces a member accepted, each kept until its utterance's expiry has passed, allowance
    included (MIS-0007 R55, R56). In memory for the checks, rebuilt at start from the member's
    log, where each acceptance is recorded, so a restart never forgets one still in force."""

    def __init__(self) -> None:
        self._until: Dict[str, float] = {}

    def __len__(self) -> int:
        return len(self._until)

    def seen(self, nonce: str, now: float) -> bool:
        until = self._until.get(nonce)
        return until is not None and now <= until

    def add(self, nonce: str, keep_until: float) -> None:
        self._until[nonce] = max(keep_until, self._until.get(nonce, keep_until))

    def prune(self, now: float) -> None:
        """Forget nonces whose utterances can no longer pass the expiry check anyway."""
        self._until = {n: t for n, t in self._until.items() if t >= now}

    @classmethod
    def from_events(cls, events: Iterable[dict], card: str, allowance_s: float) -> "NonceRecord":
        """The record as the log has it: every accepted nonce for ``card``. Expired ones are pruned
        by the first check, so a long log costs one pass at start."""
        record = cls()
        for event in events:
            data = event.get("data") or {}
            if data.get("verdict") != "accepted" or not calling_card.is_card(str(data.get("agent", ""))):
                continue
            if not calling_card.same(str(data["agent"]), card):
                continue
            nonce, expires_at = data.get("nonce"), data.get("expires_at")
            if isinstance(nonce, str) and isinstance(expires_at, (int, float)):
                record.add(nonce, float(expires_at) + allowance_s)
        return record


@dataclass(frozen=True)
class Check:
    """A member's verdict on one message: ``envelope`` is set whenever the shape was read, so the
    refusal can be recorded by its metadata."""

    verdict: Verdict
    reason: str = ""
    envelope: Optional[Dispatched] = None

    @property
    def accepted(self) -> bool:
        return self.verdict == "accepted"


class Verifier:
    """A member's check of what arrives on its voice topic (R48, R50).

    ``dispatcher`` is the card its voice section names; ``keys(card)`` reads the registry's keys
    valid now for a card. ``nonces`` is the record of accepted nonces, which the caller rebuilds
    from the log at start.
    """

    def __init__(self, card: str, dispatcher: str, keys: Callable[[str], List[str]], *,
                 nonces: Optional[NonceRecord] = None, allowance_s: float = DEFAULT_CLOCK_ALLOWANCE_S,
                 max_lifetime_s: float = DEFAULT_MAX_LIFETIME_S):
        self.card, self.dispatcher, self.keys = card, dispatcher, keys
        self.nonces = nonces if nonces is not None else NonceRecord()
        self.allowance_s, self.max_lifetime_s = allowance_s, max_lifetime_s

    def check(self, payload: bytes, *, retained: bool, now: float) -> Check:
        if retained:
            return Check("retained", "a retained message on the voice topic is dropped unread: the broker would "
                                     "replay it on every reconnect (MIS-0007 R67)")
        if len(payload) > MAX_PAYLOAD:
            return Check("malformed", f"{len(payload)} bytes is longer than any utterance")
        try:
            env = _DISPATCHED.validate_json(payload)
        except ValidationError as e:
            return Check("malformed", f"not a dispatched utterance or voice event ({e.error_count()} problem(s))")
        if not calling_card.same(env.signer, self.dispatcher):
            return Check("unknown_signer", f"signed as {env.signer}, but this agent's voice comes only from "
                                           f"{self.dispatcher}", env)
        try:
            keys = self.keys(self.dispatcher)
        except (OSError, ValueError) as e:      # RegistryError is a ValueError
            return Check("unknown_signer", f"the operator's registry can't be read, so no key verifies: {e}", env)
        if not keys:
            return Check("unknown_signer", f"the operator's registry holds no key valid now for {self.dispatcher}",
                         env)
        if not signature_verifies(env, keys):
            return Check("bad_signature", f"the signature doesn't verify against {self.dispatcher}'s keys", env)
        if not calling_card.same(env.target, self.card):
            return Check("wrong_target", f"signed for {env.target}, not this agent", env)
        if now > env.expires_at + self.allowance_s:
            return Check("expired", f"expired {now - env.expires_at:.1f} s ago, past the "
                                    f"{self.allowance_s:g} s clock allowance (MIS-0007 R57)", env)
        if env.expires_at - now > self.max_lifetime_s + self.allowance_s:
            return Check("expiry_too_far", f"its expiry is {env.expires_at - now:.0f} s off; this agent accepts "
                                           f"at most {self.max_lifetime_s:g} s", env)
        self.nonces.prune(now)
        if self.nonces.seen(env.nonce, now):
            return Check("replayed", "its nonce was accepted before (MIS-0007 R55)", env)
        self.nonces.add(env.nonce, env.expires_at + self.allowance_s)
        return Check("accepted", "", env)
