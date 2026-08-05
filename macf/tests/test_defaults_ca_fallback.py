"""Tests for the deployment-defaults fallback of consciousness_artifacts.

`agents.yaml` documents `defaults.consciousness_artifacts` as "used if not
specified per-agent". That fallback crashed provisioning outright: main() passes
the defaults through `model_dump()`, so the nested value is a plain dict, while
`create_agent_tree` reached for `.private` on it.

It went unnoticed because the only deployment in existence declared
consciousness_artifacts on every agent, so the fallback never executed. A config
path that is documented but never exercised is untested by construction.

Two defects at the same site, and the quieter one is worse:

  loud   `ca_config.private` -> AttributeError, container restart-loops
  silent `getattr(ca_config, 'immutable_structure', True)` returns the DEFAULT for
         a dict, so `immutable_structure: false` in defaults was overridden to
         true with no error at all — a wrong answer on a permissions flag

Both are covered below, each with a negative control.
"""

import importlib.util
from pathlib import Path

import pytest

from macf.models.agent_spec import AgentSpec, ConsciousnessArtifactsConfig

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"


@pytest.fixture(scope="module")
def start_module():
    spec = importlib.util.spec_from_file_location("maceff_start_defaults", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def agent_without_ca():
    """An agent that relies on the defaults — the shape that triggered the bug."""
    return AgentSpec(username="pa_defaults", personality="agents/p.md")


@pytest.fixture
def agent_with_ca():
    return AgentSpec(
        username="pa_explicit",
        personality="agents/p.md",
        consciousness_artifacts=ConsciousnessArtifactsConfig(
            private=["checkpoints"], public=["roadmaps"], immutable_structure=True
        ),
    )


class TestDefaultsFallback:
    def test_dict_defaults_are_coerced_to_a_model(self, start_module, agent_without_ca):
        """The regression itself: a dict from model_dump() must come back as a
        model, because every caller dereferences .private / .public."""
        defaults = {
            "consciousness_artifacts": {
                "private": ["checkpoints", "reflections"],
                "public": ["roadmaps"],
                "immutable_structure": True,
            }
        }
        resolved = start_module.resolve_ca_config(agent_without_ca, defaults)

        assert isinstance(resolved, ConsciousnessArtifactsConfig)
        # The attribute access that used to raise
        assert resolved.private == ["checkpoints", "reflections"]
        assert resolved.public == ["roadmaps"]

    def test_immutable_false_in_defaults_is_honoured(self, start_module, agent_without_ca):
        """The silent defect. `getattr(dict, 'immutable_structure', True)` returns
        True regardless of what the deployment asked for, so a config requesting
        writable artifact parents got read-only ones and nothing said so."""
        defaults = {
            "consciousness_artifacts": {
                "private": ["checkpoints"],
                "public": ["roadmaps"],
                "immutable_structure": False,
            }
        }
        resolved = start_module.resolve_ca_config(agent_without_ca, defaults)

        assert resolved.immutable_structure is False, (
            "immutable_structure: false in defaults was silently overridden to true"
        )

    def test_already_a_model_passes_through(self, start_module, agent_without_ca):
        """Defaults supplied as a model (not every caller uses model_dump) must not
        be double-wrapped."""
        model = ConsciousnessArtifactsConfig(private=["checkpoints"], public=["roadmaps"])
        resolved = start_module.resolve_ca_config(
            agent_without_ca, {"consciousness_artifacts": model}
        )
        assert resolved is model

    def test_per_agent_config_wins_over_defaults(self, start_module, agent_with_ca):
        defaults = {
            "consciousness_artifacts": {
                "private": ["SHOULD_NOT_WIN"],
                "public": ["SHOULD_NOT_WIN"],
            }
        }
        resolved = start_module.resolve_ca_config(agent_with_ca, defaults)
        assert resolved.private == ["checkpoints"]
        assert resolved.public == ["roadmaps"]

    def test_no_defaults_and_no_spec_is_none(self, start_module, agent_without_ca):
        assert start_module.resolve_ca_config(agent_without_ca, None) is None
        assert start_module.resolve_ca_config(agent_without_ca, {}) is None

    def test_defaults_without_the_key_is_none(self, start_module, agent_without_ca):
        """A defaults block carrying only container_env must not be mistaken for a
        CA config."""
        resolved = start_module.resolve_ca_config(
            agent_without_ca, {"container_env": {"FOO": "bar"}}
        )
        assert resolved is None

    def test_resolved_config_survives_the_immutable_read(self, start_module, agent_without_ca):
        """End-to-end on the exact expression create_agent_tree evaluates. This is
        the line that crashed provisioning, reproduced without needing root or a
        filesystem."""
        defaults = {
            "consciousness_artifacts": {
                "private": ["checkpoints"],
                "public": ["roadmaps"],
                "immutable_structure": True,
            }
        }
        ca_config = start_module.resolve_ca_config(agent_without_ca, defaults)

        immutable = ca_config.immutable_structure if ca_config else True
        assert immutable is True
        # And the dereferences that follow it in create_agent_tree
        assert list(ca_config.private) and list(ca_config.public)
