"""The daemon tells each unit which unit it is and how often it beats (persistent_layer 11.2).
These were typed again into every declaration, where a missing or mistyped value silently
stopped a unit's liveness: two of three cutover trial runs failed that way."""
import getpass
import json

import pytest

from macf.pd.interface import Unit
from test_primal_daemon import drive, make_core, make_unit, script, wait_for  # noqa: F401 - fixtures


def _dumped(tmp_path, make_core, script, environment=None):
    dump = tmp_path / "env.json"
    unit = make_unit("worker", script, {"dump": str(dump)}, interval=0.5, environment=environment)
    core = make_core([unit])
    core.boot()
    assert wait_for(dump.exists, timeout=5.0), "the unit never wrote its environment"
    return json.loads(dump.read_text())["env"]


def test_a_unit_learns_its_name_and_interval_from_the_daemon(tmp_path, make_core, script):
    env = _dumped(tmp_path, make_core, script)
    assert env["MACF_PD_UNIT"] == "worker"
    assert float(env["MACF_PD_LIVENESS_S"]) == 0.5


def test_a_declared_value_that_agrees_is_kept(tmp_path, make_core, script):
    env = _dumped(tmp_path, make_core, script,
                  environment={"MACF_PD_UNIT": "worker", "MACF_PD_LIVENESS_S": "0.50"})
    assert env["MACF_PD_UNIT"] == "worker" and env["MACF_PD_LIVENESS_S"] == "0.50"


def test_a_declared_home_that_isnt_this_agents_is_refused_at_load(tmp_path):
    """The daemon gives each unit the agent's home; a declared one elsewhere would have the
    unit write its events where the daemon never reads (head maintainer, on #686)."""
    from macf.pd.core import DeclarationRefused, load_declaration
    from macf.pd.interface import Declaration, declaration_path
    home = tmp_path / "home"

    def declare(value):
        path = declaration_path(home)
        path.parent.mkdir(parents=True, exist_ok=True)
        unit = Unit(name="worker", command=["true"], account=getpass.getuser(), restart="always",
                    liveness_interval_s=60, memory_limit_mb=1,
                    environment={"MACEFF_AGENT_HOME_DIR": value})
        path.write_text(Declaration(version=1, agent="Tester@abc123", units=[unit]).model_dump_json())

    declare(str(tmp_path / "elsewhere"))
    with pytest.raises(DeclarationRefused, match="not this agent's home"):
        load_declaration(home, "Tester@abc123")
    for same in (str(home), "{agent_home}", str(home) + "/"):
        declare(same)
        assert load_declaration(home, "Tester@abc123").units[0].name == "worker"


@pytest.mark.parametrize("environment, words", [
    ({"MACF_PD_UNIT": "other"}, "sets it to the unit's name"),
    ({"MACF_PD_LIVENESS_S": "30"}, "not its liveness_interval_s 60"),
    ({"MACF_PD_LIVENESS_S": "soon"}, "not its liveness_interval_s 60"),
])
def test_a_declared_value_that_disagrees_is_refused_at_load(environment, words):
    with pytest.raises(ValueError, match=words):
        Unit(name="worker", command=["true"], account="a", restart="always",
             liveness_interval_s=60, memory_limit_mb=1, environment=environment)
