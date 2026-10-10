"""Replace a file whole or not at all.

Opening a file with mode "w" empties it before anything is written, so a write that
fails part way (a full disk, a killed process) leaves an empty or half-written file
where a good one was. On 2026-10-10 a full /home did exactly that to a task file: the
task vanished from the tree, and the only copy of its creation was in the event log.

``write_text_atomic`` writes a temporary file beside the target, flushes it to disk,
and renames it over the target, which POSIX makes atomic within one filesystem. A
failure leaves the old file as it was and removes the temporary one.
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
        if mode is not None:
            os.chmod(tmp, mode)
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
