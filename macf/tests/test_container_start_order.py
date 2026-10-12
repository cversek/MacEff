"""The container's access path starts before anything slow (MIS-0002-R57).

``docker/scripts/start.py`` provisions users and starts services, so its ``main`` cannot
run in a test. The order of its calls is what R57 is about, so the test reads that order
from the source: the line of the first call of each step inside ``main``.

Measured before the change, on a live deployment's last start: sshd came up 12 s after
start.py began, with the MACF install skipped; after a rebuild that install takes 2-3
minutes, and nobody could log in during it.
"""
import ast
import importlib.util
from pathlib import Path

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"
AFTER_ACCESS = ("create_workspace_structure", "install_macf_tools", "initialize_agents",
                "setup_policies", "place_secrets", "start_amail_services",
                "build_policy_index", "start_search_service_daemon")


def _start_module():
    spec = importlib.util.spec_from_file_location("maceff_start_order", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_a_failing_step_skips_only_its_dependents():
    """A step that raises after sshd is recorded; steps that need it are skipped, and
    every other step still runs, so main goes on to wait on sshd (R57, R58)."""
    start = _start_module()
    ran = []

    def boom():
        raise RuntimeError("install failed")

    failed = start.run_after_access([
        ("tools", boom, ()),
        ("agents", lambda: ran.append("agents"), ("tools",)),
        ("secrets", lambda: ran.append("secrets"), ()),
        ("amail", lambda: ran.append("amail"), ("secrets",)),
        ("index", lambda: ran.append("index"), ("tools",)),
        ("search", lambda: ran.append("search"), ("index",)),
    ])
    assert failed == ["tools", "agents", "index", "search"]
    assert ran == ["secrets", "amail"]


def test_every_step_after_sshd_runs_inside_the_guard():
    """No slow step is called in main outside run_after_access, where one exception
    would return from main and stop the container with sshd in it."""
    tree = ast.parse(START_PY.read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    guard = next(n for n in ast.walk(main) if isinstance(n, ast.Call)
                 and getattr(n.func, "id", None) == "run_after_access")
    guarded = {id(n) for n in ast.walk(guard)}
    for helper in (n for n in ast.walk(main) if isinstance(n, ast.FunctionDef) and n is not main):
        guarded |= {id(n) for n in ast.walk(helper)}
    calls = [n for n in ast.walk(main) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) in AFTER_ACCESS]
    named = {n.func.id for n in calls}
    assert named == set(AFTER_ACCESS), f"not called at all: {set(AFTER_ACCESS) - named}"
    unguarded = sorted(n.func.id for n in calls if id(n) not in guarded)
    assert not unguarded, f"called outside the guard: {unguarded}"
