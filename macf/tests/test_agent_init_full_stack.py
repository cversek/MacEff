"""``macf_tools agent init`` installs the agent's whole persistent-layer stack (MIS-0002).

Every test runs against a tmp home with the service manager, the claude CLI and ``pd install``
mocked: nothing here touches the real home, systemd or Claude Code. The harness install runs for
real, into the tmp home.
"""
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from macf import agent_stack
from macf.agent_stack import ALREADY, DONE, DRIFT, PLANNED, REFUSED, SKIPPED, STEPS, WOULD, Result, run_stack
from macf.cli import _build_parser
from macf.pd.interface import Declaration

REPO = Path(__file__).resolve().parents[2]
#: The real live-session check, before the fixture stubs it out.
REAL_LIVE_CHECK = agent_stack.legacy_harness_live
CARD = "Tester@abc123"


def _args(*flags):
    return _build_parser().parse_args(["agent", "init", "-y", *flags])


@pytest.fixture
def stack(tmp_path, monkeypatch):
    """A fresh agent home that is also the login home, with every outside party mocked."""
    home = tmp_path / "home"
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(json.dumps({"agent_identity": {"calling_card": "Tester"}}))
    (home / ".maceff_primary_agent.id").write_text("abc123de-0000-0000-0000-000000000000\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("MACEFF_PROJECT_DIR", raising=False)
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    monkeypatch.setattr("macf.utils.paths.find_agent_home", lambda *a, **k: home)

    claude_calls = []

    def fake_claude(argv, **kw):
        # Emulates the CLI's own state files, so a second run finds the plugin installed.
        claude_calls.append(argv)
        plugins = home / ".claude" / "plugins"
        plugins.mkdir(parents=True, exist_ok=True)
        if argv[1:4] == ["plugin", "marketplace", "add"]:
            (plugins / "known_marketplaces.json").write_text(json.dumps({"maceff": {"source": argv[4]}}))
        if argv[1:3] == ["plugin", "install"]:
            (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {argv[3]: []}}))
        return subprocess.CompletedProcess(argv, 0, "", "")

    installs = []
    installed = {"unit": False, "stale": False}
    build = {"drift": None}
    restarts = []

    def fake_pd_install(args):
        installs.append(args)
        installed["unit"], installed["stale"] = True, False
        print("Tester@abc123: installed")
        return 0

    real_which = agent_stack.shutil.which
    monkeypatch.setattr(agent_stack.shutil, "which",
                        lambda name: "/fake/bin/claude" if name == "claude" else real_which(name))
    monkeypatch.setattr(agent_stack.subprocess, "run", fake_claude)
    monkeypatch.setattr(agent_stack, "legacy_harness_live", lambda ctx: None)
    # No live session and no daemon unless a test says so: nothing reads the real host.
    for source in ("_clients_from_proc", "_clients_from_ps", "_clients_from_sidecars"):
        monkeypatch.setattr(agent_stack, source, lambda *a: [])
    monkeypatch.setattr(agent_stack, "_systemd_harness_live", lambda ctx: None)
    monkeypatch.setattr(agent_stack, "daemon_session_pid", lambda ctx, d: None)
    monkeypatch.setattr(agent_stack, "service_manager_missing", lambda: None)
    monkeypatch.setattr(agent_stack, "pd_unit_current", lambda card, h: installed["unit"] and not installed["stale"])
    monkeypatch.setattr(agent_stack, "pd_unit_installed", lambda card, h: installed["unit"])
    monkeypatch.setattr(agent_stack, "daemon_build_drift", lambda ctx: build["drift"])
    monkeypatch.setattr(agent_stack, "daemon_restart", lambda card: restarts.append(card))
    moved = {"to": None}
    monkeypatch.setattr(agent_stack, "program_change", lambda ctx: moved["to"])
    restarts_on_install = {"yes": False}
    monkeypatch.setattr(agent_stack, "install_restarts", lambda: restarts_on_install["yes"])
    monkeypatch.setattr("macf.pd.cli.cmd_pd_install", fake_pd_install)
    return SimpleNamespace(home=home, claude=claude_calls, installs=installs, unit=installed, build=build,
                           restarts=restarts, moved=moved, restarts_on_install=restarts_on_install)


def _run(stack, *flags, preamble_status=DONE, in_container=False):
    return run_stack(_args(*flags), stack.home, in_container=in_container,
                     preamble=lambda: Result("preamble", preamble_status))


def _by_step(results):
    return {r.step: r for r in results}


