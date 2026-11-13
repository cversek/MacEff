"""One capture unit for several agents (MIS-0008 6.8): who it listens for, and the check that no two
agents can be woken or keyed the same way (R26).

The shared capture unit runs on a system daemon and serves each member agent that declares a voice
section. A phrase or key two agents share would wake whichever one the unit happened to match, so
the unit refuses that whole set of members at load, naming each clash, rather than guessing.
"""
from __future__ import annotations

from typing import Dict, List

from macf.pd.interface import VoiceSection


class MembersRefused(ValueError):
    """Two member agents declare the same wake phrase or the same key."""


def _phrase(text: str) -> str:
    return " ".join("".join(c for c in text.lower() if c.isalnum() or c.isspace()).split())


def check_members(sections: Dict[str, VoiceSection]) -> None:
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
