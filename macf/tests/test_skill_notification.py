"""Skill invocations are identifiable in notifications (cversek/MacEff#163).

From a phone, "⚙️ Skill" is nearly information-free — the skill *name* is the
entire signal. Skills also need a glyph distinct from the generic gear so they
are scannable in a channel timeline.
"""
from unittest.mock import Mock

from macf.hooks.handle_permission_request import _send_permission_preview


def _capture(tool_name, tool_input):
    sent = []
    _send_permission_preview(
        tool_name, tool_input,
        send_notification=lambda msg, **kw: sent.append(msg),
        send_document=Mock(),
        html_escape=lambda s: s,
    )
    return sent


def test_skill_notification_names_the_skill():
    sent = _capture("Skill", {"skill": "maceff:jotewr"})
    assert len(sent) == 1
    assert "maceff:jotewr" in sent[0]


def test_skill_notification_uses_distinct_glyph():
    """Not the generic gear Bash uses — skills must stand out."""
    skill_msg = _capture("Skill", {"skill": "maceff:ccp"})[0]
    bash_msg = _capture("Bash", {"command": "ls"})[0]
    assert "🎛️" in skill_msg
    assert "⚙️" not in skill_msg
    assert "⚙️" in bash_msg  # unchanged


def test_skill_notification_includes_short_args():
    sent = _capture("Skill", {"skill": "maceff:jotewr", "args": "5k reflection"})
    assert "5k reflection" in sent[0]


def test_skill_notification_truncates_long_args():
    sent = _capture("Skill", {"skill": "s", "args": "x" * 500})
    assert "…" in sent[0]
    assert len(sent[0]) < 500


def test_skill_notification_survives_missing_fields():
    """A payload without skill/args must not raise."""
    sent = _capture("Skill", {})
    assert "unknown" in sent[0]