def _declaration(stack):
    return json.loads((stack.home / ".maceff" / "pd" / "declaration.json").read_text())


def test_plan_lists_every_step_and_changes_nothing(stack, capsys):
    rc, results = _run(stack, "--plan")
    out = capsys.readouterr().out
    assert rc == 0
    for step, _what, _flag in STEPS:
        assert f"{step}:" in out
    assert results[0].status == PLANNED
    assert {r.status for r in results[1:]} == {WOULD}, results   # each checked, none acted
    assert {s for s, _w, _f in STEPS} >= {"preamble", "task-store", "declaration", "harness",
                                          "channel", "permissions", "daemon"}
    assert not (stack.home / ".maceff" / "pd").exists() and stack.claude == [] and stack.installs == []


def test_fresh_home_gets_a_valid_declaration_and_the_whole_stack(stack):
    rc, results = _run(stack)
    steps = _by_step(results)
    assert rc == 0, results
    assert all(steps[s].status == DONE for s in ("task-store", "declaration", "harness", "channel",
                                                 "permissions", "daemon")), results
    declaration = _declaration(stack)
    Declaration.model_validate(declaration)   # the daemon's own model
    units = {u["name"]: u for u in declaration["units"]}
    assert set(units) == {"session", "monitor", "search"}
    assert units["session"]["kind"] == "session"
    assert units["session"]["command"][-5:] == ["unit", "--home", "{agent_home}", "--project-dir", "{agent_home}"]
    assert units["monitor"]["command"][1:] == ["-m", "macf.transcript_monitor", "--follow"]
    assert units["search"]["command"][1:] == ["-m", "macf.search_service.daemon", "--unit"]
    assert declaration["agent"] == CARD
    assert {"plugin": "maceff-channel", "marketplace": "maceff"} in declaration["allowlisted_channels"]
    # No Telegram here and no mail: neither is declared.
    assert declaration["operator_channels"] == [] and declaration["notice_routes"] == {}
    # The channel comes from the packaged marketplace; the harness was given it.
    from macf.channels.marketplace import packaged_marketplace
    assert ["/fake/bin/claude", "plugin", "marketplace", "add", str(packaged_marketplace())] in stack.claude
    assert ["/fake/bin/claude", "plugin", "install", "maceff-channel@maceff"] in stack.claude
    harness = json.loads((stack.home / ".maceff" / "harness_Tester_abc123.json").read_text())
    assert "plugin:maceff-channel@maceff" in harness["channels"]
    assert len(stack.installs) == 1


def test_telegram_and_mail_are_declared_when_the_agent_uses_them(stack):
    (stack.home / ".claude").mkdir()
    (stack.home / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"telegram@claude-plugins-official": True}}))
    (stack.home / ".maceff" / "amail.json").write_text(json.dumps({"agent": "tester", "handoff": "/x"}))
    _run(stack)
    declaration = _declaration(stack)
    assert declaration["operator_channels"] == ["plugin:telegram:telegram"]
    assert declaration["notice_routes"] == {"amail": "agent"}
    assert {"plugin": "telegram", "marketplace": "claude-plugins-official"} in declaration["allowlisted_channels"]


def test_an_existing_declaration_is_never_overwritten_and_its_gaps_are_reported(stack):
    path = stack.home / ".maceff" / "pd" / "declaration.json"
    path.parent.mkdir(parents=True)
    mine = {"version": 1, "agent": CARD, "units": [
        {"name": "my-session", "kind": "session", "command": ["/bin/true"], "account": "x",
         "restart": "always", "liveness_interval_s": 60, "memory_limit_mb": 10}]}
    text = json.dumps(mine)
    path.write_text(text)
    rc, results = _run(stack)
    result = _by_step(results)["declaration"]
    assert path.read_text() == text
    assert result.status == DRIFT
    assert "no monitor unit" in result.detail and "no search unit" in result.detail
    assert "session unit" not in result.detail          # a session under another name counts
    assert "maceff-channel@maceff" in result.detail


@pytest.mark.parametrize("step,flag", [(s, f"--{f.replace('_', '-')}") for s, _w, f in STEPS])
def test_each_skip_flag_skips_its_step(stack, step, flag):
    called = []
    with patch.dict(agent_stack.RUNNERS, {step: lambda ctx: called.append(step) or Result(step, DONE)}):
        _rc, results = run_stack(_args(flag), stack.home, in_container=False,
                                 preamble=lambda: called.append("preamble") or Result("preamble", DONE))
    assert _by_step(results)[step].status == SKIPPED
    assert step not in called


