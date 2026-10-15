"""The daemon tells each unit which unit it is and how often it beats (persistent_layer 11.2).
These were typed again into every declaration, where a missing or mistyped value silently
stopped a unit's liveness: two of three cutover trial runs failed that way."""
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


@pytest.mark.parametrize("environment, words", [
    ({"MACF_PD_UNIT": "other"}, "sets it to the unit's name"),
    ({"MACF_PD_LIVENESS_S": "30"}, "not its liveness_interval_s 60"),
    ({"MACF_PD_LIVENESS_S": "soon"}, "not its liveness_interval_s 60"),
])
def test_a_declared_value_that_disagrees_is_refused_at_load(environment, words):
    with pytest.raises(ValueError, match=words):
        Unit(name="worker", command=["true"], account="a", restart="always",
             liveness_interval_s=60, memory_limit_mb=1, environment=environment)
