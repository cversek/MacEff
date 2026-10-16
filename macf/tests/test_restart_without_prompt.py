"""A supervised restart never waits on a person (MIS-0002 landing, "channel first,
keystrokes as the fallback", success criterion 3; persistent_layer 1.7).

Claude Code asks a person to confirm a channel loaded under its development flag, at every
start. A restart the primal daemon performs has no person to answer, so the session's command
must never carry that flag: a channel the session needs loads through an allowlist or an
official listing, and until it does the keystroke fallback wakes the session (1.9).
Observed on the host on 2026-10-14: a killed client was restarted by the daemon and resumed
the conversation in four seconds with nobody at the keyboard.
"""
from pathlib import Path

from macf.utils.harness import HarnessParams, render_child

DEVELOPMENT_FLAGS = ("--dangerously-load-development-channels", "development-channels")


def _child(tmp_path, channels):
    return render_child(HarnessParams(agent="Tester_abc123", home=tmp_path, python=Path("/bin/true"),
                                      macf_tools=tmp_path / "macf_tools", child_path=tmp_path / "child",
                                      registry_dir=tmp_path / "reg", channels=channels))


def test_the_session_command_never_carries_a_development_channel_flag(tmp_path):
    for channels in ([], ["plugin:telegram@claude-plugins-official"],
                     ["plugin:telegram@claude-plugins-official", "plugin:maceff@maceff"]):
        script = _child(tmp_path, channels)
        assert not any(flag in script for flag in DEVELOPMENT_FLAGS), (channels, "a restart would wait on a person")
        for c in channels:
            assert c in script, "the declared channels are still passed, by --channels"