def test_a_second_run_reports_everything_already_done(stack):
    rc1, _ = _run(stack)
    claude_before, installs_before = len(stack.claude), len(stack.installs)
    rc2, results = _run(stack, preamble_status=ALREADY)
    assert rc1 == rc2 == 0
    assert [r.status for r in results] == [ALREADY] * len(STEPS), results
    assert len(stack.claude) == claude_before and len(stack.installs) == installs_before


def test_a_live_legacy_session_stages_the_declaration_for_cutover(stack, monkeypatch):
    monkeypatch.setattr(agent_stack, "legacy_harness_live", lambda ctx: "cc-harness-x.service is active")
    _rc, results = _run(stack)
    steps = _by_step(results)
    pd = stack.home / ".maceff" / "pd"
    assert not (pd / "declaration.json").exists() and (pd / "declaration.json.cutover").exists()
    assert steps["daemon"].status == SKIPPED and "cutover" in steps["daemon"].detail
    assert stack.installs == []


def test_a_container_leaves_the_declaration_harness_and_daemon_to_its_start_step(stack):
    _rc, results = _run(stack, in_container=True)
    steps = _by_step(results)
    assert {steps[s].status for s in ("declaration", "harness", "daemon")} == {SKIPPED}
    assert not (stack.home / ".maceff" / "pd" / "declaration.json").exists()
    assert stack.installs == []


def _with_clients(monkeypatch, clients):
    """The real live-session check, over a mocked process table and no sidecars."""
    monkeypatch.setattr(agent_stack, "legacy_harness_live", REAL_LIVE_CHECK)
    monkeypatch.setattr(agent_stack, "_clients_from_proc", lambda *a: list(clients))
    monkeypatch.setattr(agent_stack, "_clients_from_ps", lambda: list(clients))
    monkeypatch.setattr(agent_stack, "_clients_from_sidecars", list)


def test_a_hand_started_client_in_the_project_dir_stages_the_declaration(stack, monkeypatch):
    # No systemd unit, no tmux, no supervisor: a plain claude -c in the agent's directory.
    _with_clients(monkeypatch, [(4242, str(stack.home))])
    _rc, results = _run(stack)
    steps = _by_step(results)
    pd = stack.home / ".maceff" / "pd"
    assert not (pd / "declaration.json").exists() and (pd / "declaration.json.cutover").exists()
    assert "pid 4242" in steps["declaration"].detail and "harness cutover" in steps["declaration"].detail
    assert steps["daemon"].status == SKIPPED and stack.installs == []


def test_a_client_in_another_directory_does_not_block(stack, monkeypatch, tmp_path):
    elsewhere = tmp_path / "other-project"
    elsewhere.mkdir()
    _with_clients(monkeypatch, [(4242, str(elsewhere))])
    _rc, results = _run(stack)
    assert (stack.home / ".maceff" / "pd" / "declaration.json").exists()
    assert _by_step(results)["daemon"].status == DONE


def test_the_proc_walk_finds_this_accounts_claude_and_its_cwd(tmp_path):
    proc = tmp_path / "proc"
    for pid, argv, cwd in ((101, b"/home/x/.local/bin/claude\0-c\0", tmp_path),
                           (102, b"/usr/bin/python3\0-m\0macf.cli\0", tmp_path),
                           (103, b"node\0/opt/lib/node_modules/@anthropic-ai/claude-code/cli.js\0", tmp_path)):
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "cmdline").write_bytes(argv)
        (proc / str(pid) / "cwd").symlink_to(cwd)
    assert sorted(agent_stack._clients_from_proc(proc)) == [(101, str(tmp_path)), (103, str(tmp_path))]


def test_a_running_harness_launch_agent_counts_as_live_on_macos(stack, monkeypatch):
    agents = stack.home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "cc-harness-Tester_abc123.plist").write_text("<plist/>")
    real_which = agent_stack.shutil.which
    monkeypatch.setattr(agent_stack.shutil, "which",
                        lambda name: "/bin/launchctl" if name == "launchctl" else real_which(name))
    monkeypatch.setattr(agent_stack.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 0, "gui/501/cc-harness-Tester_abc123 = {\n\tstate = running\n\tpid = 777\n}\n", ""))
    ctx = agent_stack.Context(home=stack.home, login_home=stack.home, in_container=False,
                              args=_args(), card=CARD)
    said = agent_stack._launchd_harness_live(ctx, platform="darwin")
    assert said and "cc-harness-Tester_abc123" in said and "pid 777" in said
    assert agent_stack._launchd_harness_live(ctx, platform="linux") is None


