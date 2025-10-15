"""
Sidecar file management for hook state and consciousness awareness.

Uses unified paths: /tmp/macf/{agent_id}/{session_id}/hooks/
"""
import sys
from io import StringIO
from pathlib import Path
from typing import Optional, Tuple

# Import from centralized utils
from ..utils import (
    get_current_session_id,
    get_hooks_dir,
    write_json_safely,
    read_json_safely
)
from .logging import log_hook_event
from ..config import ConsciousnessConfig


class OutputCapture:
    """
    Context manager to capture stdout and stderr output from hook execution.

    Usage:
        with OutputCapture() as capture:
            print("Important message")
            print("Error message", file=sys.stderr)

        stdout, stderr = capture.get_output()
    """

    def __init__(self):
        self._stdout_buffer = StringIO()
        self._stderr_buffer = StringIO()
        self._original_stdout = None
        self._original_stderr = None

    def __enter__(self):
        """Start capturing output."""
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = self._stdout_buffer
        sys.stderr = self._stderr_buffer
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop capturing output."""
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        return False  # Don't suppress exceptions

    def get_output(self) -> Tuple[str, str]:
        """
        Get captured output.

        Returns:
            Tuple of (stdout, stderr) strings
        """
        return (
            self._stdout_buffer.getvalue(),
            self._stderr_buffer.getvalue()
        )


def update_sidecar(
    hook_name: str,
    state: dict,
    stdout: Optional[str] = None,
    stderr: Optional[str] = None
) -> None:
    """
    Update session-specific sidecar file in hooks/ subdirectory.

    Args:
        hook_name: Name of the hook
        state: State data (should include session_id)
        stdout: Captured stdout (optional)
        stderr: Captured stderr (optional)
    """
    try:
        # Get session_id
        session_id = state.get("session_id")
        if not session_id or session_id == "unknown":
            session_id = get_current_session_id()

        # Get hooks directory
        hooks_dir = get_hooks_dir(session_id, create=True)
        if not hooks_dir:
            return

        sidecar_path = hooks_dir / f"sidecar_{hook_name}.json"

        # Load previous state for logging
        previous_state = read_json_safely(sidecar_path)

        # Log state change
        if previous_state:
            log_hook_event({
                "hook_name": hook_name,
                "event_type": "SIDECAR_UPDATE",
                "session_id": session_id
            })

        # Build new state
        new_state = {
            "hook_name": hook_name,
            "session_id": session_id,
            **state
        }

        # Add captured output if provided
        if stdout is not None:
            new_state["stdout_captured"] = stdout
        if stderr is not None:
            new_state["stderr_captured"] = stderr

        # Write sidecar file
        write_json_safely(sidecar_path, new_state)

    except Exception as e:
        print(f"Sidecar update error: {e}", file=sys.stderr)


def read_sidecar(
    hook_name: str,
    session_id: Optional[str] = None
) -> dict:
    """
    Read sidecar file from hooks/ subdirectory.

    Args:
        hook_name: Name of the hook
        session_id: Session ID (auto-detected if None)

    Returns:
        Sidecar state dict or empty dict if not found
    """
    try:
        if not session_id:
            session_id = get_current_session_id()

        hooks_dir = get_hooks_dir(session_id, create=False)
        if not hooks_dir:
            return {}

        sidecar_path = hooks_dir / f"sidecar_{hook_name}.json"
        return read_json_safely(sidecar_path)

    except Exception:
        return {}