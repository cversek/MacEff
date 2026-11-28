"""Choosing an agent's voice with its operator (MIS-0008 R30, R31; the ``voice_generation`` policy).

The agent infers a few traits for its voice from its own identity and role, and puts them to the
operator before anything is generated (R31). From the agreed traits this module proposes candidate
settings; each speaks the same line through the speech worker; the operator picks or steers; and
the choice is written into the agent's voice section with the traits behind it (R30).

The trait-to-voice mapping is deliberately simple: a first version for the working prototype to
improve on. It reads accent and timbre words to rank the engine's voices, pace words to set the
speed, and always offers a blend of the two best.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

from macf.voice.state import voice_dir

#: Kokoro's voices this mapping knows, with what each sounds like. Prefix: a/b for American or
#: British, m/f for a male or female voice.
VOICES: Dict[str, str] = {
    "am_michael": "steady warm mid", "am_onyx": "deep low calm", "am_adam": "plain mid", "am_eric": "bright brisk",
    "am_fenrir": "deep gravelly strong", "am_liam": "young light", "am_puck": "playful bright",
    "am_echo": "soft calm", "bm_george": "deep measured formal", "bm_lewis": "warm low", "bm_daniel": "crisp formal",
    "bm_fable": "storyteller warm", "af_heart": "warm bright", "af_bella": "bright lively", "af_sarah": "calm clear",
    "af_nicole": "soft calm", "bf_emma": "crisp clear", "bf_isabella": "warm measured", "bf_alice": "light bright",
}
ACCENT = {"british": "b", "english": "b", "american": "a"}
PACE = {"calm": -0.05, "measured": -0.05, "steady": -0.03, "slow": -0.1, "deliberate": -0.05,
        "brisk": 0.07, "quick": 0.1, "energetic": 0.08, "lively": 0.05}
LINE = "Hello. This is how I would sound reading you a short update, so listen for whether it suits me."


@dataclass(frozen=True)
class Candidate:
    number: int
    voice: str
    speed: float


def _words(traits: List[str]) -> List[str]:
    return [w for t in traits for w in t.lower().replace(",", " ").split()]


def candidates(traits: List[str], count: int = 4) -> List[Candidate]:
    """Settings to try for these traits: the best-matching voices, then a blend of the top two."""
    words = _words(traits)
    accent = next((ACCENT[w] for w in words if w in ACCENT), None)
    gender = "f" if any(w in ("female", "woman", "feminine") for w in words) else (
        "m" if any(w in ("male", "man", "masculine") for w in words) else None)
    speed = round(min(1.3, max(0.8, 1.0 + sum(PACE.get(w, 0.0) for w in words))), 2)

    def score(name: str) -> float:
        s = sum(1.0 for w in words if w in VOICES[name].split())
        s += 0.5 if accent and name[0] == accent else 0.0
        s += 0.5 if gender and name[1] == gender else 0.0
        return s

    ranked = sorted(VOICES, key=lambda n: (-score(n), n))
    singles = [Candidate(i + 1, name, speed) for i, name in enumerate(ranked[:max(1, count - 1)])]
    blend = Candidate(len(singles) + 1, f"{ranked[0]}:0.6,{ranked[1]}:0.4", speed)
    return singles + [blend]


def candidates_path(home: Path) -> Path:
    return voice_dir(home) / "speech" / "candidates.json"


def keep_candidates(home: Path, traits: List[str], found: List[Candidate]) -> None:
    path = candidates_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"traits": traits, "made_at": time.time(),
                                "candidates": [asdict(c) for c in found]}, indent=1) + "\n")


class ChoiceRefused(ValueError):
    """The choice can't be recorded, with the reason."""


def record_choice(home: Path, number: int) -> dict:
    """Write the chosen candidate, with the traits it was made from, into the voice section (R30).

    Only the agent's own declaration in its home is written, and only if the result still loads;
    a declaration rendered by the operator's tooling is the operator's to change."""
    from macf.pd.interface import Declaration, SpeechSettings
    from macf.pd.names import declaration_path, rendered_declaration_path
    path = candidates_path(home)
    if not path.exists():
        raise ChoiceRefused("no candidates have been made; run voice select samples first")
    made = json.loads(path.read_text())
    chosen = next((c for c in made["candidates"] if c["number"] == number), None)
    if chosen is None:
        raise ChoiceRefused(f"there is no candidate {number}; the candidates are 1 to {len(made['candidates'])}")
    if rendered_declaration_path(home).exists():
        raise ChoiceRefused("this agent's declaration is rendered by the operator's tooling; give the operator "
                            "the speech settings to add")
    target = declaration_path(home)
    raw = json.loads(target.read_text())
    if not raw.get("voice"):
        raise ChoiceRefused("the declaration has no voice section; add one, naming the capture unit, first")
    speech = SpeechSettings(voice=chosen["voice"], speed=chosen["speed"], traits=made["traits"],
                            chosen_at=time.time(),
                            **{k: v for k, v in (raw["voice"].get("speech") or {}).items()
                               if k in ("lang", "fx", "while_locked", "engine")})
    raw["voice"]["speech"] = speech.model_dump()
    Declaration.model_validate(raw)       # refuse whole rather than write a declaration that won't load
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(raw, indent=2) + "\n")
    tmp.replace(target)
    return raw["voice"]["speech"]