def _snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


def _write_partial_declaration(stack):
    path = stack.home / ".maceff" / "pd" / "declaration.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "agent": CARD, "units": [
        {"name": "session", "kind": "session", "command": ["/bin/true"], "account": "x",
         "restart": "always", "liveness_interval_s": 60, "memory_limit_mb": 10}]}))
    return path


def test_an_existing_declaration_with_a_live_client_never_reaches_pd_install(stack, monkeypatch):
    _write_partial_declaration(stack)
    _with_clients(monkeypatch, [(5151, str(stack.home))])
    _rc, results = _run(stack)
    steps = _by_step(results)
    assert steps["declaration"].status == DRIFT              # the declaration step had nothing to stage
    assert steps["daemon"].status == SKIPPED
    assert "pid 5151" in steps["daemon"].detail and "harness cutover" in steps["daemon"].detail
    assert stack.installs == []


def test_plan_reports_what_an_existing_declaration_lacks(stack, capsys):
    _write_partial_declaration(stack)
    _rc, results = _run(stack, "--plan")
    detail = _by_step(results)["declaration"].detail
    assert "no monitor unit" in detail and "no search unit" in detail
    assert "no monitor unit" in capsys.readouterr().out


def test_plan_says_a_live_client_would_stop_the_daemon_step(stack, monkeypatch, capsys):
    _write_partial_declaration(stack)
    _with_clients(monkeypatch, [(5151, str(stack.home))])
    _rc, results = _run(stack, "--plan")
    daemon = _by_step(results)["daemon"]
    assert daemon.status == SKIPPED and "pid 5151" in daemon.detail
    assert "pid 5151" in capsys.readouterr().out


def test_plan_writes_nothing(stack):
    _write_partial_declaration(stack)
    before = _snapshot(stack.home)
    _run(stack, "--plan")
    assert _snapshot(stack.home) == before
    assert stack.claude == [] and stack.installs == []


def test_a_client_below_the_confirmed_session_unit_is_that_unit(stack, monkeypatch):
    _write_partial_declaration(stack)
    _with_clients(monkeypatch, [(5151, str(stack.home))])
    monkeypatch.setattr(agent_stack, "daemon_session_pid", lambda ctx, d: 900)
    monkeypatch.setattr(agent_stack, "ancestors", lambda pid: {pid, 901, 900, 1})
    stack.unit["unit"] = True              # a daemon running its session unit is installed
    _rc, results = _run(stack)
    daemon = _by_step(results)["daemon"]
    assert daemon.status == ALREADY and "pid 900" in daemon.detail
    assert stack.installs == []
    _rc, results = _run(stack, "--plan")
    assert _by_step(results)["daemon"].status == ALREADY


def test_a_client_not_below_the_session_unit_still_blocks(stack, monkeypatch):
    _write_partial_declaration(stack)
    _with_clients(monkeypatch, [(5151, str(stack.home))])
    monkeypatch.setattr(agent_stack, "daemon_session_pid", lambda ctx, d: 900)
    monkeypatch.setattr(agent_stack, "ancestors", lambda pid: {pid, 77, 1})
    _rc, results = _run(stack)
    daemon = _by_step(results)["daemon"]
    assert daemon.status == SKIPPED and "pid 5151" in daemon.detail
    assert stack.installs == []


def test_plan_prints_findings_not_the_static_list(stack, capsys):
    _run(stack, "--plan")
    out = capsys.readouterr().out
    assert "1. preamble" not in out and "agent init --plan" in out


# --- the packaged marketplace ------------------------------------------------------------------

def test_the_packaged_marketplace_and_the_root_one_agree():
    from macf.channels.marketplace import packaged_marketplace
    packaged = packaged_marketplace()
    root = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    pkg = json.loads((packaged / ".claude-plugin" / "marketplace.json").read_text())

    def without_sources(m):
        return {**m, "plugins": [{k: v for k, v in p.items() if k != "source"} for p in m["plugins"]]}
    assert without_sources(root) == without_sources(pkg)
    # One copy of the plugin: both catalogs resolve each plugin to the same directory.
    for r, p in zip(root["plugins"], pkg["plugins"], strict=True):
        assert (REPO / r["source"]).resolve() == (packaged / p["source"]).resolve()
        assert ((packaged / p["source"]) / ".claude-plugin" / "plugin.json").is_file()
        assert ((packaged / p["source"]) / ".mcp.json").is_file()
    assert not (REPO / "plugins" / "maceff-channel").exists()


