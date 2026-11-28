"""What an agent's speech says aloud: text made fit to hear, words respelled, sentences split
(MIS-0008 6.6).

Code and markdown read badly aloud, so they are dropped or flattened. A speech engine says some
names wrong; the agent's pronunciation table respells them the way the engine says them right.
Sentences are spoken one at a time, so the first is heard while the rest are still being made.
"""
from __future__ import annotations

import re
from typing import Dict, List

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_LINE_MARK = re.compile(r"^\s*[#>*-]+\s*", re.M)


def clean(text: str, table: Dict[str, str] = None) -> str:
    """What should be heard: code blocks named, not read; links by their words; marks dropped."""
    text = _FENCE.sub(" code block omitted. ", text)
    text = _INLINE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _URL.sub(" a link ", text)
    text = _LINE_MARK.sub("", text)
    text = text.replace("**", "").replace("*", "")
    return respell(re.sub(r"[ \t]+", " ", text).strip(), table or {})


def respell(text: str, table: Dict[str, str]) -> str:
    """Replace each listed word, its case exactly as listed, longest first. A word counts only
    standing alone: after whitespace or a line start, and before whitespace, common punctuation or
    a line end. So "Ira." and "Ira's" are respelled, and "MacEff-Ira" and "Irate" are not."""
    for word in sorted(table, key=len, reverse=True):
        text = re.sub(rf"(?<!\S){re.escape(word)}(?=[\s.,!?;:'\")\]]|$)", table[word], text, flags=re.M)
    return text


def sentences(text: str) -> List[str]:
    """Split where a sentence or a line ends, keeping the punctuation with its sentence."""
    return [s.strip() for s in re.split(r"(?<=[.!?:;])\s+|\n+", text) if s.strip()]
