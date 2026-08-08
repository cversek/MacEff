"""Tests for the concept vocabulary layer.

The property under test is easy to state and easy to get subtly wrong: a
concept extractor decides **what the knowledge graph believes an artifact is
about**, and both of its failure directions are silent.

Extracting too little produces orphans — artifacts that exist on disk and
cannot be reached by the concept query a successor would actually use. That
failure at least *looks* like absence.

Extracting too much is worse. It produces edges that were never claimed, and a
graph with false edges looks HEALTHIER than one with missing edges, so nothing
prompts anyone to check. Measured on the real corpus, three reflections
consisted entirely of concepts quoted inside code spans while discussing
notation; the old extractor counted them, and those three artifacts appeared
connected while being orphans.

So the tests below spend most of their effort on the boundary between a
concept USED and a concept MENTIONED, and on the union rule that lets a
document be about something in its summary and about something else in its
prose without either suppressing the other.
"""

import pytest

from macf.concepts import (
    extract_wiki_concepts,
    normalize_concept,
    normalize_concepts,
)


class TestNormalizeConcept:
    """Canonical form: one spelling per concept, or the graph splits."""

    @pytest.mark.parametrize("raw,expected", [
        ("verification", "verification"),
        ("Verification", "verification"),
        ("VERIFICATION", "verification"),
        ("[[verification]]", "verification"),
        ("  verification  ", "verification"),
        ("knowledge web", "knowledge_web"),
        ("knowledge-web", "knowledge_web"),
        ("knowledge_web", "knowledge_web"),
        ("verification.md", "verification"),
        ("Verification.MD", "verification"),
        ("[[Knowledge-Web.md]]", "knowledge_web"),
    ])
    def test_spellings_collapse_to_one_form(self, raw, expected):
        assert normalize_concept(raw) == expected

    def test_hyphen_becomes_underscore(self):
        """The scholarship policy specifies underscores.

        A previous implementation preserved hyphens, so ``knowledge-web`` and
        ``knowledge_web`` were two nodes. That is drift the doctor is meant to
        report, not a distinction worth keeping.
        """
        assert normalize_concept("knowledge-web") == normalize_concept("knowledge_web")

    @pytest.mark.parametrize("junk", ["", "   ", "[[]]", "!!!", "---"])
    def test_nothing_survivable_yields_empty(self, junk):
        """Callers drop these; an empty concept must never become a node."""
        assert normalize_concept(junk) == ""


class TestNormalizeConcepts:
    def test_dedupes_preserving_first_seen_order(self):
        """Order carries authorial emphasis — the first concept listed is
        usually what the artifact is most about."""
        assert normalize_concepts(["b", "a", "B", "c", "A"]) == ["b", "a", "c"]

    def test_variants_dedupe_against_each_other(self):
        assert normalize_concepts(["Knowledge-Web", "knowledge_web", "knowledge web"]) == ["knowledge_web"]

    def test_empties_dropped_not_kept_as_blank_nodes(self):
        assert normalize_concepts(["ok", "", "  ", "[[]]"]) == ["ok"]

    def test_none_and_empty_input(self):
        assert normalize_concepts(None) == []
        assert normalize_concepts([]) == []