def test_start_py_installs_the_maceff_channel_from_the_packaged_marketplace(tmp_path):
    from macf.channels.marketplace import packaged_marketplace
    spec = importlib.util.spec_from_file_location("maceff_start_stack", REPO / "docker" / "scripts" / "start.py")
    start = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(start)
    assert start.KNOWN_MARKETPLACE_SOURCES["maceff"] == str(packaged_marketplace())
    (tmp_path / "pa_test").mkdir()
    calls = []
    with patch.object(start, "HOME_ROOT", tmp_path), \
            patch.object(start, "run_command", side_effect=lambda cmd, **kw: calls.append((cmd, kw))):
        start.ensure_channel_plugins("pa_test", ["plugin:maceff-channel@maceff"])
    payloads = [c[-1] for c, _kw in calls]
    assert payloads == [f"timeout 90 claude plugin marketplace add {packaged_marketplace()}",
                        "timeout 90 claude plugin install maceff-channel@maceff"]
    assert all(kw.get("check") is False for _c, kw in calls)


# --- the harness's Remote Control name ---------------------------------------------------------

def _params(tmp_path, **kw):
    from macf.utils.harness import HarnessParams
    return HarnessParams(agent="T_abc123", home=tmp_path, python=Path("/usr/bin/python3"),
                         macf_tools=Path("/usr/bin/macf_tools"), child_path=tmp_path / "child", **kw)


def test_remote_control_is_rendered_before_the_variadic_channels(tmp_path):
    from macf.utils.harness import render_child
    child = render_child(_params(tmp_path, channels=("plugin:tg@m",), remote_control="seat-one"))
    exec_line = [ln for ln in child.splitlines() if ln.startswith("exec claude")][0]
    assert exec_line == 'exec claude -c "$PROMPT" "$@" --remote-control seat-one --channels plugin:tg@m'


def test_no_remote_control_leaves_the_child_and_settings_unchanged(tmp_path):
    from macf.utils.harness import load_settings, render_child, save_settings
    p = _params(tmp_path, channels=("plugin:tg@m",))
    assert 'exec claude -c "$PROMPT" "$@" --channels plugin:tg@m\n' in render_child(p)
    assert "remote-control" not in render_child(p)
    save_settings(p)
    assert "remote_control" not in json.loads(p.settings_path.read_text())
    # And a recorded name comes back on a flagless reload.
    named = _params(tmp_path, remote_control="seat-one")
    save_settings(named)
    assert load_settings(_params(tmp_path)).remote_control == "seat-one"


# ---------------------------------------------------------------------------
# The preamble step, unattended: skipped and the flag named, never an EOFError refusal
# ---------------------------------------------------------------------------

class _Stdin:
    """A stdin that is, or isn't, a terminal."""
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


@pytest.fixture
def preamble(stack, tmp_path, monkeypatch):
    """The real preamble step against the stack's home, with a template of its own."""
    from macf import cli
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "PA_PREAMBLE.md").write_text("<!-- MACEFF_PA_PREAMBLE_v9.9_START -->\npreamble\n"
                                              "<!-- MACEFF_PA_PREAMBLE_v9.9_END -->\n")
    monkeypatch.setenv("MACEFF_TEMPLATES_DIR", str(templates))
    monkeypatch.chdir(stack.home)
    config = SimpleNamespace(agent_name="Tester")

    def step(*flags):
        args = _build_parser().parse_args(["agent", "init", *flags])
        return cli._agent_init_preamble(args, stack.home, config)
    return step


def _no_input(*a, **k):
    raise AssertionError("prompted with nobody to answer")


@pytest.mark.parametrize("existing", [False, True])
def test_a_preamble_with_no_terminal_is_skipped_naming_yes(preamble, stack, monkeypatch, existing):
    claude_md = stack.home / "CLAUDE.md"
    if existing:
        claude_md.write_text("# my own notes\n")
    monkeypatch.setattr("sys.stdin", _Stdin(False))
    monkeypatch.setattr("builtins.input", _no_input)
    result = preamble()
    assert result.status == SKIPPED, result
    assert "not interactive" in result.detail and "--yes" in result.detail
    assert (claude_md.read_text() == "# my own notes\n") if existing else not claude_md.exists()


