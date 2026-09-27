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
    ok, msg = add_entry("2026-01-03_c_learning.md", "Embedded Debug", agent_home=home.home)
    assert ok and "consultation trigger" in msg
    assert "## Embedded Debug (1)" in (home.ldir / "INDEX.md").read_text()
    assert ("consultation trigger", "Embedded Debug") in _checks(verify(home.home, memory_file=home.mem))


def test_a_missing_trigger_names_where_it_looked(home, tmp_path):
    gone = tmp_path / "nowhere" / "MEMORY.md"
    f = next(f for f in verify(home.home, memory_file=gone).findings if f.check == "consultation trigger")
    assert str(gone) in f.detail
