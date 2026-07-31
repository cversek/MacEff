"""Preamble upgrade behavior for `macf_tools agent init` (issue #153).

An upgrade must leave exactly one managed preamble block. Blocks installed
before the boundary-marker convention sit *above* the boundary, in the region
otherwise treated as user content — they must still be recognized as managed
content (via their sentinels) and removed, without disturbing genuine user text.
"""
import os
import subprocess

import pytest


BOUNDARY = (
    "---\n\n"
    "<!-- ⚠️ DO NOT WRITE BELOW THIS LINE ⚠️ -->\n"
    "<!-- Framework preamble managed by macf_tools - edits below will be lost on upgrade -->\n"
    "<!-- Add custom policies and agent-specific content ABOVE this boundary -->\n"
)

USER_TEXT = "This is genuine user content that must survive an upgrade."


def _run_init(home):
    return subprocess.run(
        ["macf_tools", "agent", "init", "-y"],
        capture_output=True, text=True,
        env={**os.environ, "MACEFF_AGENT_HOME_DIR": str(home)},
    )


@pytest.fixture
def agent_home(tmp_path):
    home = tmp_path / "agenthome"
    home.mkdir()
    return home


def test_stale_preamble_above_boundary_is_removed(agent_home):
    """A pre-boundary preamble stranded above the boundary is stripped."""
    (agent_home / "CLAUDE.md").write_text(
        "<!-- MACEFF_PA_PREAMBLE_v1.3_START -->\n"
        "# OLD PREAMBLE v1.3\nSuperseded guidance.\n"
        "<!-- MACEFF_PA_PREAMBLE_v1.3_END -->\n\n"
        f"# My Custom Policies\n{USER_TEXT}\n\n"
        + BOUNDARY +
        "\n<!-- MACEFF_PA_PREAMBLE_v1.4_START -->\n# CURRENT\n"
        "<!-- MACEFF_PA_PREAMBLE_v1.4_END -->\n"
    )

    result = _run_init(agent_home)
    assert result.returncode == 0, result.stdout + result.stderr

    content = (agent_home / "CLAUDE.md").read_text()
    assert content.count("_START -->") == 1, f"expected one managed block:\n{content}"
    assert "OLD PREAMBLE v1.3" not in content, "stale preamble body survived"
    assert USER_TEXT in content, "genuine user content was destroyed"
    assert "Removing 1 stale preamble block(s)" in result.stdout


def test_user_content_without_stale_block_is_untouched(agent_home):
    """No sentinels above the boundary → user content passes through unchanged."""
    (agent_home / "CLAUDE.md").write_text(
        f"# My Custom Policies\n{USER_TEXT}\n\n" + BOUNDARY +
        "\n<!-- MACEFF_PA_PREAMBLE_v1.4_START -->\n# CURRENT\n"
        "<!-- MACEFF_PA_PREAMBLE_v1.4_END -->\n"
    )

    result = _run_init(agent_home)
    assert result.returncode == 0, result.stdout + result.stderr

    content = (agent_home / "CLAUDE.md").read_text()
    assert USER_TEXT in content
    assert content.count("_START -->") == 1
    assert "stale preamble block" not in result.stdout
