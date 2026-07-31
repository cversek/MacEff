"""Structural tests for the maceff_tools/*-sync scripts.

These scripts had been broken for as long as the repo layout had been current,
and nothing announced it: the directory move from ``tools/bin/`` to
``maceff_tools/`` left ``REPO_ROOT`` resolving to the repo's *parent*, a later
move of ``policies/`` and ``templates/`` under ``framework/`` invalidated every
source prefix, ``framework-upgrade`` kept calling a ``tools-sync`` script that
had been deliberately deleted, and no sync path existed at all for
``commands/``, ``skills/``, ``subagents/``, ``output-styles/``.

Each test runs the real script against a synthetic repo tree, so a future
restructure that moves these directories again fails here instead of silently
producing an empty deploy tree.
"""

import os
import shutil
import subprocess

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOOLS = os.path.join(REPO, "maceff_tools")

ASSET_TREES = ("commands", "skills", "subagents", "output-styles")


def _fake_repo(root):
    """Build a minimal repo mirroring the real layout the scripts expect."""
    tools = root / "maceff_tools"
    tools.mkdir(parents=True)
    for script in ("policy-sync", "template-sync", "assets-sync", "framework-upgrade"):
        dest = tools / script
        shutil.copy2(os.path.join(TOOLS, script), dest)
        dest.chmod(0o755)

    policies = root / "framework" / "policies" / "base"
    policies.mkdir(parents=True)
    (policies / "core_principles.md").write_text("# core\n")
    (root / "framework" / "policies" / "manifest.json").write_text('{"policies": []}\n')

    templates = root / "framework" / "templates"
    templates.mkdir(parents=True)
    (templates / "PA_PREAMBLE.md").write_text("# preamble\n")

    for tree in ASSET_TREES:
        d = root / "framework" / tree
        d.mkdir(parents=True)
        (d / f"{tree}-sample.md").write_text(f"# {tree}\n")

    (root / ".maceff" / "framework").mkdir(parents=True)
    return root


def _run(root, script, *args):
    return subprocess.run(
        [str(root / "maceff_tools" / script), *args],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path):
    return _fake_repo(tmp_path / "MacEff")


class TestPolicySync:
    def test_resolves_repo_root_one_level_up(self, repo):
        """REPO_ROOT must be the repo, not its parent.

        With the old ``../..`` this cannot pass: the source path would land
        outside the fake repo entirely.
        """
        result = _run(repo, "policy-sync")
        assert result.returncode == 0, result.stderr
        synced = repo / ".maceff/framework/policies/sets/base/core_principles.md"
        assert synced.is_file()

    def test_reads_source_from_framework_policies(self, repo):
        """The source prefix is framework/policies/, not policies/."""
        shutil.rmtree(repo / "framework" / "policies" / "base")
        result = _run(repo, "policy-sync")
        assert result.returncode == 1
        assert "source policy set not found" in result.stderr

    def test_syncs_the_manifest_alongside_the_set(self, repo):
        """The manifest lives outside any set and needs its own copy step."""
        assert _run(repo, "policy-sync").returncode == 0
        assert (repo / ".maceff/framework/policies/manifest.json").is_file()

    def test_links_current_to_the_synced_set(self, repo):
        assert _run(repo, "policy-sync").returncode == 0
        current = repo / ".maceff/framework/policies/current"
        assert current.is_symlink()
        assert os.readlink(current) == "sets/base"


class TestTemplateSync:
    def test_reads_source_from_framework_templates(self, repo):
        result = _run(repo, "template-sync")
        assert result.returncode == 0, result.stderr
        assert (repo / ".maceff/framework/templates/PA_PREAMBLE.md").is_file()

    def test_fails_when_source_absent(self, repo):
        shutil.rmtree(repo / "framework" / "templates")
        result = _run(repo, "template-sync")
        assert result.returncode == 1
        assert "source templates directory not found" in result.stderr


class TestAssetsSync:
    def test_covers_every_asset_tree(self, repo):
        """The four trees that previously had no sync path at all."""
        result = _run(repo, "assets-sync")
        assert result.returncode == 0, result.stderr
        for tree in ASSET_TREES:
            assert (repo / ".maceff/framework" / tree / f"{tree}-sample.md").is_file()

    def test_can_sync_a_single_tree(self, repo):
        assert _run(repo, "assets-sync", "skills").returncode == 0
        assert (repo / ".maceff/framework/skills/skills-sample.md").is_file()
        assert not (repo / ".maceff/framework/commands").exists()

    def test_absent_source_is_an_error_not_a_silent_skip(self, repo):
        """Negative control.

        A sync reporting success while copying nothing is precisely how the
        asset trees stayed missing from containers.
        """
        shutil.rmtree(repo / "framework" / "skills")
        result = _run(repo, "assets-sync")
        assert result.returncode == 1
        assert "source asset tree not found" in result.stderr


class TestFrameworkUpgrade:
    def test_refuses_to_run_when_a_step_script_is_missing(self, repo):
        """Negative control for the defect that broke every upgrade.

        ``tools-sync`` was deleted on purpose but kept being called; the
        upgrade died partway through. A missing step must now abort before any
        step runs.
        """
        (repo / "maceff_tools" / "assets-sync").unlink()
        result = _run(repo, "framework-upgrade")
        assert result.returncode == 1
        assert "assets-sync" in result.stderr
        assert "partial upgrade" in result.stderr
        # Nothing should have been synced before the refusal.
        assert not (repo / ".maceff/framework/policies/sets").exists()

    def test_does_not_call_the_deleted_tools_sync(self):
        """Regression guard on the real script, not the fixture copy.

        The script mentions ``tools-sync`` in a comment explaining the history,
        so this asserts on invocation, not on the word appearing at all.
        """
        body = open(os.path.join(TOOLS, "framework-upgrade")).read()
        assert "${SCRIPT_DIR}/tools-sync" not in body
        step_lines = [ln for ln in body.splitlines() if ln.strip().startswith('"')]
        assert not any("tools-sync" in ln for ln in step_lines)
        assert not os.path.exists(os.path.join(TOOLS, "tools-sync"))


class TestGeneratedTreeIsIgnored:
    """The sync destination is generated output and must not be tracked.

    Its ignore patterns carried trailing inline comments. gitignore honours
    ``#`` only at the start of a line, so each pattern was the literal string
    ``".maceff/framework/         # All framework content ..."`` and matched
    nothing — a rule that read as configured while enforcing nothing.
    """

    @pytest.mark.parametrize(
        "path",
        [
            ".maceff/framework/skills/sample.md",
            ".maceff/config/example.env",
            ".maceff/sessions/abc/state.json",
            ".maceff/agent_state.json",
        ],
    )
    def test_generated_paths_are_ignored(self, path):
        # --no-index asks whether the PATTERN matches. Without it, git reports
        # any already-tracked path as not-ignored, so a broken pattern and a
        # tracked file are indistinguishable — the test would pass for the
        # wrong reason on exactly the files that matter.
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", path],
            cwd=REPO,
            capture_output=True,
        )
        assert result.returncode == 0, f"no .gitignore pattern matches {path}"


class TestNoScriptResolvesAboveTheRepo:
    """Repo-wide guard against the ``../..`` class of defect returning."""

    @pytest.mark.parametrize(
        "script", ["policy-sync", "template-sync", "assets-sync"]
    )
    def test_repo_root_is_not_the_parent_directory(self, script):
        body = open(os.path.join(TOOLS, script)).read()
        assert '"$(dirname "$0")"/../..' not in body
