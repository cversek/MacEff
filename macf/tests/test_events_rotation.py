"""Rotation and archive-spanning reads: the four Phase 3 criteria.

The load-bearing one is the CONTROL. "A query returns the same results after
rotation" is satisfied trivially by a query that returns nothing in both cases,
so seam-invisibility is only meaningful alongside a demonstration that the same
query can still return DIFFERENT results when it should.
"""
import json
import lzma

import pytest

from macf.agent_events_log import (
    CYCLE_BOUNDARY_EVENT,
    query_events,
    read_events,
    set_log_path,
)
from macf.eventlog import archive as arch


def _rec(ts, cycle, event="cli_command_invoked"):
    return {
        "timestamp": ts, "event": event,
        "breadcrumb": f"s_aaaa/c_{cycle}/p_bbbb/t_{int(ts)}", "data": {},
    }


@pytest.fixture
def log(tmp_path):
    p = tmp_path / "agent_events_log.jsonl"
    lines, ts = [], 1_600_000_000.0
    for cycle in (20, 25, 30):
        lines.append(_rec(ts, cycle, CYCLE_BOUNDARY_EVENT)); ts += 86_400
        for _ in range(3):
            lines.append(_rec(ts, cycle)); ts += 3_600
    p.write_text("".join(json.dumps(r) + "\n" for r in lines))
    set_log_path(p)
    yield p
    set_log_path(None)


def _all_events(reverse=False):
    return list(read_events(reverse=reverse, scope="all"))


def test_a_window_spanning_the_seam_returns_what_it_did_before(log):
    before_fwd = _all_events()
    before_rev = _all_events(reverse=True)
    before_c20 = query_events({"breadcrumb": {"c": 20}})

    result = arch.rotate_log(log)
    assert result["rotated"] is True
    assert result["archived_lines"] == 8   # cycles 20 and 25
    assert result["kept_lines"] == 4       # the open cycle stays live

    assert _all_events() == before_fwd, "forward read across the seam changed"
    assert _all_events(reverse=True) == before_rev, "reverse read changed"
    assert query_events({"breadcrumb": {"c": 20}}) == before_c20, (
        "a cycle that moved into an archive stopped being reachable"
    )


def test_the_query_can_still_return_different_results(log):
    """CONTROL -- without this, seam-invisibility is satisfied by a dead query."""
    arch.rotate_log(log)
    c20 = query_events({"breadcrumb": {"c": 20}})
    c25 = query_events({"breadcrumb": {"c": 25}})
    absent = query_events({"breadcrumb": {"c": 99}})
    assert len(c20) == 4 and len(c25) == 4
    assert c20 != c25, "the query returns the same thing regardless of the filter"
    assert absent == [], "a cycle that never existed must not match"


def test_the_open_cycle_stays_live_so_the_common_path_is_untouched(log):
    arch.rotate_log(log)
    live = log.read_text().strip().splitlines()
    assert len(live) == 4
    assert all('"c_30"' in ln or "c_30" in ln for ln in live)
    # A cycle-scoped read is the default and must not open an archive at all.
    calls = []
    real = arch.iter_archive_lines
    arch.iter_archive_lines = lambda *a, **k: (calls.append(a), real(*a, **k))[1]
    try:
        list(read_events(reverse=True))          # default scope="cycle"
    finally:
        arch.iter_archive_lines = real
    assert calls == [], "a cycle-scoped read reached into an archive"


def test_selection_skips_non_matching_archives_without_decompressing(log, tmp_path):
    arch.rotate_log(log)
    d = arch.archive_dir(log)
    # A second archive far in the past, which no window below should touch.
    other = d / "agent_events_log_20200101_20200102.jsonl.xz"
    with lzma.open(other, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(_rec(1_577_836_800.0, 5)) + "\n")

    chosen = arch.select_archives(log, since=1_600_000_000.0)
    assert other not in chosen, "an out-of-range archive was selected"
    assert len(chosen) == 1

    opened = []
    real = arch.iter_archive_lines
    arch.iter_archive_lines = lambda p, **k: (opened.append(p), real(p, **k))[1]
    try:
        list(arch.iter_log_lines(log, reverse=False, include_archives=True,
                                 since=1_600_000_000.0))
    finally:
        arch.iter_archive_lines = real
    assert other not in opened, "a non-matching archive was decompressed"


def test_an_unparseable_archive_name_is_included_not_skipped(log):
    """A naming bug must not become silently missing history."""
    arch.rotate_log(log)
    d = arch.archive_dir(log)
    odd = d / "agent_events_log_NOTADATE.jsonl.xz"
    with lzma.open(odd, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(_rec(1_600_000_000.0, 7)) + "\n")
    assert arch.parse_archive_range(odd) is None
    assert odd in arch.select_archives(log, since=1_600_000_000.0)


def test_the_live_log_survives_a_failed_verification(log, monkeypatch):
    """Copy and verify BEFORE removing anything -- proved by breaking it."""
    original = log.read_text()

    def corrupt(path, reverse=False):
        yield "this is not what was written\n"

    monkeypatch.setattr(arch, "iter_archive_lines", corrupt)
    with pytest.raises(RuntimeError, match="verification failed"):
        arch.rotate_log(log)

    assert log.read_text() == original, "the live log was truncated anyway"
    assert not list(arch.archive_dir(log).glob(".agent_events_log_*")), "partial left behind"


def test_rotating_twice_is_a_no_op_the_second_time(log):
    first = arch.rotate_log(log)
    assert first["rotated"] is True
    second = arch.rotate_log(log)
    assert second["rotated"] is False
    assert "nothing older" in second["reason"]
