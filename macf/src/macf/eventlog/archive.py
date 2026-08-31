"""Rotation and archive-spanning reads for the agent events log.

The log grows at a measured 2.29 MB/day and is dominated by history rather than
by current capture: Phase 1 of this mission reduced what gets written and left
the ~105 MB already on disk untouched. Rotation addresses that directly --
measured on the real 143 MB log, compression recovers 93% of it **losslessly**,
against 47% for eliding history in place, which also destroys the elided detail.

Three properties this module is built around, each because its absence is a
failure this project has already had:

**The reader ships with the splitter.** An archive the query cannot span is a
deletion with extra steps. That is why the codec is stdlib ``lzma`` and not
``zstd``: measured, ``zstandard`` is absent from every deployment container, so
zstd archives would be unreadable exactly where the logs live. At preset 6 lzma
also compresses *better* than zstd -3 (16.3x vs 10.3x) and decompresses the
whole corpus in 0.39s, which is nothing against a forensic scan.

**Selection never decompresses.** The date range lives in the filename, so
choosing which archives a window touches costs a readdir.

**Copy and verify before removing anything.** The archive is written, read back,
and compared by content hash *before* the live log is truncated -- and the whole
sequence holds the same ``flock`` the writers use, so a concurrent append blocks
rather than landing in the gap.
"""
import fcntl
import hashlib
import json
import lzma
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from ..utils.streaming import iter_lines_forward, iter_lines_reverse

ARCHIVE_DIRNAME = "events_archive"
ARCHIVE_PREFIX = "agent_events_log_"

# Dispatch on the suffix rather than assuming one codec. This is the only
# future-proofing here and it costs a dict lookup: an archive written by a
# different codec later can be read alongside these without a migration.
_DECOMPRESSORS = {
    ".xz": lzma.open,
    ".lzma": lzma.open,
}

LZMA_PRESET = 6


def archive_dir(log_path: Path) -> Path:
    """Directory holding rotated archives, beside the live log."""
    return Path(log_path).parent / ARCHIVE_DIRNAME


def _daystamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d")


def archive_name(start_ts: float, end_ts: float) -> str:
    """Archive filename carrying its own date range.

    The range is in the NAME so `select_archives` can skip an archive without
    opening it -- a stated completion criterion for this phase.
    """
    return f"{ARCHIVE_PREFIX}{_daystamp(start_ts)}_{_daystamp(end_ts)}.jsonl.xz"


def parse_archive_range(path: Path) -> Optional[Tuple[str, str]]:
    """(start_daystamp, end_daystamp) for an archive, or None if unparseable.

    Returns None rather than raising, and callers treat None as "cannot rule it
    out" -- an unreadable name must never cause an archive to be silently
    skipped, because that turns a naming bug into missing forensic history.
    """
    name = Path(path).name
    if not name.startswith(ARCHIVE_PREFIX):
        return None
    stem = name[len(ARCHIVE_PREFIX):].split(".")[0]
    parts = stem.split("_")
    if len(parts) != 2 or not all(p.isdigit() and len(p) == 8 for p in parts):
        return None
    return parts[0], parts[1]


def list_archives(log_path: Path) -> List[Path]:
    """Every archive beside the log, oldest first by range start."""
    d = archive_dir(log_path)
    if not d.is_dir():
        return []
    found = [p for p in d.iterdir()
             if p.name.startswith(ARCHIVE_PREFIX) and p.suffix in _DECOMPRESSORS]
    return sorted(found, key=lambda p: (parse_archive_range(p) or ("", ""), p.name))


def select_archives(
    log_path: Path,
    since: Optional[float] = None,
    until: Optional[float] = None,
) -> List[Path]:
    """Archives whose date range intersects [since, until], oldest first.

    Selection reads only filenames. An archive whose range cannot be parsed is
    INCLUDED, not skipped: excluding it would answer the query with a silent
    omission, and this module's whole subject is that a narrowed answer reads
    like a complete one.
    """
    lo = _daystamp(since) if since is not None else None
    hi = _daystamp(until) if until is not None else None
    out = []
    for p in list_archives(log_path):
        rng = parse_archive_range(p)
        if rng is None:
            out.append(p)
            continue
        start, end = rng
        if lo is not None and end < lo:
            continue
        if hi is not None and start > hi:
            continue
        out.append(p)
    return out


