"""The learnings index and its trigger kept current by a tool (#392 item 6).

Every curation must add each learning under its cluster, keep the counts, and
check that the auto-loaded trigger still names every cluster. By hand that is
the step that gets skipped, and nothing looks wrong afterwards: the consult
step just stops finding things. `add` does the edit; `verify` is the doctor
that notices when it was not done.
"""
from types import SimpleNamespace

import pytest

from macf.learnings_index import add_entry, parse_index, verify

INDEX = """# Agent Learnings Index

**Last Updated**: 2026-01-01
**Total Learnings**: 2
**Topics**: 2

## Hooks (1)

- **Hook output is proprioception** -- `2026-01-01_a_learning.md`

## Testing (1)

- **Prove the checker fires** -- `2026-01-02_b_learning.md`
"""

TRIGGER = "Index (2 learnings): agent/private/learnings/INDEX.md\nClusters: Hooks · Testing\n"


@pytest.fixture
def home(tmp_path):
    ldir = tmp_path / "agent" / "private" / "learnings"
    ldir.mkdir(parents=True)
    (ldir / "2026-01-01_a_learning.md").write_text("# Learning: Hook output is proprioception\n")
    (ldir / "2026-01-02_b_learning.md").write_text("# Learning: Prove the checker fires\n")
    (ldir / "INDEX.md").write_text(INDEX)
    mem = tmp_path / "MEMORY.md"
    mem.write_text(TRIGGER)
    return SimpleNamespace(home=tmp_path, ldir=ldir, mem=mem)


def _checks(dx):
    return sorted((f.check, f.subject) for f in dx.findings)


def test_a_consistent_index_and_trigger_verify_clean(home):
    dx = verify(home.home, memory_file=home.mem)
    assert dx.findings == [] and dx.chart.vitals == {"learnings": 2, "indexed": 2, "clusters": 2}


def test_verify_finds_each_way_the_index_can_stop_being_true(home):
    (home.ldir / "2026-01-03_c_learning.md").write_text("# Learning: new\n")          # unindexed
    (home.ldir / "2026-01-02_b_learning.md").unlink()                                  # dangling
    home.mem.write_text("Clusters: Hooks\n")                                           # trigger drift
    checks = _checks(verify(home.home, memory_file=home.mem))
    assert ("unindexed learnings", "2026-01-03_c_learning.md") in checks
    assert ("dangling entries", "2026-01-02_b_learning.md") in checks
    assert ("consultation trigger", "Testing") in checks
    assert any(c == "consultation trigger" and s.endswith("MEMORY.md") for c, s in checks), \
        "a trigger that does not point at INDEX.md is reported"


def test_add_files_the_entry_and_keeps_every_count_true(home):
    (home.ldir / "2026-01-03_c_learning.md").write_text("# Learning: Structure beats memory\n")
    ok, msg = add_entry("2026-01-03_c_learning.md", "Testing", hook="WHEN a lesson recurs", agent_home=home.home)
    assert ok, msg
    text = (home.ldir / "INDEX.md").read_text()
    assert "## Testing (2)" in text and "**Total Learnings**: 3" in text
    assert "- **Structure beats memory** -- `2026-01-03_c_learning.md` -- WHEN a lesson recurs" in text
    assert parse_index(text)["Testing"]["files"][-1] == "2026-01-03_c_learning.md"
    stale = verify(home.home, memory_file=home.mem).findings
    assert [f.detail for f in stale] == ["says 2 learnings, there are 3"], "the trigger's count went stale"
    home.mem.write_text(TRIGGER.replace("2 learnings", "3 learnings"))
    assert verify(home.home, memory_file=home.mem).findings == []
    assert add_entry("2026-01-03_c_learning.md", "Testing", agent_home=home.home) == \
        (False, "2026-01-03_c_learning.md is already indexed")


def test_a_new_cluster_is_created_and_the_trigger_reminder_given(home):
    (home.ldir / "2026-01-03_c_learning.md").write_text("# Learning: new domain\n")
    ok, msg = add_entry("2026-01-03_c_learning.md", "Embedded Debug", agent_home=home.home, new_cluster=True)
    assert ok and "consultation trigger" in msg
    assert "## Embedded Debug (1)" in (home.ldir / "INDEX.md").read_text()
    assert ("consultation trigger", "Embedded Debug") in _checks(verify(home.home, memory_file=home.mem))


def test_a_missing_trigger_names_where_it_looked(home, tmp_path):
    gone = tmp_path / "nowhere" / "MEMORY.md"
    f = next(f for f in verify(home.home, memory_file=gone).findings if f.check == "consultation trigger")
    assert str(gone) in f.detail


def test_an_entry_written_as_a_markdown_link_counts_as_indexed(home):
    """The policy prescribes no entry form, and hand-curated indexes link the file.

    A checker that read only backticked names reported every linked entry as a
    learning the consult step cannot find: 54 false findings on one live index.
    """
    (home.ldir / "INDEX.md").write_text(INDEX.replace(
        "- **Prove the checker fires** -- `2026-01-02_b_learning.md`",
        "- [Prove the checker fires](2026-01-02_b_learning.md) — before trusting a gate"))
    dx = verify(home.home, memory_file=home.mem)
    assert dx.findings == [] and dx.chart.vitals["indexed"] == 2


