"""Unit tests for macf.utils.streaming line iterators.

Covers correctness (line ordering, cross-chunk reassembly, UTF-8, edge
cases) plus a memory-bound regression test that demonstrates the
seek-from-end reader doesn't materialize the file (closes the OOM bug
fixed in cversek/MacEff#94).
"""
from __future__ import annotations

import os
import resource
import sys
from pathlib import Path

import pytest

from macf.utils.streaming import iter_lines_forward, iter_lines_reverse


# --- iter_lines_reverse: happy paths and edge cases ----------------------

def test_reverse_yields_lines_newest_first(tmp_path: Path):
    """Multi-line file: yielded in reverse order with empty trailing-newline element."""
    p = tmp_path / "f.txt"
    p.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    lines = list(iter_lines_reverse(p))

    # Trailing newline produces an empty final element when splitting.
    # Reverse-iteration yields that empty string FIRST (most recent EOL),
    # then "gamma", "beta", "alpha".
    assert lines == ["", "gamma", "beta", "alpha"]


def test_reverse_no_trailing_newline(tmp_path: Path):
    """File without trailing newline: last line yielded first, no empty element."""
    p = tmp_path / "f.txt"
    p.write_text("alpha\nbeta\ngamma", encoding="utf-8")

    lines = list(iter_lines_reverse(p))

    assert lines == ["gamma", "beta", "alpha"]


def test_reverse_empty_file_yields_nothing(tmp_path: Path):
    """Zero-byte file: generator terminates without yielding."""
    p = tmp_path / "empty.txt"
    p.touch()

    assert list(iter_lines_reverse(p)) == []


def test_reverse_single_line_no_newline(tmp_path: Path):
    """File containing one line with no newline: yielded as the sole element."""
    p = tmp_path / "f.txt"
    p.write_text("solitary", encoding="utf-8")

    assert list(iter_lines_reverse(p)) == ["solitary"]


def test_reverse_reassembles_across_chunk_boundary(tmp_path: Path):
    """Line that spans a chunk boundary must be reassembled correctly.

    We force the line in question to straddle a chunk by picking a small
    chunk_size and a line longer than that.
    """
    p = tmp_path / "f.txt"
    # 100-char line, with shorter ones bracketing it, written as JSONL-style
    long_line = "X" * 100
    p.write_text(f"first\n{long_line}\nlast\n", encoding="utf-8")

    # chunk_size=32 forces long_line to straddle multiple chunks
    lines = list(iter_lines_reverse(p, chunk_size=32))

    # Drop empty trailing-newline artifact for clarity
    non_empty = [line for line in lines if line]
    assert non_empty == ["last", long_line, "first"]


def test_reverse_utf8_multibyte_across_chunk_boundary(tmp_path: Path):
    """Multi-byte UTF-8 char split mid-codepoint by chunk boundary still decodes."""
    p = tmp_path / "f.txt"
    # "ééééé" is 5 chars × 2 bytes each = 10 bytes per "éééé" group.
    # Mix with ASCII to force boundary placement.
    p.write_bytes(b"hello\n" + ("é" * 50).encode("utf-8") + b"\nworld\n")

    # Small chunk_size guarantees a multi-byte char gets split
    lines = list(iter_lines_reverse(p, chunk_size=17))
    non_empty = [line for line in lines if line]

    assert non_empty == ["world", "é" * 50, "hello"]


# --- iter_lines_forward ---------------------------------------------------

def test_forward_yields_in_order_with_newlines_included(tmp_path: Path):
    """Forward iteration preserves order and keeps the trailing newline on each line."""
    p = tmp_path / "f.txt"
    p.write_text("one\ntwo\nthree\n", encoding="utf-8")

    lines = list(iter_lines_forward(p))

    assert lines == ["one\n", "two\n", "three\n"]


def test_forward_empty_file(tmp_path: Path):
    """Forward read of empty file yields nothing."""
    p = tmp_path / "empty.txt"
    p.touch()

    assert list(iter_lines_forward(p)) == []


# --- Memory-bound regression (production-path validation) ----------------

@pytest.mark.skipif(
    sys.platform == "win32",
    reason="ru_maxrss semantics differ on Windows; test is unix-only."
)
def test_reverse_does_not_materialize_large_file(tmp_path: Path):
    """Closes cversek/MacEff#94: scanning a large JSONL backwards must not
    materialize the file. We write a 30 MB JSONL and verify peak RSS growth
    during a backward scan stays well under the file size.

    We can't assert an exact RSS number portably (RSS depends on Python
    object overhead, page granularity, prior allocations) so we assert the
    growth from a baseline taken AFTER allocation of the iterator is
    bounded by a small multiple of chunk_size + max_line_size.
    """
    p = tmp_path / "big.jsonl"
    # 30 MB of repeating ~300-byte lines (event-log shape).
    line = '{"timestamp": 1778700000, "event": "fake", "data": {"k": "' + "x" * 200 + '"}}'
    line_size = len(line) + 1  # +1 for newline
    target_bytes = 30 * 1024 * 1024
    num_lines = target_bytes // line_size
    with open(p, "w", encoding="utf-8") as f:
        for _ in range(num_lines):
            f.write(line + "\n")

    file_size = p.stat().st_size
    assert file_size >= 25 * 1024 * 1024, "test fixture should be ~30 MB"

    # Baseline RSS AFTER fixture write (so we measure only the read cost).
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    # Stream the file backwards, consume a handful of lines, then break.
    count = 0
    for _line in iter_lines_reverse(p, chunk_size=65536):
        count += 1
        if count >= 50:
            break

    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # On macOS ru_maxrss is bytes; on Linux it's KB. Either way, the growth
    # should be a tiny fraction of the file size. Allow 2 MB of slop for
    # interpreter/import-time allocations unrelated to the read.
    growth = rss_after - rss_before
    # Convert growth to bytes if we're on Linux (assume KB if growth looks
    # small enough to be a KB delta on a multi-MB file).
    growth_bytes = growth if sys.platform == "darwin" else growth * 1024

    # Bound: chunk_size + interpreter slop. Pick 4 MB.
    assert growth_bytes < 4 * 1024 * 1024, (
        f"RSS growth {growth_bytes} bytes exceeded streaming bound — "
        f"file size was {file_size} bytes (suggests materialization)."
    )

    # Sanity: we actually read something.
    assert count == 50
