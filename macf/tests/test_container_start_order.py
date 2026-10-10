"""The container's access path starts before anything slow (MIS-0002-R57).

``docker/scripts/start.py`` provisions users and starts services, so its ``main`` cannot
run in a test. The order of its calls is what R57 is about, so the test reads that order
from the source: the line of the first call of each step inside ``main``.

Measured before the change, on a live deployment's last start: sshd came up 12 s after
start.py began, with the MACF install skipped; after a rebuild that install takes 2-3
minutes, and nobody could log in during it.
"""
import ast
from pathlib import Path

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"


def _first_calls():
    tree = ast.parse(START_PY.read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    first = {}
    for node in ast.walk(main):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name == "Popen" and node.args and "sshd" in ast.unparse(node.args[0]):
                name = "sshd"
            if name:
                first[name] = min(first.get(name, node.lineno), node.lineno)
    return first


def test_container_start_order():
    """sshd after the egress rules and what a login needs, before every slow step."""
    at = _first_calls()
    assert at["apply_egress_policy"] < at["sshd"], "an agent could log in unrestricted"
    for needed in ("propagate_container_env", "install_ssh_key"):
        assert at[needed] < at["sshd"], f"a login before {needed} gets a half-made account"
    for slow in ("create_workspace_structure", "install_macf_tools", "initialize_agents",
                 "start_amail_services", "build_policy_index", "start_search_service_daemon"):
        assert at["sshd"] < at[slow], f"sshd waits on {slow}"


def test_optional_units_independent():
    """MIS-0002-R58: the optional units (the policy index and the search service) come
    after every required one, so a slow or hung optional unit delays nothing else. Each
    already runs under its own timeout (120 s, 30 s)."""
    at = _first_calls()
    for optional in ("build_policy_index", "start_search_service_daemon"):
        for required in ("sshd", "initialize_agents", "place_secrets", "start_amail_services"):
            assert at[required] < at[optional], f"{required} waits on the optional {optional}"
