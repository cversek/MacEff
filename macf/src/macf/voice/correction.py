"""Domain term correction for voice transcripts.

Zero-dependency fuzzy matching that corrects misheard MACF jargon
without requiring an LLM API. Uses Levenshtein distance + phonetic
similarity to match Whisper output against known vocabulary.

Examples:
  "Jotur" → "JOTEWR"
  "EPIS dock" → "EPIST_DOC"
  "Manny Mika F" → "MannyMacEff"
  "the mini rename" → "demini-rename"
"""

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .vocabulary import PRIORITY_TERMS, extract_vocabulary


@dataclass
class Correction:
    """A single term correction with confidence."""
    original: str
    corrected: str
    confidence: float
    position: int  # char offset in text


@dataclass
class CorrectedTranscript:
    """Transcript with corrections applied."""
    original_text: str
    corrected_text: str
    corrections: list
    method: str = "fuzzy_match"

    def to_dict(self):
        return {
            "original_text": self.original_text,
            "corrected_text": self.corrected_text,
            "corrections": [asdict(c) for c in self.corrections],
            "method": self.method,
        }


def levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,
                prev_row[j + 1] + 1,
                prev_row[j] + cost,
            ))
        prev_row = curr_row

    return prev_row[-1]


def phonetic_key(word: str) -> str:
    """Simple phonetic key — reduces word to consonant skeleton.

    Not a full Soundex/Metaphone, but catches common speech-to-text
    confusions like: JOTEWR→Jotur, MACF→MacF, demini→the mini.
    """
    word = word.upper()
    # Remove vowels (except leading), collapse doubles
    if not word:
        return ""
    result = [word[0]]
    for c in word[1:]:
        if c not in 'AEIOU' and c != result[-1]:
            result.append(c)
    return ''.join(result)


def normalized_similarity(s1: str, s2: str) -> float:
    """Compute normalized similarity (0-1) between two strings.

    Combines case-insensitive Levenshtein with phonetic matching.
    """
    s1_lower = s1.lower()
    s2_lower = s2.lower()

    # Exact match (case-insensitive)
    if s1_lower == s2_lower:
        return 1.0

    # Levenshtein similarity
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    lev_dist = levenshtein(s1_lower, s2_lower)
    lev_sim = 1.0 - (lev_dist / max_len)

    # Phonetic similarity bonus
    pk1 = phonetic_key(s1)
    pk2 = phonetic_key(s2)
    if pk1 == pk2:
        phonetic_bonus = 0.2
    elif pk1 and pk2:
        pk_max = max(len(pk1), len(pk2))
        pk_dist = levenshtein(pk1, pk2)
        phonetic_bonus = 0.1 * (1.0 - pk_dist / pk_max)
    else:
        phonetic_bonus = 0.0

    return min(1.0, lev_sim + phonetic_bonus)


def _load_fusion_patterns() -> dict:
    """Load fusion patterns from local JSON data file.

    Patterns are kept in a separate data file (not version controlled)
    to isolate domain-specific vocabulary from generic correction code.
    Returns empty dict if file not found (graceful degradation).
    """
    patterns_file = Path(__file__).parent / "fusion_patterns.json"
    if not patterns_file.exists():
        return {}
    try:
        data = json.loads(patterns_file.read_text())
        # Remove metadata keys (starting with _)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except (json.JSONDecodeError, OSError):
        return {}


# Multi-word fusion patterns loaded from local data file
FUSION_PATTERNS = _load_fusion_patterns()


def correct_transcript(
    text: str,
    vocabulary: Optional[list] = None,
    threshold: float = 0.65,
) -> CorrectedTranscript:
    """Correct domain terms in a voice transcript using fuzzy matching.

    Args:
        text: Raw transcript from Whisper
        vocabulary: List of known domain terms (auto-extracted if None)
        threshold: Minimum similarity to consider a correction (0-1)

    Returns:
        CorrectedTranscript with original, corrected, and correction details
    """
    if vocabulary is None:
        vocabulary = extract_vocabulary()

    corrections = []
    corrected = text

    # Phase 1: Multi-word fusion patterns (case-insensitive)
    text_lower = corrected.lower()
    for pattern, replacement in sorted(FUSION_PATTERNS.items(), key=lambda x: len(x[0]), reverse=True):
        idx = text_lower.find(pattern)
        while idx != -1:
            original_span = corrected[idx:idx + len(pattern)]
            if original_span.lower() != replacement.lower():
                corrections.append(Correction(
                    original=original_span,
                    corrected=replacement,
                    confidence=0.95,
                    position=idx,
                ))
                corrected = corrected[:idx] + replacement + corrected[idx + len(pattern):]
                text_lower = corrected.lower()
            idx = text_lower.find(pattern, idx + len(replacement))

    # Phase 2: Single-word fuzzy matching against vocabulary
    # DISABLED (Cycle 505): Too aggressive — matches innocent English words
    # (string→STRONG, graph→TRAP, module→MODE, scope→SCOPE, please→PHASE)
    # Fusion patterns (Phase 1) are reliable. Single-word matching needs
    # LLM-backed correction (MISSION #314 Phase 3) to be safe.
    # Re-enable when LLM provider validates candidates before replacement.
    ENABLE_FUZZY_SINGLE_WORD = False

    if not ENABLE_FUZZY_SINGLE_WORD:
        return CorrectedTranscript(
            original_text=text,
            corrected_text=corrected,
            corrections=corrections,
            method="fusion_patterns_only",
        )

    COMMON_WORDS = {
        'the', 'and', 'for', 'not', 'but', 'all', 'are', 'has', 'was', 'can',
        'this', 'that', 'with', 'from', 'have', 'been', 'will', 'each', 'its',
        'also', 'into', 'over', 'such', 'than', 'them', 'then', 'just', 'our',
        'need', 'make', 'like', 'stop', 'check', 'three', 'tier', 'hook', 'uses',
        'mode', 'data', 'goes', 'through', 'switch', 'sure', 'create', 'forces',
        'block', 'needs', 'agent', 'sub', 'decision', 'format', 'default', 'cycle',
        'pipeline', 'transformations', 'continuation', 'rename',
    }

    vocab_set = {t.lower(): t for t in vocabulary}
    # Only match words 4+ chars that aren't common English
    word_pattern = re.compile(r'\b[A-Za-z_][A-Za-z0-9_-]{3,}\b')

    for match in word_pattern.finditer(corrected):
        word = match.group()
        word_lower = word.lower()

        # Skip common English words
        if word_lower in COMMON_WORDS:
            continue

        # Skip if already a known term
        if word_lower in vocab_set:
            continue

        # Find best matching vocabulary term
        # Require higher similarity for shorter words
        min_sim = threshold if len(word) >= 5 else 0.80
        best_term = None
        best_sim = 0.0

        for term in vocabulary:
            if len(term) < 4:
                continue
            # Skip if length difference is too large (unlikely match)
            if abs(len(term) - len(word)) > max(3, len(word) // 2):
                continue
            sim = normalized_similarity(word, term)
            if sim > best_sim and sim >= min_sim:
                best_sim = sim
                best_term = term

        if best_term and best_term.lower() != word_lower:
            corrections.append(Correction(
                original=word,
                corrected=best_term,
                confidence=best_sim,
                position=match.start(),
            ))
            corrected = corrected[:match.start()] + best_term + corrected[match.end():]

    return CorrectedTranscript(
        original_text=text,
        corrected_text=corrected,
        corrections=corrections,
        method="fuzzy_match",
    )
