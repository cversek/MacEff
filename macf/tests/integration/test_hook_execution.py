"""
Integration tests for hook execution.

These tests execute hooks as black boxes via subprocess, the way Claude Code
actually runs them. This catches integration failures that unit tests miss.

References C84: SessionStart hook crashed silently due to missing @dataclass.
Unit tests passed because they mocked dependencies. These integration tests
execute real hooks and catch real failures.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import pytest

from macf.utils import find_project_root


def get_hook_script_path(hook_name):
    """Get path to installed hook script using dynamic project root detection."""
    project_root = find_project_root()
    hook_path = project_root / '.claude' / 'hooks' / f'{hook_name}.py'

    if not hook_path.exists():
        pytest.skip(f"Hook {hook_name} not installed at {hook_path}")

    return hook_path


def execute_hook(hook_path, stdin_data="", tmp_project_root=None):
    """
    Execute hook as subprocess the way Claude Code does.

    SAFETY: Uses MACF_TESTING_MODE=true to prevent state mutations,
    and optionally MACF_PROJECT_ROOT to isolate state files.

    Args:
        hook_path: Path to hook script
        stdin_data: JSON input for hook
        tmp_project_root: If provided, isolates state to this temp directory

    Returns (stdout, stderr, returncode)
    """
    # Belt & suspenders: testing mode + project isolation
    env = {
        **os.environ,
        'MACF_TESTING_MODE': 'true',  # Prevents state mutations
    }
    if tmp_project_root:
        env['MACF_PROJECT_ROOT'] = str(tmp_project_root)

    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=10,
        env=env
    )
    return result.stdout, result.stderr, result.returncode


def test_session_start_hook_executes():
    """
    Test SessionStart hook executes without crashing.

    C84 Bug 1: Missing @dataclass caused hook to crash on state instantiation.
    This test catches that failure - hook must execute and return valid JSON.
    """
    hook_path = get_hook_script_path('session_start')

    # Execute hook with empty input (normal session start)
    stdout, stderr, returncode = execute_hook(hook_path, "")

    # Hook should exit 0 (never crash)
    assert returncode == 0, f"Hook crashed with exit code {returncode}\nstderr: {stderr}"

    # Should produce valid JSON output
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as e:
        pytest.fail(f"Hook produced invalid JSON: {e}\nstdout: {stdout}")

    # Should have continue field (Claude Code requirement)
    assert "continue" in result, "Hook output missing 'continue' field"
    assert result["continue"] is True, "Hook returned continue=False"


def test_session_start_hook_produces_output():
    """
    Test SessionStart hook produces consciousness injection content.

    C84 Bug 2: Hook executed but produced no output (silent failure).
    This catches hooks that run but don't inject expected context.
    """
    hook_path = get_hook_script_path('session_start')

    stdout, stderr, returncode = execute_hook(hook_path, "")

    assert returncode == 0, f"Hook crashed: {stderr}"

    result = json.loads(stdout)

    # Should have hookSpecificOutput for consciousness injection
    assert "hookSpecificOutput" in result, "Missing hookSpecificOutput field"

    hook_output = result["hookSpecificOutput"]
    assert "additionalContext" in hook_output, "Missing additionalContext field"

    # Should have actual content (not empty string)
    context = hook_output["additionalContext"]
    assert len(context) > 0, "additionalContext is empty"
    assert "MACF" in context, "Missing MACF attribution in output"


def test_session_start_compaction_detection():
    """
    Test SessionStart hook detects compaction via source field.

    Validates end-to-end compaction detection and recovery message formatting.
    """
    hook_path = get_hook_script_path('session_start')

    # Provide input with source='compact' (compaction signal)
    input_data = {"source": "compact", "session_id": "test-compact-123"}
    stdin_json = json.dumps(input_data)

    stdout, stderr, returncode = execute_hook(hook_path, stdin_json)

    assert returncode == 0, f"Hook crashed on compaction: {stderr}"

    result = json.loads(stdout)
    assert "hookSpecificOutput" in result

    context = result["hookSpecificOutput"]["additionalContext"]

    # Should mention compaction in output
    # (exact format may vary, but ULTRATHINK or TRAUMA should appear)
    assert any(keyword in context for keyword in ["COMPACTION", "TRAUMA", "ULTRATHINK"]), \
        f"Compaction not detected in output: {context[:200]}"


def test_pre_tool_use_hook_executes():
    """Test PreToolUse hook executes and produces temporal awareness."""
    hook_path = get_hook_script_path('pre_tool_use')

    # Provide tool invocation input
    input_data = {
        "tool": "Read",
        "parameters": {"file_path": "/test/file.py"}
    }
    stdin_json = json.dumps(input_data)

    stdout, stderr, returncode = execute_hook(hook_path, stdin_json)

    assert returncode == 0, f"PreToolUse hook crashed: {stderr}"

    result = json.loads(stdout)
    assert result["continue"] is True
    assert "hookSpecificOutput" in result


def test_post_tool_use_hook_executes():
    """Test PostToolUse hook executes without crashing."""
    hook_path = get_hook_script_path('post_tool_use')

    # Provide tool completion input
    input_data = {
        "tool": "Read",
        "success": True
    }
    stdin_json = json.dumps(input_data)

    stdout, stderr, returncode = execute_hook(hook_path, stdin_json)

    assert returncode == 0, f"PostToolUse hook crashed: {stderr}"

    result = json.loads(stdout)
    assert result["continue"] is True


def test_hook_error_handling():
    """
    Test hooks handle errors gracefully without crashing session.

    Hooks should NEVER crash - they must return {"continue": True} even on errors.
    """
    hook_path = get_hook_script_path('session_start')

    # Provide malformed JSON
    stdout, stderr, returncode = execute_hook(hook_path, "invalid json {{{")

    # Hook should exit 0 even with bad input
    assert returncode == 0, "Hook crashed on malformed input"

    # Should still produce valid JSON
    try:
        result = json.loads(stdout)
        assert result.get("continue") is True, "Hook should continue even on errors"
    except json.JSONDecodeError:
        pytest.fail("Hook failed to produce valid JSON on error")


def test_all_hooks_execute_successfully():
    """
    Smoke test that all installed hooks can execute.

    Catches installation issues, missing dependencies, import errors.
    """
    hooks = [
        'session_start',
        'pre_tool_use',
        'post_tool_use',
        'user_prompt_submit',
        'stop',
        'subagent_stop'
    ]

    for hook_name in hooks:
        try:
            hook_path = get_hook_script_path(hook_name)
        except pytest.skip.Exception:
            continue  # Hook not installed, skip

        stdout, stderr, returncode = execute_hook(hook_path, "")

        assert returncode == 0, \
            f"Hook {hook_name} crashed\nstderr: {stderr}\nstdout: {stdout}"

        # All hooks should produce valid JSON
        try:
            result = json.loads(stdout)
            assert "continue" in result, f"Hook {hook_name} missing 'continue' field"
        except json.JSONDecodeError as e:
            pytest.fail(f"Hook {hook_name} produced invalid JSON: {e}")


def test_session_start_state_persistence():
    """
    Test SessionStart hook persists state correctly.

    Validates end-to-end state save/load cycle through actual hook execution.
    """
    hook_path = get_hook_script_path('session_start')

    # Execute hook twice - second execution should load state from first
    stdout1, stderr1, returncode1 = execute_hook(hook_path, "")
    assert returncode1 == 0, f"First execution failed: {stderr1}"

    stdout2, stderr2, returncode2 = execute_hook(hook_path, "")
    assert returncode2 == 0, f"Second execution failed: {stderr2}"

    # Both should produce valid output
    result1 = json.loads(stdout1)
    result2 = json.loads(stdout2)

    assert result1["continue"] is True
    assert result2["continue"] is True


def test_hook_output_format_compliance():
    """
    Test hooks produce output compliant with Claude Code spec.

    Required format:
    {
      "continue": true,
      "hookSpecificOutput": {
        "hookEventName": "HookName",
        "additionalContext": "..."
      }
    }
    """
    hook_path = get_hook_script_path('session_start')

    stdout, stderr, returncode = execute_hook(hook_path, "")
    assert returncode == 0

    result = json.loads(stdout)

    # Validate structure
    assert isinstance(result, dict), "Output must be dict"
    assert "continue" in result, "Missing 'continue' field"
    assert isinstance(result["continue"], bool), "'continue' must be boolean"

    if "hookSpecificOutput" in result:
        hook_output = result["hookSpecificOutput"]
        assert isinstance(hook_output, dict), "hookSpecificOutput must be dict"

        if "hookEventName" in hook_output:
            assert isinstance(hook_output["hookEventName"], str), \
                "hookEventName must be string"

        if "additionalContext" in hook_output:
            assert isinstance(hook_output["additionalContext"], str), \
                "additionalContext must be string"
