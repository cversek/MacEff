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
from typing import Generator, Optional, Union


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
    end: Optional[int] = None,
) -> Generator[str, None, None]:
    """Yield decoded lines from ``path`` in reverse order (newest first).

    ``end`` starts the read at that byte offset instead of at EOF, so a reader
    can take the file as it was at a known size and not see what was appended
    after. It is clamped to the file's size.

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
        position = f.tell() if end is None else min(end, f.tell())
        if position <= 0:
            return

        # The pieces of the line being read, newest piece first. A line that
        # spans many chunks is joined once, when its start is found; re-joining
        # it for every chunk it spans made a long line cost its length squared.
        pending = []

        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            f.seek(position)
            chunk = f.read(read_size)

            pieces = chunk.split(b"\n")
            # The chunk's last piece ends the pending line. With no newline in
            # the chunk, the line goes on into the next (older) chunk.
            pending.append(pieces[-1])
            if len(pieces) == 1:
                continue
            yield b"".join(reversed(pending)).decode(encoding, errors="replace")
            # Whole lines inside the chunk, newest first.
            for line in reversed(pieces[1:-1]):
                yield line.decode(encoding, errors="replace")
            # The first piece may begin in an earlier chunk.
            pending = [pieces[0]]

        # The start of the file begins the last line.
        yield b"".join(reversed(pending)).decode(encoding, errors="replace")
