"""Concepts: the vocabulary layer of the knowledge web.

A **concept** is the thing a ``[[wiki_link]]`` names. Concepts are not owned by
any consciousness-artifact type — a concept is precisely what lets a learning, a
reflection, a checkpoint, an experiment and an idea refer to the same subject.
They therefore live here rather than inside the module for any one CA type.

Two responsibilities, and only these:

- **normalization** — mapping every spelling of a concept to one canonical form,
  so that ``[[Knowledge-Web]]``, ``[[knowledge web]]`` and ``[[knowledge_web]]``
  are one node rather than three;
- **extraction** — deciding which ``[[...]]`` occurrences in a document are
  genuine participation and which are merely the document talking about
  notation.

Graph construction, querying and reporting build on this and belong elsewhere.
"""

from __future__ import annotations

import re
from typing import Iterable, List

__all__ = ["normalize_concept", "normalize_concepts", "extract_wiki_concepts"]


def normalize_concept(raw: str) -> str:
    """Map one concept spelling to its canonical form.

    Canonical form is lowercase, underscore-separated, with no ``[[ ]]``
    wrapper and no ``.md`` suffix. Hyphens and spaces both become underscores:
    the scholarship policy specifies underscores, so a hyphenated spelling is
    drift to be merged, not a distinct concept to be preserved.

    Returns an empty string when nothing survives normalization; callers are
    expected to drop those rather than create an empty node.
    """
    if not raw:
        return ""
    c = raw.strip().strip("[]").strip()
    c = re.sub(r"\.md$", "", c, flags=re.IGNORECASE)
    c = c.lower()
    c = re.sub(r"[\s\-]+", "_", c)
    c = re.sub(r"[^a-z0-9_]", "", c)
    c = re.sub(r"_+", "_", c).strip("_")
    return c


def normalize_concepts(raw: Iterable[str]) -> List[str]:
    """Normalize a sequence of concepts, dropping empties, deduping in order.

    First-seen order is preserved because it carries authorial emphasis: the
    concept an author listed first is usually the one the artifact is most
    about.
    """
    seen = set()
    out: List[str] = []
    for token in raw or []:
        c = normalize_concept(token)
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def extract_wiki_concepts(content: str) -> List[str]:
    """Extract the concepts a document participates in, as a normalized union.

    Two sources, both counted:

    - the canonical ``## Wiki-Links`` section, which summarises what the whole
      artifact is about;
    - inline ``[[concept]]`` usage anywhere else, which binds an individual
      *passage* to a concept. Reflections in particular are expansion rather
      than summary, so their conceptual work lives in the prose and tagging
      only the document loses it.

    Earlier behaviour treated the whole-document scan as a *fallback*: a
    non-empty section suppressed every inline concept, so adding a summary
    section to a richly linked document REDUCED its graph presence. The two
    sources are now unioned, section first.

    Occurrences inside fenced code blocks or inline code spans are **mentions,
    not uses**, and are excluded. A corpus that documents its own conventions
    writes about concepts deliberately; counting those mints phantom nodes for
    the very spellings a passage is explaining. Measured on this corpus, three
    reflections consisted *entirely* of such mentions and appeared connected
    while being orphans.

    Block quotes are deliberately NOT excluded: no artifact in the corpus
    currently places a wiki-link inside one, so excluding them would be
    untested behaviour written for a case that does not occur.
    """
    # Fenced blocks first, so a fence containing backticks cannot leave a
    # dangling code-span delimiter behind.
    prose = re.sub(r"```.*?```", " ", content, flags=re.DOTALL)
    prose = re.sub(r"~~~.*?~~~", " ", prose, flags=re.DOTALL)
    prose = re.sub(r"`[^`\n]*`", " ", prose)

    section: List[str] = []
    wl = re.search(r"##\s*Wiki-Links\s*\n(.+?)(?:\n##\s|\Z)", prose,
                   re.DOTALL | re.IGNORECASE)
    if wl:
        section = re.findall(r"\[\[(.+?)\]\]", wl.group(1))
        rest = prose[:wl.start()] + prose[wl.end():]
    else:
        rest = prose

    inline = re.findall(r"\[\[(.+?)\]\]", rest)
    return normalize_concepts(list(section) + list(inline))