def iter_archive_lines(path: Path, reverse: bool = False) -> Generator[str, None, None]:
    """Lines from one archive, in either direction, memory-bounded.

    A reverse read decompresses to a temp file and reuses the seek-from-end
    iterator rather than materialising the archive as a list. An archive can
    hold a whole quarter of history; buffering it in RAM would reintroduce the
    OOM this log's streaming readers were written to fix.
    """
    opener = _DECOMPRESSORS.get(Path(path).suffix)
    if opener is None:
        raise ValueError(
            f"no decompressor for {Path(path).name!r}. Refusing to skip it: an "
            "unreadable archive must be an error, never an empty result."
        )
    if not reverse:
        with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                yield line
        return

    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix="macf_arch_", suffix=".jsonl")
        with os.fdopen(fd, "wb") as out, opener(path, "rb") as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
        for line in iter_lines_reverse(Path(tmp)):
            yield line
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def iter_log_lines(
    log_path: Path,
    reverse: bool = True,
    include_archives: bool = False,
    since: Optional[float] = None,
    until: Optional[float] = None,
) -> Generator[str, None, None]:
    """Lines across the live log and, optionally, its archives.

    This is the seam, and it is invisible to callers by construction: the
    ordering contract is the same one a single file gives. Reverse reads the
    live log first and then archives newest-first; forward reads archives
    oldest-first and then the live log.
    """
    log_path = Path(log_path)
    archives = select_archives(log_path, since, until) if include_archives else []

    if reverse:
        if log_path.exists():
            yield from iter_lines_reverse(log_path)
        for p in reversed(archives):
            yield from iter_archive_lines(p, reverse=True)
    else:
        for p in archives:
            yield from iter_archive_lines(p, reverse=False)
        if log_path.exists():
            yield from iter_lines_forward(log_path)


def _sha256_lines(lines) -> str:
    h = hashlib.sha256()
    for line in lines:
        h.update(line.encode("utf-8"))
    return h.hexdigest()


def rotate_log(
    log_path: Path,
    boundary_event: str = "compaction_detected",
    preset: int = LZMA_PRESET,
    keep_current_cycle: bool = True,
) -> dict:
    """Move history older than the current cycle into a verified archive.

    Returns a dict describing what happened; ``rotated`` is False when there was
    nothing older than the current cycle, which is the ordinary no-op case.

    The current cycle stays in the live log deliberately. Cycle-scoped reads are
    the common path and the default, so leaving the open cycle live means the
    common path never touches an archive and does not get slower.

    Ordering is the safety property: archive written -> archive read back and
    hash-compared -> only then is the live log truncated, all under one
    exclusive lock. The exposure window is the kept lines held in memory between
    truncate and rewrite, and it is bounded by ONE CYCLE rather than by the log,
    because everything older is already durably in the verified archive.
    """
    log_path = Path(log_path)
    if not log_path.exists():
        return {"rotated": False, "reason": "no log"}

    with open(log_path, "r+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            lines = fh.readlines()
            if not lines:
                return {"rotated": False, "reason": "empty log"}

            split = 0
            if keep_current_cycle:
                for i in range(len(lines) - 1, -1, -1):
                    try:
                        if json.loads(lines[i]).get("event") == boundary_event:
                            split = i
                            break
                    except (json.JSONDecodeError, ValueError):
                        continue

            to_archive, to_keep = lines[:split], lines[split:]
            if not to_archive:
                return {"rotated": False,
                        "reason": "nothing older than the current cycle"}

            stamps = []
            for line in to_archive:
                try:
                    ts = json.loads(line).get("timestamp")
                    if isinstance(ts, (int, float)):
                        stamps.append(ts)
                except (json.JSONDecodeError, ValueError):
                    continue
            if not stamps:
                return {"rotated": False, "reason": "no parseable timestamps"}

            dest_dir = archive_dir(log_path)
            dest_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            dest = dest_dir / archive_name(min(stamps), max(stamps))

            expect_hash = _sha256_lines(to_archive)

            # Write to a temp beside the destination, then move into place; a
            # partially written archive must never be nameable as a real one.
            # The temp is DOT-PREFIXED rather than dot-suffixed so it keeps the
            # codec suffix (verification reads it back through the same
            # dispatcher a real archive uses) while failing the ARCHIVE_PREFIX
            # test in `list_archives`, so a crash mid-write leaves something no
            # reader will ever mistake for history.
            tmp = dest.with_name("." + dest.name)
            with lzma.open(tmp, "wt", encoding="utf-8", preset=preset) as out:
                out.writelines(to_archive)

            # VERIFY BY READING BACK, not by trusting the write returned.
            got_lines = list(iter_archive_lines(tmp, reverse=False))
            if len(got_lines) != len(to_archive):
                tmp.unlink(missing_ok=True)
                raise RuntimeError(
                    f"archive verification failed: wrote {len(to_archive)} "
                    f"lines, read back {len(got_lines)}. Live log untouched."
                )
            if _sha256_lines(got_lines) != expect_hash:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(
                    "archive verification failed: content hash mismatch. "
                    "Live log untouched."
                )

            os.replace(tmp, dest)
            dest.chmod(0o600)

            # Truncate IN PLACE rather than replacing the file: a rename would
            # change the inode, and any writer holding the old one would append
            # into a file nothing reads.
            fh.seek(0)
            fh.truncate()
            fh.writelines(to_keep)
            fh.flush()
            os.fsync(fh.fileno())

            return {
                "rotated": True,
                "archive": str(dest),
                "archived_lines": len(to_archive),
                "kept_lines": len(to_keep),
                "archive_bytes": dest.stat().st_size,
                "sha256": expect_hash,
            }
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


__all__ = [
    "ARCHIVE_DIRNAME",
    "archive_dir",
    "archive_name",
    "parse_archive_range",
    "list_archives",
    "select_archives",
    "iter_archive_lines",
    "iter_log_lines",
    "rotate_log",
]
