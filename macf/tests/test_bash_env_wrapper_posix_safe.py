"""The BASH_ENV wrapper must not break a POSIX login shell.

``/etc/profile.d/maceff-bash-env.sh`` has two readers and only one was designed
for. It is the BASH_ENV target, and it also sits in ``/etc/profile.d``, which
EVERY POSIX login shell sources. Its ``#!/bin/bash`` line does not restrict it:
a shebang is read by the kernel on exec and ignored entirely on ``.``.

So dash followed it into ``~/.bash_init.sh``, which sources framework shell
scripts that legitimately use bash arrays -- and the login shell ABORTED before
running its command WHILE EXITING 0. A ``/bin/sh`` cron entry in an agent
account would do nothing and report success.

Three assertions, because the obvious fix passes the first one by accident:
guarding the wrapper so hard that bash stops sourcing anything would make dash
clean and the deployment useless. The bash-side assertion is what makes the
dash-side one mean something.
"""
import importlib.util
import subprocess
from pathlib import Path

import pytest

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"


def _load_start():
    spec = importlib.util.spec_from_file_location("maceff_start_bashenv", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WRAPPER = _load_start().BASH_ENV_WRAPPER

# Verbatim shape of what actually broke: bash array syntax dash cannot parse.
BASH_ONLY_INIT = 'chan_args=()\nchan_args+=(--channel "x")\nexport MACEFF_PROOF=reached\n'


def _sh_is_posix() -> bool:
    """True when /bin/sh is a non-bash shell, which is what this file tests."""
    out = subprocess.run(["/bin/sh", "-c", "echo ${BASH_VERSION:-none}"],
                         capture_output=True, text=True)
    return out.stdout.strip() == "none"


@pytest.fixture
def home(tmp_path):
    (tmp_path / ".bash_init.sh").write_text(BASH_ONLY_INIT)
    return tmp_path


def _run(shell, wrapper_text, home_dir, tmp_path, command):
    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text(wrapper_text)
    return subprocess.run(
        [shell, "-c", f". {wrapper}; {command}"],
        capture_output=True, text=True, env={"HOME": str(home_dir), "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.skipif(not _sh_is_posix(), reason="/bin/sh is bash here; nothing to test")
def test_posix_shell_survives_the_wrapper(home, tmp_path):
    """The regression: dash must reach its own command, not die in the profile."""
    r = _run("/bin/sh", WRAPPER, home, tmp_path, "echo MARKER")
    assert "MARKER" in r.stdout, (
        f"POSIX shell never reached its command. stderr: {r.stderr!r}"
    )
    assert "Syntax error" not in r.stderr, f"unexpected stderr: {r.stderr!r}"


@pytest.mark.skipif(not _sh_is_posix(), reason="/bin/sh is bash here; nothing to test")
def test_the_guard_is_what_saves_it(home, tmp_path):
    """CONTROL: without the guard this scenario MUST fail.

    Without it, the first test could pass for reasons unrelated to the fix --
    a tmp HOME with no init file, say. This pins the failure to the guard.
    """
    unguarded = WRAPPER.replace('if [ -n "$BASH_VERSION" ]; then', "if true; then", 1)
    assert unguarded != WRAPPER, "guard not found in wrapper — test is stale"
    r = _run("/bin/sh", unguarded, home, tmp_path, "echo MARKER")
    assert "MARKER" not in r.stdout, (
        "the unguarded wrapper did NOT break the POSIX shell, so the guarded "
        "one proves nothing"
    )


def test_bash_still_sources_the_user_init(home, tmp_path):
    """The guard must scope the wrapper to bash, not disable it.

    Guarding it into a no-op would satisfy the dash test and silently strip
    every agent's environment. This is the assertion that forbids that.
    """
    r = _run("/bin/bash", WRAPPER, home, tmp_path, 'echo "PROOF=$MACEFF_PROOF"')
    assert "PROOF=reached" in r.stdout, (
        f"bash no longer sources ~/.bash_init.sh — the guard over-reached. "
        f"stdout: {r.stdout!r} stderr: {r.stderr!r}"
    )
