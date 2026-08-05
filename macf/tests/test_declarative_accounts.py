"""Tests for declarative account provisioning: flavor, multi-key SSH, vanilla purity.

Three capabilities are covered here, all of which used to be impossible without
editing provisioning code:

1. **flavor** — an account can opt out of the MacEff footprint entirely.
2. **ssh_keys** — an account can authorize more than one key, which is what lets it
   be shared with a collaborator.
3. **vanilla purity** — the claim "a vanilla home has no MacEff artifacts" is
   checked against the filesystem rather than asserted about control flow.

Every invariant below carries a negative control: the test plants the violation and
proves the checker notices. A check never observed failing is not a check.

``docker/scripts/start.py`` is a container entrypoint, not a package module, so it
is loaded by path here (matching test_container_amail_tree.py).
"""

import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from macf.models.agent_spec import (
    AgentFlavor,
    AgentsConfig,
    AgentSpec,
    DefaultsConfig,
)

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"

# Duplicated from start.py deliberately. If the two ever disagree, either a new
# provisioning step added an artifact without a negative control, or one was
# removed — test_footprint_constant_is_fully_covered fails and says which.
EXPECTED_FOOTPRINT_PATHS = [
    "agent",
    "CLAUDE.md",
    ".maceff",
    ".claude/commands",
    ".claude/skills",
    ".claude/output-styles",
    ".claude/agents",
]


@pytest.fixture(scope="module")
def start_module():
    """Load start.py by path; it lives outside the importable package."""
    spec = importlib.util.spec_from_file_location("maceff_start_accounts", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Schema: flavor and personality
# ---------------------------------------------------------------------------


class TestFlavorSchema:
    def test_flavor_defaults_to_maceff(self):
        """Omitting flavor must keep the pre-existing behaviour, or every
        deployment written before this field silently changes meaning."""
        spec = AgentSpec(username="pa_x", personality="agents/x.md")
        assert spec.flavor == AgentFlavor.MACEFF
        assert spec.is_vanilla is False

    def test_maceff_requires_personality(self):
        spec_kwargs = {"username": "pa_y"}
        with pytest.raises(ValidationError, match="personality is required"):
            AgentSpec(**spec_kwargs)

    def test_maceff_with_personality_is_valid(self):
        """Negative control for the rule above: the same call succeeds once the
        only missing piece is supplied."""
        spec = AgentSpec(username="pa_y", personality="agents/y.md")
        assert spec.personality == "agents/y.md"

    def test_vanilla_without_personality_is_valid(self):
        spec = AgentSpec(username="owner_b_vanilla_01", flavor="vanilla")
        assert spec.is_vanilla is True
        assert spec.personality is None

    def test_vanilla_rejects_personality(self):
        """Accepting-and-ignoring would let a config claim an identity that is
        never installed — the config reporting one thing, the home showing another."""
        with pytest.raises(ValidationError, match="meaningless for"):
            AgentSpec(
                username="owner_b_vanilla_01",
                flavor="vanilla",
                personality="agents/n.md",
            )

    def test_unknown_flavor_rejected(self):
        with pytest.raises(ValidationError):
            AgentSpec(username="pa_z", personality="p.md", flavor="semi-maceff")


# ---------------------------------------------------------------------------
# Schema: ssh_keys
# ---------------------------------------------------------------------------


class TestSshKeysSchema:
    def test_omitted_ssh_keys_is_none(self):
        """None is the signal for the legacy single-file fallback, and must be
        distinguishable from an empty list."""
        spec = AgentSpec(username="pa_x", personality="p.md")
        assert spec.ssh_keys is None

    def test_empty_list_rejected(self):
        """An empty list almost certainly means templating produced nothing, which
        would lock the account out silently."""
        with pytest.raises(ValidationError, match="must not be an empty list"):
            AgentSpec(username="pa_x", personality="p.md", ssh_keys=[])

    def test_blank_entry_rejected(self):
        with pytest.raises(ValidationError, match="non-empty"):
            AgentSpec(username="pa_x", personality="p.md", ssh_keys=["key_a", "  "])

    def test_multiple_keys_preserved_in_order(self):
        spec = AgentSpec(
            username="owner_a_maceff_01",
            personality="p.md",
            ssh_keys=["key_a", "key_b"],
        )
        assert spec.ssh_keys == ["key_a", "key_b"]

    def test_admin_ssh_keys_declarable_on_defaults(self):
        """Admin access is configuration like any other account, not a hardcoded
        username in a provisioning script."""
        defaults = DefaultsConfig(admin_ssh_keys=["key_a"])
        assert defaults.admin_ssh_keys == ["key_a"]


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------


@pytest.fixture
def keys_dir(tmp_path, start_module, monkeypatch):
    d = tmp_path / "keys"
    d.mkdir()
    (d / "key_a.pub").write_text("ssh-ed25519 AAAAkeya user-a@example.invalid\n")
    (d / "key_b.pub").write_text("ssh-ed25519 AAAAkeyb user-b@example.invalid\n")
    (d / "pa_legacy.pub").write_text("ssh-ed25519 AAAAlegacy legacy@host\n")
    monkeypatch.setattr(start_module, "KEYS_DIR", d)
    return d


class TestKeyResolution:
    def test_named_keys_resolve_in_order(self, start_module, keys_dir):
        keys = start_module.resolve_ssh_keys("u", ["key_a", "key_b"])
        assert keys == [
            "ssh-ed25519 AAAAkeya user-a@example.invalid",
            "ssh-ed25519 AAAAkeyb user-b@example.invalid",
        ]

    def test_literal_key_passes_through(self, start_module, keys_dir):
        literal = "ssh-ed25519 AAAAinline inline@host"
        assert start_module.resolve_ssh_keys("u", [literal]) == [literal]

    def test_named_and_literal_can_mix(self, start_module, keys_dir):
        literal = "ecdsa-sha2-nistp256 AAAAecdsa e@host"
        keys = start_module.resolve_ssh_keys("u", ["key_a", literal])
        assert len(keys) == 2
        assert keys[1] == literal

    def test_missing_named_key_raises(self, start_module, keys_dir):
        """Skipping it would produce an account that looks provisioned and cannot
        be logged into — discovered only when authentication fails."""
        with pytest.raises(FileNotFoundError, match="could not be resolved"):
            start_module.resolve_ssh_keys("u", ["key_a", "absent_key"])

    def test_none_falls_back_to_legacy_single_file(self, start_module, keys_dir):
        """Backward compatibility: deployments that never declared ssh_keys keep
        getting /keys/{username}.pub."""
        keys = start_module.resolve_ssh_keys("pa_legacy", None)
        assert keys == ["ssh-ed25519 AAAAlegacy legacy@host"]

    def test_none_with_no_legacy_file_is_empty_not_error(self, start_module, keys_dir):
        assert start_module.resolve_ssh_keys("pa_absent", None) == []


# ---------------------------------------------------------------------------
# Vanilla purity — the enumerated footprint check
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_home(tmp_path):
    """A home containing only what a vanilla account is allowed to have."""
    home = tmp_path / "owner_b_vanilla_01"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "authorized_keys").write_text("ssh-ed25519 AAAA n@h\n")
    for sub in ("cur", "new", "tmp"):
        (home / "Maildir" / sub).mkdir(parents=True)
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text(json.dumps({"cleanupPeriodDays": 99999}))
    (home / ".bash_init.sh").write_text(
        "#!/bin/bash\nexport BASH_ENV=\"$HOME/.bash_init.sh\"\n"
        "# Vanilla account: no MacEff environment by design\n"
    )
    return home


