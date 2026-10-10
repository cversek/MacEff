"""Replace a file whole or not at all.

Opening a file with mode "w" empties it before anything is written, so a write that
fails part way (a full disk, a killed process) leaves an empty or half-written file
where a good one was. On 2026-10-10 a full /home did exactly that to a task file: the
task vanished from the tree, and the only copy of its creation was in the event log.

``write_text_atomic`` writes a temporary file beside the target and renames it over the
target, which POSIX makes atomic within one filesystem: a reader sees the old file or the
new one, never part, and so do two writers racing (each rename replaces the file whole).
A failure leaves the old file as it was and removes the temporary one. The file is
fsync'd before the rename; that narrows, but does not close, the window in which a power
loss could lose the write (macOS's ``fsync`` does not flush the drive's own cache, and the
directory is not synced). Atomicity is the promise, not durability.

The rename needs write permission on the target's directory, not on the file. A caller
writing into a directory it keeps read-only (the task store, born 555) lifts it around the
write: ``macf.task.reader.writable_store``.
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Union


def write_text_atomic(path: Union[str, Path], text: str, encoding: str = "utf-8") -> None:
    """Write *text* to *path* so a reader sees the old content or the new, never part.

    The file's permission bits are kept when it exists. Raises whatever the write
    raised, after removing the temporary file.
    """
    path = Path(path)
    mode = None
    try:
        mode = path.stat().st_mode & 0o7777
    except FileNotFoundError:
        pass
    if mode is None:
        # A new file gets what open() would have given it, not mkstemp's 0600.
        umask = os.umask(0)
        os.umask(umask)
        new_mode = 0o666 & ~umask
    else:
        new_mode = mode
    # A rename needs write permission on the directory, not on the file, so without this a
    # read-only file (the 444 sentinel task) would be replaced where open(path, "w") refused.
    if mode is not None and not os.access(path, os.W_OK):
        raise PermissionError(f"{path} is read-only; not replacing it")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, new_mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def write_json_atomic(path: Union[str, Path], data: Any, indent: int = 2) -> None:
    """``json.dump`` to *path*, whole or not at all. The JSON is built before the file is
    touched, so data that cannot be serialized leaves the old file unchanged too."""
    write_text_atomic(path, json.dumps(data, indent=indent))
