"""Domain vocabulary extraction for Whisper initial_prompt conditioning.

Extracts terms from MACF standard paths (CLAUDE.md, policies, memories)
and compresses them into Whisper's 223-token initial_prompt budget.

Token budget (Whisper architecture constraint):
  n_text_ctx = 448, split half prompt / half output → 223 tokens max
  ~60 tokens: curated priority terms (always included)
  ~20 tokens: style-setting prefix
  ~100 tokens: dynamic terms from context
  ~40 tokens: safety margin
"""

import re
import sys
import os
from pathlib import Path
from typing import Optional


# High-priority MACF domain terms — always included in prompt
# These are the terms most likely to be misheard by Whisper
PRIORITY_TERMS = [
    # Framework
    "MACF", "MacEff", "macf_tools",
    # Consciousness artifacts
    "JOTEWR", "CCP", "BKG", "EPIST_DOC",
    # Tools and pipeline
    "demini", "demini-rename", "demini-split", "demini-bkg",
    # Agents and roles
    "ClaudeTheBuilder", "MannyMacEff", "DevOpsEng", "TestEng",
    # Concepts
    "breadcrumb", "compaction", "consciousness artifact",
    # Projects
    "NeuroFieldz", "neurovep", "VoxelCAD",
    # Protocol terms
    "DELEG_DRV", "DEV_DRV", "INST_LANG",
    # Mode/state
    "AUTO_MODE", "MANUAL_MODE", "YOLO BOZO",
]


def extract_terms_from_text(text: str) -> set:
    """Extract likely domain terms from text content.

    Finds:
    - ALL_CAPS acronyms (2+ chars): MACF, CCP, BKG
    - PascalCase compound words: ClaudeTheBuilder, MacEff
    - snake_CASE identifiers: AUTO_MODE, DEV_DRV
    """
    terms = set()

    # ALL_CAPS (2+ uppercase letters, may contain underscores)
    terms.update(re.findall(r'\b[A-Z][A-Z_]{1,}\b', text))

    # PascalCase (two+ capitalized segments)
    terms.update(re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text))

    # snake_CASE with uppercase (like AUTO_MODE, DEV_DRV)
    terms.update(re.findall(r'\b[A-Z][A-Z_]*_[A-Z][A-Z_]*\b', text))

    # Filter out common English/code words that happen to be ALL_CAPS
    noise = {
        # Common English words that happen to be ALL_CAPS in markdown/docs
        'THE', 'AND', 'FOR', 'NOT', 'BUT', 'ALL', 'ARE', 'HAS', 'WAS', 'CAN',
        'WHEN', 'WHAT', 'THIS', 'THAT', 'WITH', 'FROM', 'HAVE', 'BEEN', 'HOW',
        'WILL', 'YOUR', 'EACH', 'MUST', 'ONLY', 'ALSO', 'INTO', 'OVER', 'ANY',
        'SUCH', 'THAN', 'THEM', 'THEN', 'VERY', 'JUST', 'LIKE', 'MAKE', 'WHY',
        'DOES', 'DONE', 'USED', 'TRUE', 'FALSE', 'NULL', 'NONE', 'TODO', 'USE',
        'NOTE', 'IMPORTANT', 'CRITICAL', 'WARNING', 'ERROR', 'DEBUG', 'STOP',
        'README', 'CHANGELOG', 'LICENSE', 'VERSION', 'NEVER', 'ALWAYS', 'BOTH',
        'FIRST', 'AFTER', 'BEFORE', 'EVERY', 'SHOULD', 'WOULD', 'COULD',
        'CORRECT', 'WRONG', 'REQUIRED', 'OPTIONAL', 'DEFAULT', 'EXAMPLE',
        'ABSOLUTELY', 'APPROVED', 'ACTIVE', 'COMPLETE', 'CURRENT', 'CONTENT',
        'COMMITTED', 'CONFIRMED', 'CONTEXT', 'CODE', 'ARGUMENTS', 'ARTIFACT',
        'ANALYSIS', 'AUTHORIZED', 'COMMITS', 'COMMITMENT',
    }
    terms -= noise

    return terms


def extract_vocabulary(
    agent_home: Optional[str] = None,
    extra_files: Optional[list] = None,
) -> list:
    """Extract domain vocabulary from MACF standard paths.

    Sources (in priority order):
    1. Curated priority terms (always included)
    2. CLAUDE.md files
    3. Memory files
    4. Policy files (term extraction only)

    Returns sorted list of unique terms.
    """
    if agent_home is None:
        agent_home = os.environ.get("MACEFF_AGENT_HOME_DIR", "")

    all_terms = set(PRIORITY_TERMS)
    sources_read = 0

    # Read CLAUDE.md files
    for claude_md in [
        Path(agent_home) / "CLAUDE.md",
        Path(agent_home) / ".claude" / "CLAUDE.md",
        Path.home() / "CLAUDE.md",
    ]:
        if claude_md.exists():
            try:
                text = claude_md.read_text(errors='replace')[:50000]  # Cap at 50K
                all_terms.update(extract_terms_from_text(text))
                sources_read += 1
            except (OSError, PermissionError) as e:
                print(f"⚠️ MACF: vocabulary extraction skipped {claude_md}: {e}", file=sys.stderr)

    # Read memory files
    memory_dirs = [
        Path.home() / ".claude" / "projects",
    ]
    for mem_dir in memory_dirs:
        if mem_dir.exists():
            for md_file in mem_dir.rglob("*.md"):
                try:
                    text = md_file.read_text(errors='replace')[:10000]
                    all_terms.update(extract_terms_from_text(text))
                    sources_read += 1
                except (OSError, PermissionError):
                    pass

    # Read extra files if provided
    if extra_files:
        for fpath in extra_files:
            p = Path(fpath)
            if p.exists():
                try:
                    text = p.read_text(errors='replace')[:20000]
                    all_terms.update(extract_terms_from_text(text))
                    sources_read += 1
                except (OSError, PermissionError):
                    pass

    return sorted(all_terms)


def build_whisper_prompt(
    terms: Optional[list] = None,
    style_prefix: str = "Discussion about software development, AI agents, and the MACF framework.",
    max_tokens: int = 223,
) -> str:
    """Build a Whisper initial_prompt from vocabulary terms.

    Fits within Whisper's 223-token budget:
    - Style prefix (~20 tokens)
    - "Key terms: " (~3 tokens)
    - Terms as comma-separated list (remaining budget)

    Uses character-based estimation: ~4 chars per token for English.
    """
    if terms is None:
        terms = extract_vocabulary()

    # Estimate token budget: ~4 chars per token
    max_chars = max_tokens * 4  # ~892 chars

    # Build prompt parts
    prefix = style_prefix
    terms_header = " Key terms: "

    # Calculate remaining budget for terms
    remaining_chars = max_chars - len(prefix) - len(terms_header)

    # Priority terms first, then alphabetical
    priority_set = set(PRIORITY_TERMS)
    priority_first = [t for t in terms if t in priority_set]
    others = [t for t in terms if t not in priority_set]

    # Build terms string within budget
    term_parts = []
    chars_used = 0
    for term in priority_first + others:
        addition = term + ", "
        if chars_used + len(addition) > remaining_chars:
            break
        term_parts.append(term)
        chars_used += len(addition)

    terms_str = ", ".join(term_parts)
    prompt = f"{prefix}{terms_header}{terms_str}"

    return prompt