class TestVanillaPurity:
    def test_clean_home_has_no_violations(self, start_module, clean_home):
        assert start_module.vanilla_home_violations(clean_home) == []

    def test_mailbox_and_ssh_are_allowed(self, start_module, clean_home):
        """A mailbox is a capability, not a framework artifact — email must work
        for vanilla accounts too."""
        assert (clean_home / "Maildir" / "new").is_dir()
        assert start_module.vanilla_home_violations(clean_home) == []

    @pytest.mark.parametrize("artifact", EXPECTED_FOOTPRINT_PATHS)
    def test_each_footprint_artifact_is_detected(self, start_module, clean_home, artifact):
        """Negative control, one per enumerated artifact: plant it, prove the
        checker notices. Without this, the checker could return [] unconditionally
        and every purity test above would still pass."""
        target = clean_home / artifact
        if "." in target.name and not target.name.startswith("."):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("planted")
        else:
            target.mkdir(parents=True, exist_ok=True)

        violations = start_module.vanilla_home_violations(clean_home)
        assert artifact in violations, f"{artifact} was not detected as a violation"

    def test_footprint_constant_is_fully_covered(self, start_module):
        """Every artifact the checker knows about must have a negative control.

        This is the test that keeps the suite honest as provisioning grows: adding
        a footprint path to start.py without adding it here fails immediately,
        rather than leaving an untested artifact that the checker silently misses.
        """
        assert set(start_module.MACEFF_FOOTPRINT_PATHS) == set(EXPECTED_FOOTPRINT_PATHS)

    def test_hooks_in_settings_detected(self, start_module, clean_home):
        """Hooks are installed by editing settings.json, not by adding a file, so
        a path check alone cannot see them."""
        settings = clean_home / ".claude" / "settings.json"
        settings.write_text(json.dumps({"hooks": {"SessionStart": [{"command": "x"}]}}))
        violations = start_module.vanilla_home_violations(clean_home)
        assert ".claude/settings.json:hooks" in violations

    def test_empty_hooks_key_is_not_a_violation(self, start_module, clean_home):
        """Guard against a false positive: an empty hooks dict installs nothing."""
        settings = clean_home / ".claude" / "settings.json"
        settings.write_text(json.dumps({"hooks": {}}))
        assert start_module.vanilla_home_violations(clean_home) == []

    def test_maceff_output_style_detected(self, start_module, clean_home):
        settings = clean_home / ".claude" / "settings.json"
        settings.write_text(json.dumps({"outputStyle": "maceff-compliance"}))
        violations = start_module.vanilla_home_violations(clean_home)
        assert any("outputStyle" in v for v in violations)

    def test_neutral_output_style_allowed(self, start_module, clean_home):
        """A vanilla account may still be configured deliberately — only MacEff
        styles are the problem, because their backing files are never installed."""
        settings = clean_home / ".claude" / "settings.json"
        settings.write_text(json.dumps({"outputStyle": "default"}))
        assert start_module.vanilla_home_violations(clean_home) == []

    def test_maceff_env_var_in_bash_init_detected(self, start_module, clean_home):
        """MACEFF_* variables are 'special context' even though they are not files."""
        (clean_home / ".bash_init.sh").write_text(
            "#!/bin/bash\nexport MACEFF_AGENT_NAME=\"nick\"\n"
        )
        violations = start_module.vanilla_home_violations(clean_home)
        assert any(".bash_init.sh" in v for v in violations)

    def test_maceff_mentioned_only_in_comment_is_not_flagged(self, start_module, clean_home):
        """False-positive guard: the vanilla bash_init legitimately contains the
        word MacEff in a comment explaining what is deliberately absent."""
        (clean_home / ".bash_init.sh").write_text(
            "#!/bin/bash\n# Vanilla account: no MACEFF_ variables by design\n"
            "export BASH_ENV=\"$HOME/.bash_init.sh\"\n"
        )
        assert start_module.vanilla_home_violations(clean_home) == []


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_legacy_shaped_config_still_validates(self):
        """A config written before flavor/ssh_keys existed must validate unchanged
        and behave identically — this is the regression that would break the
        sibling production deployment."""
        legacy = {
            "agents": {
                "manny": {
                    "username": "pa_manny",
                    "display_name": "Manny MacEff",
                    "personality": "agents/manny_personality.md",
                    "subagents": ["DevOpsEng"],
                    "assigned_projects": ["NeuroVEP"],
                }
            },
            "subagents": {
                "DataScientist": {
                    "role": "Data analysis",
                    "tool_access": "Read, Bash",
                }
            },
            "defaults": {"container_env": {"MACF_CONTEXT_WINDOW": "1000000"}},
        }
        config = AgentsConfig(**legacy)
        manny = config.agents["manny"]
        assert manny.flavor == AgentFlavor.MACEFF
        assert manny.is_vanilla is False
        assert manny.ssh_keys is None
        assert config.defaults.admin_ssh_keys is None

    def test_mixed_flavor_deployment_validates(self):
        """The target shape for the new deployment: owner-prefixed accounts of
        both flavors side by side."""
        config = AgentsConfig(
            agents={
                "owner_a_maceff": {
                    "username": "owner_a_maceff_01",
                    "personality": "agents/researcher.md",
                    "ssh_keys": ["key_a"],
                },
                "owner_b_vanilla": {
                    "username": "owner_b_vanilla_01",
                    "flavor": "vanilla",
                    "ssh_keys": ["key_b", "key_a"],
                },
            },
            subagents={},
            defaults={"admin_ssh_keys": ["key_a"]},
        )
        assert config.agents["owner_a_maceff"].is_vanilla is False
        assert config.agents["owner_b_vanilla"].is_vanilla is True
        assert len(config.agents["owner_b_vanilla"].ssh_keys) == 2