def test_a_preamble_prompt_that_meets_eof_is_skipped(preamble, stack, monkeypatch):
    def eof(*a, **k):
        raise EOFError
    monkeypatch.setattr("sys.stdin", _Stdin(True))
    monkeypatch.setattr("builtins.input", eof)
    result = preamble()
    assert result.status == SKIPPED and "--yes" in result.detail
    assert not (stack.home / "CLAUDE.md").exists()


def test_yes_accepts_the_preamble_unattended(preamble, stack, monkeypatch):
    monkeypatch.setattr("sys.stdin", _Stdin(False))
    monkeypatch.setattr("builtins.input", _no_input)
    result = preamble("--yes")
    assert result.status == DONE, result
    assert "MACEFF_PA_PREAMBLE_v9.9_START" in (stack.home / "CLAUDE.md").read_text()


def test_a_person_who_says_no_still_aborts(preamble, stack, monkeypatch):
    monkeypatch.setattr("sys.stdin", _Stdin(True))
    monkeypatch.setattr("builtins.input", lambda *a, **k: "n")
    assert preamble().status == "aborted"


def test_an_unattended_run_reports_the_preamble_skipped_and_goes_on(preamble, stack, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _Stdin(False))
    monkeypatch.setattr("builtins.input", _no_input)
    args = _build_parser().parse_args(["agent", "init"])
    rc, results = run_stack(args, stack.home, in_container=False, preamble=preamble)
    assert rc == 0, results
    assert results[0].status == SKIPPED and len(results) == len(STEPS)
    assert "preamble: skipped: not interactive" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The default session unit's XDG_RUNTIME_DIR: what harness cutover checks for
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_the_default_session_unit_declares_the_runtime_dir_the_cutover_expects(stack, monkeypatch, platform):
    from macf.pd import cutover
    from macf.pd.names import declaration_path
    # Set on both: on macOS a variable a shell happens to export is still not declared, since
    # the cutover there reads the clients' fallback under /tmp.
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/4242")
    ctx = agent_stack.Context(home=stack.home, login_home=stack.home, in_container=False, args=_args())
    agent_stack.resolve_card(ctx)
    with monkeypatch.context() as m:     # sys.platform back before anything else reads it
        m.setattr(agent_stack.sys, "platform", platform)
        declaration = agent_stack.default_declaration(ctx)
    session = next(u for u in declaration["units"] if u.get("kind") == "session")
    others = [u for u in declaration["units"] if u.get("kind") != "session"]
    if platform == "linux":
        assert session["environment"]["XDG_RUNTIME_DIR"] == "/run/user/4242"
    else:
        assert "XDG_RUNTIME_DIR" not in session["environment"]
    assert not any("XDG_RUNTIME_DIR" in u["environment"] for u in others), "the session unit's alone"
    staged = declaration_path(stack.home).with_name("declaration.json.cutover")
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(json.dumps(declaration))
    runtime = "/run/user/4242" if platform == "linux" else None
    check = cutover._staged_check(staged, ctx.card, runtime,
                                  "systemd" if platform == "linux" else "launchd")
    assert check.ok, check.detail


# ---------------------------------------------------------------------------
# A daemon that isn't current: warned of, and brought current only by --update
# ---------------------------------------------------------------------------

#: The real build readout, before the fixture stubs it out.
REAL_BUILD_DRIFT = agent_stack.daemon_build_drift


def _installed_stack(stack):
    """A first init done: the daemon's unit installed, the channel installed."""
    rc, _ = _run(stack)
    assert rc == 0 and stack.unit["unit"]
    stack.installs.clear()
    stack.claude.clear()
    return stack


def test_a_stale_unit_is_warned_of_with_the_fix_and_nothing_changes(stack):
    _installed_stack(stack)
    stack.unit["stale"] = True
    for flags in ((), ("--plan",)):
        rc, results = _run(stack, *flags)
        daemon = _by_step(results)["daemon"]
        assert rc == 0 and daemon.status == DRIFT, daemon
        assert "differs from what this macf renders" in daemon.detail
        assert "agent init --update" in daemon.detail
    assert stack.installs == [] and stack.restarts == []


def test_a_daemon_on_another_build_is_warned_of_with_the_fix(stack):
    _installed_stack(stack)
    stack.build["drift"] = "the running daemon runs macf 1.0 at aaaa, this command macf 1.0 at bbbb"
    rc, results = _run(stack)
    daemon = _by_step(results)["daemon"]
    assert daemon.status == DRIFT and "at aaaa" in daemon.detail and "agent init --update" in daemon.detail
    assert stack.installs == [] and stack.restarts == []