class TestExtractUnion:
    """Section and prose are both sources. Neither may suppress the other."""

    def test_section_and_inline_are_unioned(self):
        doc = (
            "# JOTEWR\n"
            "The lesson was about [[verification]] and how [[silent_failure]] hides.\n\n"
            "## Wiki-Links\n\n[[knowledge_web]] [[tooling]]\n"
        )
        assert extract_wiki_concepts(doc) == [
            "knowledge_web", "tooling", "verification", "silent_failure",
        ]

    def test_section_does_not_suppress_prose(self):
        """The regression this module exists to fix.

        Extraction previously treated the whole-document scan as a fallback,
        so a non-empty section discarded every inline concept — meaning that
        ADDING a summary section to a richly linked reflection REDUCED its
        graph presence.
        """
        doc = "# X\nprose [[alpha]]\n\n## Wiki-Links\n\n[[beta]]\n"
        got = extract_wiki_concepts(doc)
        assert "alpha" in got and "beta" in got

    def test_section_first_then_prose(self):
        """Summary concepts lead: they describe the whole artifact."""
        doc = "# X\nprose [[zulu]]\n\n## Wiki-Links\n\n[[alpha]]\n"
        assert extract_wiki_concepts(doc) == ["alpha", "zulu"]

    def test_overlap_appears_once(self):
        doc = "# X\nprose [[shared]] and [[only_prose]]\n\n## Wiki-Links\n\n[[shared]] [[only_section]]\n"
        assert extract_wiki_concepts(doc) == ["shared", "only_section", "only_prose"]

    def test_prose_only_document_still_participates(self):
        assert extract_wiki_concepts("# X\njust [[alpha]] here\n") == ["alpha"]

    def test_section_only_document_still_participates(self):
        assert extract_wiki_concepts("# X\n\n## Wiki-Links\n\n[[alpha]] [[beta]]\n") == ["alpha", "beta"]

    def test_no_links_yields_empty(self):
        assert extract_wiki_concepts("# X\nnothing to see\n") == []


class TestMentionVersusUse:
    """A corpus documenting its own conventions writes about concepts on
    purpose. Counting those mints phantom nodes."""

    def test_inline_code_span_is_a_mention(self):
        doc = "# X\nWrite it as `[[compaction]]` in your section.\nReal use: [[verification]].\n"
        got = extract_wiki_concepts(doc)
        assert got == ["verification"]
        assert "compaction" not in got

    def test_fenced_block_is_a_mention(self):
        doc = "# X\n```\n[[fake]]\n```\nreal [[actual]]\n"
        assert extract_wiki_concepts(doc) == ["actual"]

    def test_tilde_fenced_block_is_a_mention(self):
        doc = "# X\n~~~\n[[fake]]\n~~~\nreal [[actual]]\n"
        assert extract_wiki_concepts(doc) == ["actual"]

    def test_document_of_only_mentions_is_an_orphan(self):
        """The measured real-world case.

        Three reflections in the corpus contained wiki-links exclusively
        inside code spans while explaining the notation. They must extract to
        nothing — reporting them as orphans is correct, and is strictly better
        than the edges the old extractor invented for them.
        """
        doc = "# Reflection\nI wrote `[[verification]]` and `[[epistemics]]` while explaining the syntax.\n"
        assert extract_wiki_concepts(doc) == []

    def test_fence_containing_backticks_does_not_leak(self):
        """Fenced blocks are stripped before code spans, so an inner backtick
        cannot leave a dangling delimiter that swallows real prose."""
        doc = "# X\n```\nuse ` and [[fake]]\n```\nreal [[actual]]\n"
        assert extract_wiki_concepts(doc) == ["actual"]

    def test_block_quotes_are_kept(self):
        """Deliberate, and narrow: no artifact in the corpus puts a wiki-link
        in a block quote, so excluding them would be untested behaviour
        written for a case that does not occur. Documented so a future change
        is a decision rather than an accident."""
        assert extract_wiki_concepts("# X\n> quoted [[alpha]]\n") == ["alpha"]


class TestExtractionNormalizes:
    def test_variants_across_sources_merge(self):
        """A concept written one way inline and another in the summary is one
        node, not two."""
        doc = "# X\nprose [[Knowledge-Web]]\n\n## Wiki-Links\n\n[[knowledge_web]]\n"
        assert extract_wiki_concepts(doc) == ["knowledge_web"]

    def test_heading_variants_recognised(self):
        for heading in ("## Wiki-Links", "##  Wiki-Links", "## wiki-links"):
            doc = f"# X\n\n{heading}\n\n[[alpha]]\n"
            assert extract_wiki_concepts(doc) == ["alpha"], heading

    def test_following_section_terminates_the_block(self):
        """Concepts after the next heading are prose, not summary — they must
        still be found, but the section must not swallow the rest of the file."""
        doc = "# X\n\n## Wiki-Links\n\n[[alpha]]\n\n## Notes\n\ntail [[beta]]\n"
        assert extract_wiki_concepts(doc) == ["alpha", "beta"]