# ---------------------------------------------------------------------------
# Maildir
# ---------------------------------------------------------------------------


class TestMaildir:
    def test_maildir_is_not_a_forbidden_artifact(self, start_module):
        """Mail must not live under agent/, or email becomes a MacEff-only
        capability and vanilla accounts cannot have it."""
        assert not any(
            p.startswith("Maildir") for p in start_module.MACEFF_FOOTPRINT_PATHS
        )

    def test_maildir_created_with_standard_subdirs(self, start_module, tmp_path, monkeypatch):
        """A Maildir without cur/new/tmp is not a Maildir — every MUA and MDA
        expects all three. Calls the real function, not a re-implementation."""
        monkeypatch.setattr(start_module, "HOME_ROOT", tmp_path)
        monkeypatch.setattr(start_module, "run_command", lambda *a, **k: None)

        maildir = start_module.create_maildir("someuser")

        assert maildir == tmp_path / "someuser" / "Maildir"
        for sub in ("cur", "new", "tmp"):
            assert (maildir / sub).is_dir(), f"Maildir/{sub} missing"

    def test_maildir_creation_is_idempotent(self, start_module, tmp_path, monkeypatch):
        """Container restart re-runs provisioning against a persistent home volume;
        a second call must not fail or discard existing mail."""
        monkeypatch.setattr(start_module, "HOME_ROOT", tmp_path)
        monkeypatch.setattr(start_module, "run_command", lambda *a, **k: None)

        maildir = start_module.create_maildir("someuser")
        (maildir / "new" / "msg1").write_text("existing mail")

        start_module.create_maildir("someuser")

        assert (maildir / "new" / "msg1").read_text() == "existing mail"