def test_a_current_daemon_is_not_warned_of(stack):
    _installed_stack(stack)
    rc, results = _run(stack)
    daemon = _by_step(results)["daemon"]
    assert daemon.status == ALREADY and "runs this build" in daemon.detail and "--update" not in daemon.detail


def test_update_reinstalls_restarts_once_and_refreshes_the_channel_only(stack):
    from macf.pd.names import declaration_path
    _installed_stack(stack)
    stack.unit["stale"] = True
    stack.build["drift"] = "the running daemon runs macf 1.0 at aaaa, this command macf 1.0 at bbbb"
    declaration = declaration_path(stack.home)
    before = declaration.read_bytes()
    called = []
    rc, results = run_stack(_args("--update"), stack.home, in_container=False,
                            preamble=lambda: called.append("preamble") or Result("preamble", DONE))
    steps = _by_step(results)
    assert rc == 0, results
    assert steps["daemon"].status == DONE, steps["daemon"]
    assert [a.force for a in stack.installs] == [True], "the unit reinstalled as rendered now, once"
    assert stack.restarts == [CARD], "the daemon restarted once; nothing else restarted"
    assert any(c[1:3] == ["plugin", "update"] for c in stack.claude)
    assert any(c[1:4] == ["plugin", "marketplace", "update"] for c in stack.claude)
    assert declaration.read_bytes() == before, "the declaration is never rewritten"
    assert called == [], "the preamble isn't touched"
    for step in ("preamble", "task-store", "harness", "permissions"):
        assert steps[step].status == SKIPPED and "--update" in steps[step].detail, step


def test_update_on_a_current_daemon_restarts_nothing(stack):
    _installed_stack(stack)
    _rc, results = _run(stack, "--update")
    assert _by_step(results)["daemon"].status == ALREADY
    assert stack.installs == [] and stack.restarts == []


def test_update_never_writes_a_missing_declaration(stack):
    from macf.pd.names import declaration_path
    _rc, results = _run(stack, "--update")
    assert _by_step(results)["declaration"].status == SKIPPED
    assert not declaration_path(stack.home).exists()


def test_update_in_a_container_changes_nothing(stack):
    rc, results = _run(stack, "--update", in_container=True)
    assert rc == 0 and len(results) == 1 and results[0].status == SKIPPED
    assert "container's start step" in results[0].detail
    assert stack.claude == [] and stack.installs == [] and stack.restarts == []


def test_plan_with_update_changes_nothing(stack):
    _installed_stack(stack)
    stack.unit["stale"] = True
    before = _snapshot(stack.home)
    _rc, results = _run(stack, "--plan", "--update")
    assert _by_step(results)["daemon"].status == WOULD
    assert _by_step(results)["channel"].status == WOULD
    assert _snapshot(stack.home) == before
    assert stack.claude == [] and stack.installs == [] and stack.restarts == []


def test_the_build_drift_is_read_as_pd_status_reads_it(stack, monkeypatch):
    def report(source, daemon_build, cli_build="macf 1.0 at bbbb"):
        monkeypatch.setattr("macf.pd.client.status",
                            lambda home, card: SimpleNamespace(source=source, daemon_build=daemon_build,
                                                               cli_build=cli_build))
    ctx = agent_stack.Context(home=stack.home, login_home=stack.home, in_container=False, args=_args())
    agent_stack.resolve_card(ctx)
    report("daemon", "macf 1.0 at aaaa")
    assert "aaaa" in REAL_BUILD_DRIFT(ctx) and "bbbb" in REAL_BUILD_DRIFT(ctx)
    report("daemon", "macf 1.0 at bbbb")
    assert REAL_BUILD_DRIFT(ctx) is None
    report("daemon", "")
    assert "older" in REAL_BUILD_DRIFT(ctx)
    report("event log", "")
    assert REAL_BUILD_DRIFT(ctx) is None, "no daemon answering, nothing to compare"


def test_the_systemd_adapter_restarts_the_daemons_unit_and_reads_its_file(tmp_path):
    from macf.pd.adapter import SystemdAdapter
    calls = []

    def run(argv):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")
    tier = SystemdAdapter(user_home=tmp_path, run=run)
    tier.restart(CARD)
    assert calls == [["systemctl", "--user", "restart", "maceff_pd-Tester_abc123.service"]]
    assert tier.installed(CARD, tmp_path) is None
    unit = tmp_path / ".config" / "systemd" / "user" / "maceff_pd-Tester_abc123.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("old")
    assert tier.installed(CARD, tmp_path) == "old" != tier.render(CARD, tmp_path)


