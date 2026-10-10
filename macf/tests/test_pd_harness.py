"""The Claude Code harness adapter's hold on the client's own compactions.

MIS-0002-R126 (adapter_MUST_turn_off_harness_idle_compaction): where the harness can
compact an idle session on its own, the adapter turns that off unless the declaration
keeps it. Claude Code compacts a session about 54 minutes after its last request once
the context passes a threshold, and from 2.1.290 the settings key ``idleCompaction``
set to false stops that alone, leaving compaction at the context limit on.
"""
import json

import pytest

from macf.utils.claude_settings import idle_compaction_status, set_idle_compaction


def _settings(root):
    return json.loads((root / ".claude" / "settings.local.json").read_text())


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text(json.dumps({"env": {"A": "1"}, "hooks": {}}))
    return tmp_path


def test_idle_compaction_off(project):
    """The adapter writes idleCompaction false and leaves every other key alone."""
    result = set_idle_compaction(False, client_version="2.1.296", project_root=project)
    settings = _settings(project)
    assert settings["idleCompaction"] is False
    assert settings["env"] == {"A": "1"} and "hooks" in settings
    assert result["changed"] is True
    assert idle_compaction_status(project)["state"] == "off"


def test_refuses_on_client_without_the_setting(project):
    """Before 2.1.290 the client ignores the key, so writing it would claim a protection that is not there."""
    with pytest.raises(ValueError, match="2.1.289"):
        set_idle_compaction(False, client_version="2.1.289", project_root=project)
    assert "idleCompaction" not in _settings(project)


def test_declaration_can_keep_idle_compaction(project):
    """When the declaration keeps idle compaction, the adapter writes nothing."""
    result = set_idle_compaction(False, client_version="2.1.296", project_root=project, keep=True)
    assert result["changed"] is False
    assert "idleCompaction" not in _settings(project)


def test_turning_it_back_on_removes_the_key(project):
    """`true` does not turn idle compaction on in the client, so on means the key is gone."""
    set_idle_compaction(False, client_version="2.1.296", project_root=project)
    set_idle_compaction(True, client_version="2.1.296", project_root=project)
    assert "idleCompaction" not in _settings(project)
    assert idle_compaction_status(project)["state"] == "client default"


def test_status_without_settings_file(tmp_path):
    """No settings file is the client default, reported plainly rather than raised."""
    status = idle_compaction_status(tmp_path)
    assert status["state"] == "client default"
    assert status["settings_path"].endswith("settings.local.json")
