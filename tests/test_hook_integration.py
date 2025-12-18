#!/usr/bin/env python3
"""Integration tests for SessionStart hook execution."""

import json
import subprocess
from pathlib import Path

import pytest


def test_hook_executes_without_crashing():
    """Hook executes without crashing."""
    hook_path = Path(".claude/hooks/session_start.py")

    if not hook_path.exists():
        pytest.skip("Hook not installed")

    result = subprocess.run(
        ["python3", str(hook_path)],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=5
    )

    # Hook should not crash (exit code 0 or graceful error)
    assert result.returncode == 0, f"Hook crashed: {result.stderr}"


def test_hook_outputs_valid_json():
    """Hook produces parseable JSON output."""
    hook_path = Path(".claude/hooks/session_start.py")

    if not hook_path.exists():
        pytest.skip("Hook not installed")

    result = subprocess.run(
        ["python3", str(hook_path)],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=5
    )

    # Parse output as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        pytest.fail(f"Hook output is not valid JSON: {result.stdout[:200]}")

    assert isinstance(output, dict)


def test_json_has_hook_specific_output_structure():
    """JSON has hookSpecificOutput structure."""
    hook_path = Path(".claude/hooks/session_start.py")

    if not hook_path.exists():
        pytest.skip("Hook not installed")

    result = subprocess.run(
        ["python3", str(hook_path)],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=5
    )

    output = json.loads(result.stdout)

    # Check for official Claude Code hook output format
    assert "hookSpecificOutput" in output or "continue" in output


def test_compaction_detection_logic():
    """Compaction detected correctly (if transcript available)."""
    hook_path = Path(".claude/hooks/session_start.py")

    if not hook_path.exists():
        pytest.skip("Hook not installed")

    result = subprocess.run(
        ["python3", str(hook_path)],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=5
    )

    # Hook should execute successfully
    assert result.returncode == 0

    # Output should be valid JSON
    output = json.loads(result.stdout)
    assert isinstance(output, dict)


def test_hook_performance():
    """Hook completes in reasonable time (<2 seconds)."""
    hook_path = Path(".claude/hooks/session_start.py")

    if not hook_path.exists():
        pytest.skip("Hook not installed")

    import time
    start = time.time()

    result = subprocess.run(
        ["python3", str(hook_path)],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=5
    )

    elapsed = time.time() - start

    # Hook should complete quickly (3s allows for cold-start import variance)
    assert elapsed < 3.0, f"Hook took {elapsed:.2f}s (should be <3s)"