def test_a_web_link_is_not_an_entry(home):
    (home.ldir / "INDEX.md").write_text(INDEX.replace(
        "`2026-01-02_b_learning.md`", "[see](https://example.org/2026-01-02_b_learning.md)"))
    checks = _checks(verify(home.home, memory_file=home.mem))
    assert ("unindexed learnings", "2026-01-02_b_learning.md") in checks
    assert not any(c == "dangling entries" for c, _ in checks), \
        "a web link is no entry at all, so it cannot dangle either"


def test_a_linked_entry_to_a_missing_file_is_dangling(home):
    (home.ldir / "INDEX.md").write_text(INDEX.replace(
        "`2026-01-02_b_learning.md`", "[gone](2026-01-09_gone_learning.md)"))
    checks = _checks(verify(home.home, memory_file=home.mem))
    assert ("dangling entries", "2026-01-09_gone_learning.md") in checks


# The four shapes from the review of #514: hooks link other files, and only a
# line's own entry may count.
def _with_hook(home, hook):
    (home.ldir / "INDEX.md").write_text(INDEX.replace(
        "- **Hook output is proprioception** -- `2026-01-01_a_learning.md`",
        "- [Hook output is proprioception](2026-01-01_a_learning.md) -- " + hook))


def test_a_see_also_link_in_a_hook_does_not_count_its_target_twice(home):
    _with_hook(home, "see also [the checker](2026-01-02_b_learning.md)")
    dx = verify(home.home, memory_file=home.mem)
    assert dx.findings == [] and dx.chart.vitals["indexed"] == 2


def test_a_learning_only_mentioned_in_a_hook_is_still_unindexed(home):
    (home.ldir / "2026-01-03_c_learning.md").write_text("# Learning: c\n")
    _with_hook(home, "see also [c](2026-01-03_c_learning.md)")
    checks = _checks(verify(home.home, memory_file=home.mem))
    assert ("unindexed learnings", "2026-01-03_c_learning.md") in checks


def test_a_hook_citing_a_checkpoint_is_not_a_dangling_entry(home):
    _with_hook(home, "from [the CCP](../checkpoints/2026-01-01_x_CCP.md)")
    assert not any(c == "dangling entries" for c, _ in _checks(verify(home.home, memory_file=home.mem)))


def test_an_entry_linking_a_section_is_read(home):
    (home.ldir / "INDEX.md").write_text(INDEX.replace(
        "- **Prove the checker fires** -- `2026-01-02_b_learning.md`",
        "- [Prove the checker fires](2026-01-02_b_learning.md#pattern) -- before a gate"))
    dx = verify(home.home, memory_file=home.mem)
    assert dx.findings == [] and dx.chart.vitals["indexed"] == 2


LINK_INDEX = """# Agent Learnings Index

**Total Learnings**: 2

## Hooks (1)

- [Hook output is proprioception](2026-01-01_a_learning.md) -- WHEN a hook line reads like advice
- [The reflection behind it](../reflections/2026-01-01_jotewr.md) -- background, not an entry

## Testing (1)

- [Prove the checker fires](2026-01-02_b_learning.md) -- WHEN a check passes; see also [the hook one](2026-01-01_a_learning.md)

**Keywords**: hooks, testing
"""


def test_add_writes_a_new_entry_in_the_shape_of_the_clusters_own(home):
    """An index curated by hand in link form stays in link form."""
    (home.ldir / "INDEX.md").write_text(LINK_INDEX)
    (home.ldir / "2026-01-03_c_learning.md").write_text("# Learning: Structure beats memory\n")
    ok, msg = add_entry("2026-01-03_c_learning.md", "Testing", hook="WHEN a lesson recurs", agent_home=home.home)
    assert ok, msg
    text = (home.ldir / "INDEX.md").read_text()
    assert "- [Structure beats memory](2026-01-03_c_learning.md) -- WHEN a lesson recurs" in text
    assert "## Testing (2)" in text and "**Total Learnings**: 3" in text


def test_an_unknown_cluster_is_refused_and_the_near_names_offered(home):
    """A near-miss must not quietly become a one-entry cluster."""
    (home.ldir / "2026-01-03_c_learning.md").write_text("# Learning: new\n")
    before = (home.ldir / "INDEX.md").read_text()
    ok, msg = add_entry("2026-01-03_c_learning.md", "Test", agent_home=home.home)
    assert not ok and "Testing" in msg and "--new-cluster" in msg
    assert (home.ldir / "INDEX.md").read_text() == before


def test_a_new_cluster_goes_after_the_last_cluster_not_after_trailing_text(home):
    (home.ldir / "INDEX.md").write_text(LINK_INDEX)
    (home.ldir / "2026-01-03_c_learning.md").write_text("# Learning: new domain\n")
    ok, _ = add_entry("2026-01-03_c_learning.md", "Embedded Debug", agent_home=home.home, new_cluster=True)
    text = (home.ldir / "INDEX.md").read_text()
    assert ok and text.index("## Embedded Debug (1)") < text.index("**Keywords**")


def test_a_cluster_named_only_in_a_linked_memory_file_is_reported_as_such(home):
    """The taxonomy must be in the auto-loaded file itself; a file it links loads
    only when something recalls it."""
    (home.mem.parent / "learnings_trigger.md").write_text("Clusters: Hooks · Testing\n")
    home.mem.write_text("Index (2 learnings): agent/private/learnings/INDEX.md\nClusters: Hooks\n"
                        "- [Learnings trigger](learnings_trigger.md)\n")
    f = next(f for f in verify(home.home, memory_file=home.mem).findings if f.subject == "Testing")
    assert "learnings_trigger.md" in f.detail and "recalled" in f.detail
