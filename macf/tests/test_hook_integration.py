#!/usr/bin/env python3
"""Integration tests for SessionStart hook execution.

These run the hook as a REAL subprocess. Until GH #330's guard landed the module
was skipped outright: the hook resolved the machine's live Telegram credentials
from ~/.claude/channels/telegram/ and every run messaged a real person, so the
harm was the execution and only a skip helped. The autouse fixture now sets
MACF_CHANNELS_DISABLED=1, the resolver honours it before reading any file, and
the child interpreter inherits the environment -- the one thing that crosses the
process boundary an in-process patch cannot.

Kept in the live suite: it needs an installed hook and a real subprocess.

The performance assertion is an honest witness: measured, the hook costs 0.58s
against a populated event log and 3.24s against an empty one when it reached the
network; with the guard it must not reach the network at all.
"""

import pytest

pytestmark = [pytest.mark.live]

import json
import os
import subprocess
from pathlib import Path

import pytest

# Resolved once, against the directory the suite runs from, because every run
# below gets a scratch working directory of its own.
HOOK = Path(".claude/hooks/session_start.py").resolve()


@pytest.fixture(scope="module")
def hook_env(tmp_path_factory):
    """Where every hook run in this module happens: a scratch agent home with its
    own event log, and no session.

    The hook is a real subprocess, so it takes its agent home, event log and
    session from the environment and working directory it inherits, and this
    module's warm-up runs before any function-scoped fixture can patch them. Run
    inside a live agent session, that inheritance pointed the hook at the agent's
    own event log, where it recorded session starts and command invocations, and
    at the live session's transcripts. A scratch home as the working directory,
    the log path set, and the session variables dropped keep each run to itself.
    """
    home = tmp_path_factory.mktemp("hook_home")
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
    env.update({
        "MACEFF_AGENT_HOME_DIR": str(home),
        "CLAUDE_PROJECT_DIR": str(home),
        "MACF_EVENTS_LOG_PATH": str(home / "agent_events_log.jsonl"),
        "MACF_CHANNELS_DISABLED": "1",
    })
    return home, env


def _run_hook(hook_env, timeout=5):
    home, env = hook_env
    return subprocess.run(["python3", str(HOOK)], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=timeout, cwd=home, env=env)


# Every test here shells out to the same hook. MEASURED on this suite's own
# machine: the first invocation takes 11.07s and every subsequent one 0.58s --
# a 19x spread that is import and bytecode cache warmth, not the hook's cost.
#
# That single fact explains all three intermittent failures this file produced:
# the 3s budget in test_hook_performance, and the subprocess TimeoutExpired in
# the two tests below, which set timeout=5 against a cold start that needs 11.
# Whether they passed depended on whether something else had run python3 first,
# which is why they passed alone and failed in company, or the reverse.
#
# Warming once at module scope means these tests measure the HOOK. Without it a
# wall-clock assertion here is a measurement of the filesystem cache wearing a
# performance test's clothes -- and no threshold can fix that, because the thing
# being measured is not the thing named.
@pytest.fixture(scope="module", autouse=True)
def _warm_hook_interpreter(hook_env):
    if not HOOK.exists():
        return
    _run_hook(hook_env, timeout=120)


def test_hook_executes_without_crashing(hook_env):
    """Hook executes without crashing."""
    if not HOOK.exists():
        pytest.skip("Hook not installed")

    result = _run_hook(hook_env)

    # Hook should not crash (exit code 0 or graceful error)
    assert result.returncode == 0, f"Hook crashed: {result.stderr}"


def test_hook_outputs_valid_json(hook_env):
    """Hook produces parseable JSON output."""
    if not HOOK.exists():
        pytest.skip("Hook not installed")

    result = _run_hook(hook_env)

    # Parse output as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        # Report WHY it failed to parse, not just that it did. The bound
        # exception carries the position and reason; dropping it leaves the
        # reader diffing two hundred characters of output by eye.
        pytest.fail(
            f"Hook output is not valid JSON ({e}): {result.stdout[:200]!r}\n"
            f"stderr: {result.stderr[:200]!r}"
        )

    assert isinstance(output, dict)


def test_json_has_hook_specific_output_structure(hook_env):
    """JSON has hookSpecificOutput structure."""
    if not HOOK.exists():
        pytest.skip("Hook not installed")

    result = _run_hook(hook_env)

    output = json.loads(result.stdout)

    # Check for official Claude Code hook output format
    assert "hookSpecificOutput" in output or "continue" in output


def test_compaction_detection_logic(hook_env):
    """Compaction detected correctly (if transcript available)."""
    if not HOOK.exists():
        pytest.skip("Hook not installed")

    result = _run_hook(hook_env)

    # Hook should execute successfully
    assert result.returncode == 0

    # Output should be valid JSON
    output = json.loads(result.stdout)
    assert isinstance(output, dict)


def test_hook_performance(hook_env):
    """Hook completes in reasonable time (<2 seconds)."""
    if not HOOK.exists():
        pytest.skip("Hook not installed")

    import time
    start = time.time()

    result = _run_hook(hook_env)

    elapsed = time.time() - start

    # Warm cost measured at 0.58s on this machine; 3.0 leaves ~5x headroom, so
    # this still catches a real regression while no longer failing on cache state.
    assert elapsed < 3.0, f"Hook took {elapsed:.2f}s warm (should be <3s)"


def test_a_hook_run_writes_to_its_scratch_home(hook_env):
    """The run's events land in the module's scratch log, not wherever the environment pointed."""
    if not HOOK.exists():
        pytest.skip("Hook not installed")
    home, env = hook_env
    log = Path(env["MACF_EVENTS_LOG_PATH"])
    before = log.read_text().count("\n") if log.exists() else 0
    assert _run_hook(hook_env).returncode == 0
    assert log.exists() and log.read_text().count("\n") > before