# ---------------------------------------------------------------------------
# --update on launchd, and a daemon pinned to its own interpreter
# ---------------------------------------------------------------------------

def test_update_refuses_to_move_a_pinned_daemon_without_repoint(stack):
    _installed_stack(stack)
    stack.unit["stale"] = True
    stack.moved["to"] = ("/venvs/pd/bin/python3", "/usr/local/bin/python3")
    for flags in (("--update",), ("--plan", "--update")):
        rc, results = _run(stack, *flags)
        daemon = _by_step(results)["daemon"]
        assert rc == 1 and daemon.status == REFUSED, daemon
        assert "/venvs/pd/bin/python3" in daemon.detail and "--repoint" in daemon.detail
    assert stack.installs == [] and stack.restarts == []


def test_a_pinned_daemon_is_a_finding_without_update(stack):
    _installed_stack(stack)
    stack.unit["stale"] = True
    stack.moved["to"] = ("/venvs/pd/bin/python3", "/usr/local/bin/python3")
    rc, results = _run(stack)
    daemon = _by_step(results)["daemon"]
    assert rc == 0 and daemon.status == DRIFT
    assert "runs /venvs/pd/bin/python3; this command would render /usr/local/bin/python3" in daemon.detail


def test_update_with_repoint_moves_a_pinned_daemon(stack):
    _installed_stack(stack)
    stack.unit["stale"] = True
    stack.moved["to"] = ("/venvs/pd/bin/python3", "/usr/local/bin/python3")
    rc, results = _run(stack, "--update", "--repoint")
    assert rc == 0 and _by_step(results)["daemon"].status == DONE
    assert [a.force for a in stack.installs] == [True] and stack.restarts == [CARD]


def test_update_does_not_restart_twice_where_the_install_restarts(stack):
    _installed_stack(stack)
    stack.unit["stale"] = True
    stack.restarts_on_install["yes"] = True
    rc, results = _run(stack, "--update")
    assert rc == 0 and _by_step(results)["daemon"].status == DONE
    assert [a.force for a in stack.installs] == [True] and stack.restarts == [], "the bootstrap restarted it"


def test_unit_program_reads_a_launch_agent_and_a_systemd_unit():
    import plistlib
    plist = plistlib.dumps({"Label": "x", "Program": "/a/python3", "ProgramArguments": ["maceff_pd", "-m", "macf.pd"]}).decode()
    assert agent_stack.unit_program(plist) == "/a/python3"
    older = plistlib.dumps({"Label": "x", "ProgramArguments": ["/b/python3", "-m", "macf.pd"]}).decode()
    assert agent_stack.unit_program(older) == "/b/python3", "a plist from before the Program key"
    unit = "[Service]\nExecStart='/c dir/python3' -m macf.pd /home\n"
    assert agent_stack.unit_program(unit) == "/c dir/python3"
    assert agent_stack.unit_program(None) is None and agent_stack.unit_program("garbage") is None


def test_the_launchd_reinstall_boots_out_before_bootstrapping(tmp_path):
    from macf.pd.adapter import LaunchdAdapter
    calls = []

    def run(argv):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")
    tier = LaunchdAdapter(user_home=tmp_path, uid=501, run=run)
    tier.install(CARD, tmp_path)
    assert [c[1] for c in calls] == ["bootstrap"], "a first install only bootstraps"
    calls.clear()
    tier.install(CARD, tmp_path, force=True)
    from macf.platform.launchd import pd_label
    assert calls[0] == ["launchctl", "bootout", f"gui/501/{pd_label(CARD)}"], calls
    assert calls[1][1:3] == ["bootstrap", "gui/501"], calls
    assert LaunchdAdapter.install_restarts is True


def test_the_launchd_reinstall_goes_on_when_nothing_was_loaded(tmp_path):
    from macf.pd.adapter import LaunchdAdapter
    from macf.platform.launchd import BOOTOUT_NOT_LOADED
    calls = []

    def run(argv):
        calls.append(argv)
        code = BOOTOUT_NOT_LOADED if argv[1] == "bootout" else 0
        return subprocess.CompletedProcess(argv, code, "", "Boot-out failed: 3: No such process")
    LaunchdAdapter(user_home=tmp_path, uid=501, run=run).install(CARD, tmp_path, force=True)
    assert [c[1] for c in calls] == ["bootout", "bootstrap"]
