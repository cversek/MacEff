"""A deployment can declare Claude Code's prompt suggestions off.

The settings model forbids unknown keys, so `promptSuggestionEnabled` could not
be declared at all: writing it into agents.yaml would fail provisioning. The
only way to turn suggestions off was a hand edit to one home's settings.json,
which a rebuilt home would not have.

start.py writes `ClaudeCodeSettingsConfig.model_dump(exclude_none=True)` into
~/.claude/settings.json, so the dump is the thing to test: `false` must be
written, and an unset value must be absent so the client keeps its own default.
"""
from macf.models.agent_spec import AgentSpec, ClaudeCodeSettingsConfig


def _spec(settings):
    return AgentSpec(username="pa_seat", personality="agents/seat.md",
                     claude_config={"settings": settings})


def test_declared_off_loads_and_is_written():
    settings = _spec({"promptSuggestionEnabled": False}).claude_config.settings
    assert settings.promptSuggestionEnabled is False
    assert settings.model_dump(exclude_none=True)["promptSuggestionEnabled"] is False


def test_unset_leaves_the_client_default():
    dumped = ClaudeCodeSettingsConfig().model_dump(exclude_none=True)
    assert "promptSuggestionEnabled" not in dumped


def test_declared_on_is_written_too():
    dumped = ClaudeCodeSettingsConfig(promptSuggestionEnabled=True).model_dump(exclude_none=True)
    assert dumped["promptSuggestionEnabled"] is True
