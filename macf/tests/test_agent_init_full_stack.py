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
from macf.agent_stack import ALREADY, DONE, DRIFT, PLANNED, SKIPPED, STEPS, WOULD, Result, run_stack
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
    installed = {"unit": False}

    def fake_pd_install(args):
        installs.append(args)
        installed["unit"] = True
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
    monkeypatch.setattr(agent_stack, "pd_unit_current", lambda card, h: installed["unit"])
    monkeypatch.setattr("macf.pd.cli.cmd_pd_install", fake_pd_install)
    return SimpleNamespace(home=home, claude=claude_calls, installs=installs)


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
