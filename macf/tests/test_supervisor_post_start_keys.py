"""Post-start keystroke hook (cversek/MacEff#164).

Some deployments re-present the workspace-trust dialog on every relaunch, so a
supervisor-driven restart parks the child at an interactive prompt. Attended,
that is one keystroke; unattended, it is an indefinite hang that the supervisor
reads as a healthy child. The boot-path workaround (systemd ExecStartPost)
covers unit start only — not the supervisor's own restart cycles.
"""
import subprocess
from unittest.mock import patch

from macf.supervisor import _send_post_start_keys, launch_in_terminal, run_loop


def test_sends_configured_keys_to_the_session():
    with patch("subprocess.run") as run:
        _send_post_start_keys("mysession", "Enter", 0)
    assert run.call_args[0][0] == ["tmux", "send-keys", "-t", "mysession", "Enter"]


def test_waits_the_configured_delay_before_sending():
    """The delay exists so the prompt has time to appear."""
    with patch("time.sleep") as slept, patch("subprocess.run"):
        _send_post_start_keys("s", "Enter", 18)
    slept.assert_called_once_with(18)


def test_negative_delay_is_clamped():
    with patch("time.sleep") as slept, patch("subprocess.run"):
        _send_post_start_keys("s", "Enter", -5)
    slept.assert_called_once_with(0)


def test_tmux_failure_is_non_fatal():
    """A failed keystroke must never take down the supervisor."""
    with patch("time.sleep"), patch("subprocess.run", side_effect=OSError("no tmux")):
        _send_post_start_keys("s", "Enter", 0)  # must not raise


def test_run_loop_accepts_post_start_params():
    """Signature contract: the supervisor entrypoint plumbs both params."""
    import inspect
    params = inspect.signature(run_loop).parameters
    assert "post_start_keys" in params
    assert params["post_start_delay"].default == 18


def test_launch_forwards_post_start_flags():
    """launch_in_terminal must pass the flags to the spawned supervisor."""
    import inspect
    params = inspect.signature(launch_in_terminal).parameters
    assert "post_start_keys" in params
    assert "post_start_delay" in params
