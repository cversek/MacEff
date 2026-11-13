"""One capture unit for several agents (MIS-0008 6.8): who it listens for, and the check that no two
agents can be woken or keyed the same way (R26).

The shared capture unit runs on a system daemon and serves each member agent that declares a voice
section. A phrase or key two agents share would wake whichever one the unit happened to match, so
the unit refuses that whole set of members at load, naming each clash, rather than guessing.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, Iterable, List, Optional

from macf import calling_card
from macf.voice.dispatch import sign_utterance, sign_voice_event, voice_topic


class MembersRefused(ValueError):
    """Two member agents declare the same wake phrase or the same key."""


def _phrase(text: str) -> str:
    return " ".join("".join(c for c in text.lower() if c.isalnum() or c.isspace()).split())


def check_members(sections: Dict[str, object]) -> None:
    """Refuse members whose wake phrases or keys clash (R26). ``sections`` maps each member's card
    to its voice section. Phrases compare as words, ignoring case and punctuation; a key clashes
    whether it is one agent's hold key and another's toggle key or the same role in both."""
    clashes: List[str] = []
    phrases: Dict[str, str] = {}
    keys: Dict[str, str] = {}
    for card, section in sorted(sections.items()):
        if section.wake_phrase:
            phrase = _phrase(section.wake_phrase)
            if phrase in phrases:
                clashes.append(f"{card} and {phrases[phrase]} both declare the wake phrase {phrase!r}")
            else:
                phrases[phrase] = card
        for key in (section.hold_key, section.toggle_key):
            if not key:
                continue
            if key in keys and keys[key] != card:
                clashes.append(f"{card} and {keys[key]} both declare the key {key}")
            else:
                keys[key] = card
    if clashes:
        raise MembersRefused("one capture unit can't tell these agents apart (MIS-0008 R26): " + "; ".join(clashes))


class DispatchSender:
    """The system capture unit's ``deliver``: each utterance signed for the agent whose phrase or key
    opened it (R47, R48) and published on that agent's own voice topic, never retained, since a
    retained message would be replayed to the member on every reconnect (MIS-0007 R67).

    ``publish(topic, payload)`` is the system daemon's link to its own broker; it returns whether
    the client queued the message, not that the member got it: the member's receipt says that, and
    one queued while the link was down is refused as expired if it arrives past its lifetime.
    ``now`` is the wall clock the expiry is counted from."""

    def __init__(self, signer: str, private, capture_unit: str, members: Iterable[str],
                 publish: Callable[[str, bytes], bool], *, lifetime_s: float, now: Callable[[], float] = time.time,
                 log: Callable[[str], None] = lambda s: None):
        self.signer, self.private, self.capture_unit = signer, private, capture_unit
        self.members = {calling_card.lowercase(m): m for m in members}
        self.publish, self.lifetime_s, self.now, self.log = publish, lifetime_s, now, log

    def __call__(self, utterance) -> Optional[str]:
        """Sign and send one utterance; its nonce, or None when it went nowhere, said in the log
        so the speech never vanishes silently (MIS-0007 R60)."""
        target = self.members.get(calling_card.lowercase(utterance.agent)) if utterance.agent else None
        if target is None:
            self.log(f"an utterance for {utterance.agent or 'no agent'}, which this unit doesn't serve: not sent")
            return None
        env = sign_utterance(signer=self.signer, target=target, private=self.private, now=self.now(),
                             lifetime_s=self.lifetime_s, trigger=utterance.trigger, spoken_at=utterance.spoken_at,
                             screen=utterance.screen, voice_lock=utterance.voice_lock,
                             capture_unit=self.capture_unit, text=utterance.text)
        if not self.publish(voice_topic(target), env.model_dump_json().encode()):
            self.log(f"the broker didn't take the utterance for {target}: not sent")
            return None
        return env.nonce

    def voice_event(self, agent: str, kind: str, data: dict) -> Optional[str]:
        """A member's voice lock failed or locked out: told to that member by the same signed route,
        counts and a time only (R37, R39). This is the binding's ``on_voice_event``."""
        target = self.members.get(calling_card.lowercase(agent))
        if target is None:
            self.log(f"a voice event for {agent}, which this unit doesn't serve: not sent")
            return None
        env = sign_voice_event(signer=self.signer, target=target, private=self.private, now=self.now(),
                               lifetime_s=self.lifetime_s, kind=kind, attempts=data.get("attempts"),
                               of=data.get("of"), until=data.get("until"))
        if not self.publish(voice_topic(target), env.model_dump_json().encode()):
            self.log(f"the broker didn't take the voice event for {target}: not sent")
            return None
        return env.nonce
