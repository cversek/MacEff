"""Regression tests for transcript-monitor daemonization (issue #54).

The bug: when a parent process inherits a pipe as its stderr (e.g.
`macf_tools mode set-work X 2>&1 | tail -50`), the old daemonize path only
redirected stdin/stdout and left stderr pointing at the parent's pipe.
After the parent exited, the pipe's write-end stayed held open by the
daemon's fd 2, so downstream `tail` hung until the daemon died.

The fix fully redirects stderr too, into a log file.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_detach_streams_releases_inherited_stderr_pipe(tmp_path):
    """A child process that calls _detach_standard_streams should release
    the parent pipe even though nothing else explicitly closes it.

    Run under subprocess so fd surgery stays isolated from the pytest process.
    The subprocess script:
      1. Opens a pipe
      2. dup2's the write-end to fd 2 (simulates `2>&1 | ...`)
      3. Closes the original write-end so only fd 2 keeps the pipe open
      4. Calls _detach_standard_streams()
      5. Reports the pipe-read-end status — should be EOF immediately
    """
    script = textwrap.dedent(f"""
        import os
        # Point XDG_RUNTIME_DIR at the tmp_path so the daemon log lives there
        os.environ["XDG_RUNTIME_DIR"] = {str(tmp_path)!r}
        from macf.transcript_monitor.daemon import _detach_standard_streams

        r, w = os.pipe()
        # Make fd 2 point at the pipe's write-end, as if the parent shell
        # had redirected stderr into a pipeline.
        os.dup2(w, 2)
        os.close(w)   # Only fd 2 references the write-end now.

        # Preserve a handle to the original stdout BEFORE detach — otherwise
        # _detach_standard_streams redirects fd 1 to /dev/null and the test
        # result line vanishes.
        saved_stdout = os.dup(1)

        _detach_standard_streams()

        # If the fix works, fd 2 no longer references the pipe, so reading
        # from the read-end returns EOF immediately.
        os.set_blocking(r, False)
        try:
            data = os.read(r, 1)
        except BlockingIOError:
            data = b"STILL_OPEN"  # pipe still has a write-end somewhere — BUG
        msg = "RESULT=" + ("EOF" if data == b"" else data.decode(errors="replace")) + "\\n"
        os.write(saved_stdout, msg.encode())
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=15,
    )
    assert "RESULT=EOF" in result.stdout, (
        f"Expected pipe to be EOF after _detach_standard_streams; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_detach_streams_writes_stderr_to_log_file(tmp_path):
    """After detaching, writes to stderr should land in the daemon log file,
    not vanish and not go to the inherited terminal."""
    script = textwrap.dedent(f"""
        import os, sys
        os.environ["XDG_RUNTIME_DIR"] = {str(tmp_path)!r}
        from macf.transcript_monitor.daemon import _detach_standard_streams

        _detach_standard_streams()
        # Bypass Python's buffered sys.stderr — write directly to fd 2.
        os.write(2, b"sentinel-stderr-line\\n")
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, f"subprocess failed: {result.stderr!r}"
    log_path = tmp_path / "macf_transcript_monitor.log"
    assert log_path.exists(), "daemon log file should exist after detach"
    assert "sentinel-stderr-line" in log_path.read_text()


def test_daemon_module_source_redirects_stderr(tmp_path):
    """Source-level regression: the daemonize path must route stderr through
    _detach_standard_streams, not leave it inherited. Guards against the fix
    silently regressing to the old dup2(devnull, 0..1)-only pattern."""
    import macf.transcript_monitor.daemon as daemon_mod
    source = Path(daemon_mod.__file__).read_text()
    # After the fix, the child block calls the helper.
    assert "_detach_standard_streams()" in source, (
        "expected daemon child block to call _detach_standard_streams()"
    )
    # And the comment preserving the old stderr-inheritance pattern is gone.
    assert "Keep stderr for logging" not in source, (
        "stale comment suggests the inherited-stderr bug has regressed"
    )
