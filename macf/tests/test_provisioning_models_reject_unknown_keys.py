"""Provisioning config: an unknown key must be an error, not a silent drop.

pydantic v2 defaults to extra="ignore", and none of the provisioning models set
a policy -- so a key the model did not define vanished at load with no warning,
no log line and no non-zero exit. A deployment could declare a capability, have
it discarded on every container start, and read its own config file as evidence
the capability was present.

Both polarities are tested and the second matters as much as the first:
extra="forbid" turns any field the models FORGOT to define into a hard startup
failure, so the documented surface has to be complete before this is safe.
"""

import pytest
from pydantic import ValidationError

from macf.models.agent_spec import AgentsConfig, AgentSpec
from macf.models.project_spec import ProjectsConfig


def _agent(**over):
    base = dict(username="pa_demo", personality="agents/demo.md")
    base.update(over)
    return base


# --- the defect -----------------------------------------------------------

def test_unknown_key_is_rejected_and_the_error_names_it():
    """Naming the key is the requirement, not merely failing.

    A hard failure that does not say WHICH key is just a different opaque
    failure, and provisioning runs unattended -- the log is the only thing the
    operator gets.
    """
    with pytest.raises(ValidationError) as exc:
        AgentSpec(**_agent(zzz_planted="anything"))
    assert "zzz_planted" in str(exc.value)


def test_unknown_key_is_rejected_at_a_NESTED_level():
    """A top-level-only guard would be a false fix.

    The keys actually found in the wild were nested one level down, inside an
    individual agent's block -- exactly where a top-level check does not look.
    """
    cfg = {"agents": {"demo": _agent(zzz_nested="anything")}}
    with pytest.raises(ValidationError) as exc:
        AgentsConfig(**cfg)
    assert "zzz_nested" in str(exc.value)


def test_previously_dropped_key_is_now_declared():
    """conda_env was declared by a live deployment and discarded on every boot.

    Declaring the field is what makes the value visible to the framework; the
    deployment had been hardcoding the same name in a shell script instead,
    and that duplicate is a file that can go missing with nothing to notice.
    """
    spec = AgentSpec(**_agent(conda_env="research_env"))
    assert spec.conda_env == "research_env"


# --- the other polarity: forbid must not break the real surface -----------

def test_a_config_using_the_documented_surface_still_validates():
    """The safety net for extra="forbid".

    Every field the models forgot to define is now a hard startup failure, so
    this exercises the documented surface in one object. If a real deployment
    key is missing from the schema, this is where it should surface -- in a
    test, not in a container that will not come up.
    """
    cfg = {
        "agents": {
            "demo": _agent(
                display_name="Demo Agent",
                harness_session="demo1",
                conda_env="research_env",
                ssh_keys=["ssh-ed25519 AAAA demo"],
                subagents=["TestEng"],
                assigned_projects=["Proj"],
                consciousness_artifacts={"private": ["checkpoints"],
                                         "public": ["reports"],
                                         "immutable_structure": True},
                hooks={"enabled": ["session_start"]},
                claude_config={"channels": ["plugin:x@y"]},
            )
        },
        # `subagents` is REQUIRED at this level -- pre-existing, and unrelated
        # to extra="forbid". Noted rather than changed: relaxing a required
        # field is a schema decision, not part of fixing a silent drop.
        "subagents": {},
        "defaults": {"consciousness_artifacts": {"private": ["checkpoints"]},
                     "hooks": {"enabled": ["session_start"]}},
    }
    parsed = AgentsConfig(**cfg)
    assert parsed.agents["demo"].harness_session == "demo1"
    assert parsed.agents["demo"].conda_env == "research_env"


def test_projects_config_rejects_unknown_and_accepts_documented():
    """Same contract on the other provisioning file, both directions."""
    good = {"projects": {"Proj": {"context": "projects/p.md",
                                  "repos": [{"url": "git@example.com:o/r.git"}]}}}
    assert "Proj" in ProjectsConfig(**good).projects

    bad = {"projects": {"Proj": {"context": "projects/p.md", "zzz_planted": 1}}}
    with pytest.raises(ValidationError) as exc:
        ProjectsConfig(**bad)
    assert "zzz_planted" in str(exc.value)


def test_a_typo_of_a_real_field_is_caught_rather_than_ignored():
    """The everyday case, and the reason this is worth a hard failure.

    `conda_environment` is not an exotic mistake -- it is what someone writes
    when they half-remember the key. Under extra="ignore" it validated
    cleanly and did nothing, which is indistinguishable from a working config.
    """
    with pytest.raises(ValidationError) as exc:
        AgentSpec(**_agent(conda_environment="research_env"))
    assert "conda_environment" in str(exc.value)
