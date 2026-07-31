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


def _run_init(home, *, host_home=None, extra_args=()):
    """Run `agent init -y` against an isolated agent home.

    ``host_home`` overrides ``HOME``, which isolates the *global* identity
    scope. Without it the developer's own ``~/.maceff_primary_agent.id`` is
    visible to the test and identity assertions become host-dependent —
    passing on a machine with no global id and failing on one with.
    """
    env = {**os.environ, "MACEFF_AGENT_HOME_DIR": str(home)}
    if host_home is not None:
        env["HOME"] = str(host_home)
    return subprocess.run(
        ["macf_tools", "agent", "init", "-y", *extra_args],
        capture_output=True, text=True, env=env,
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


@pytest.fixture
def host_home(tmp_path):
    """An empty stand-in for ``~`` so the global identity scope is isolated."""
    home = tmp_path / "hosthome"
    home.mkdir()
    return home


class TestAgentUuidMint:
    """`agent init` establishes the agent UUID so identity never resolves to
    @unknown (#131) — without ever silently changing it (#180)."""

    def test_mints_uuid_when_absent(self, agent_home, host_home):
        result = _run_init(agent_home, host_home=host_home)
        assert result.returncode == 0, result.stdout + result.stderr

        uuid_file = agent_home / ".maceff_primary_agent.id"
        assert uuid_file.exists(), "agent init did not mint the UUID file"
        assert uuid_file.read_text().strip(), "UUID file is empty"
        # Owner-only: the id is an identity credential, not world-readable trivia.
        assert (uuid_file.stat().st_mode & 0o077) == 0
        assert "Minted agent UUID" in result.stdout

    def test_mint_is_idempotent(self, agent_home, host_home):
        """A second init must not re-roll an established identity."""
        _run_init(agent_home, host_home=host_home)
        uuid_file = agent_home / ".maceff_primary_agent.id"
        first = uuid_file.read_text()

        result = _run_init(agent_home, host_home=host_home)
        assert uuid_file.read_text() == first, "re-init changed the agent UUID"
        assert "Minted agent UUID" not in result.stdout
        assert "Agent UUID present" in result.stdout

    def test_transfers_resolving_global_identity_rather_than_shadowing_it(
        self, agent_home, host_home
    ):
        """The #180 regression: an identity that already resolves globally is
        carried into the project file, not shadowed by a fresh one.

        Minting here overwrites nothing on disk, which is why it read as safe —
        but the project file outranks the global one in the resolver, so the
        agent's calling card changes anyway.
        """
        established = "a1b2c3d4-0000-4000-8000-000000000001"
        (host_home / ".maceff_primary_agent.id").write_text(established + "\n")

        result = _run_init(agent_home, host_home=host_home)
        assert result.returncode == 0, result.stdout + result.stderr

        uuid_file = agent_home / ".maceff_primary_agent.id"
        assert uuid_file.read_text().strip() == established, (
            "init minted a new identity over one that already resolved globally"
        )
        assert (host_home / ".maceff_primary_agent.id").read_text().strip() == established
        assert "Transferred agent UUID" in result.stdout
        assert "resolves from another scope" in result.stdout
        assert "Minted agent UUID" not in result.stdout

    def test_mint_fresh_id_opts_into_a_new_identity(self, agent_home, host_home):
        """The deliberate case stays available behind an explicit flag."""
        established = "a1b2c3d4-0000-4000-8000-000000000001"
        (host_home / ".maceff_primary_agent.id").write_text(established + "\n")

        result = _run_init(
            agent_home, host_home=host_home, extra_args=("--mint-fresh-id",)
        )
        assert result.returncode == 0, result.stdout + result.stderr

        minted = (agent_home / ".maceff_primary_agent.id").read_text().strip()
        assert minted and minted != established
        assert "Minted agent UUID" in result.stdout
