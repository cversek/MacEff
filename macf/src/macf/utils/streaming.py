"""Streaming I/O utilities — read large files without materialization.

The Stop hook scans event logs and CC transcript JSONLs to find the most
recent matching event (e.g. ``scope_timer_set``, a tool error). The naive
implementation ``f.readlines()`` materializes the entire file into a list.
For event logs that grow to hundreds of MB and transcripts that can be
~1 GB, this OOM-kills the hook at high context use.

This module provides a generator that reads a file backwards in fixed-size
chunks, yielding decoded lines newest-first. Memory bound: roughly
``chunk_size + max_line_size`` bytes at any moment, independent of file
size.
"""
from __future__ import annotations

from pathlib import Path
from typing import Generator, Union


def iter_lines_forward(
    path: Union[str, Path],
    encoding: str = "utf-8",
) -> Generator[str, None, None]:
    """Yield decoded lines from ``path`` in file order (oldest-first).

    Streams line-by-line via Python's default text-mode file iteration —
    no materialization, O(max_line_size) memory regardless of file size.
    Provided as the forward-direction peer of ``iter_lines_reverse`` so
    callers can pick a direction without leaving the streaming module.

    Args:
        path: File path to read.
        encoding: Text encoding for decoded output (default ``utf-8``).

    Yields:
        Lines as str, NEWLINE INCLUDED (matches Python's native ``for line
        in f`` behavior). Callers typically strip via ``line.strip()`` or
        ``line.rstrip('\\n')`` as needed.

    Example:
        >>> for line in iter_lines_forward("events.jsonl"):
        ...     event = json.loads(line)
        ...     process(event)
    """
    with open(path, "r", encoding=encoding) as f:
        for line in f:
            yield line


def iter_lines_reverse(
    path: Union[str, Path],
    chunk_size: int = 65536,
    encoding: str = "utf-8",
) -> Generator[str, None, None]:
    """Yield decoded lines from ``path`` in reverse order (newest first).

    Reads the file backwards from EOF in ``chunk_size`` byte chunks. Within
    each chunk, lines are split on ``b'\\n'``. The trailing fragment of a
    line that started in an earlier (older) chunk is carried over as a
    ``remainder`` so cross-chunk lines reassemble correctly.

    UTF-8 safety: decoding happens AFTER reassembly, with ``errors='replace'``
    as a defensive fallback when input contains malformed bytes (it should
    never happen for well-formed JSONL, but the alternative — crashing —
    is worse than emitting a U+FFFD).

    Args:
        path: File path to read.
        chunk_size: Bytes per read. Default 64 KB. Larger = fewer syscalls,
            higher transient memory; smaller = more syscalls, lower memory.
        encoding: Text encoding for decoded output (default ``utf-8``).

    Yields:
        Lines as str, NEWLINE STRIPPED, newest-first. Empty lines (from a
        trailing newline or blank lines in the source) are yielded as ``""``
        so callers can filter via ``if not line: continue``.

    Memory: O(chunk_size + max_line_size) regardless of file size.

    Example:
        >>> for line in iter_lines_reverse("events.jsonl"):
        ...     if not line:
        ...         continue
        ...     if marker in line:
        ...         print(line)
        ...         break
    """
    p = Path(path)
    with open(p, "rb") as f:
        f.seek(0, 2)  # SEEK_END
        position = f.tell()
        if position == 0:
            return

        # remainder holds the partial leading line from the current chunk,
        # whose continuation lives in the next (older) chunk we'll read.
        remainder = b""

        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            f.seek(position)
            chunk = f.read(read_size)

            # The remainder from the previous iteration represents the START
            # of a line whose REST is at the END of THIS (older) chunk.
            # Concatenate so the split below produces complete lines.
            data = chunk + remainder
            lines = data.split(b"\n")

            if position > 0:
                # First piece may be incomplete — its prefix lives in an
                # even earlier chunk. Save it as the new remainder.
                remainder = lines[0]
                # Yield the rest newest-first (last index is most recent).
                for line in reversed(lines[1:]):
                    yield line.decode(encoding, errors="replace")
            else:
                # No more chunks; every piece is complete.
                for line in reversed(lines):
                    yield line.decode(encoding, errors="replace")
