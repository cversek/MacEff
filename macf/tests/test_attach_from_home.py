"""Attach resolves an agent's session from its own daemon (MIS-0002-R100), and names the
window by the agent's card."""
from types import SimpleNamespace

from macf.pd.client import DaemonUnavailable
from macf.utils.attach import NONE, TMUX, AttachPlan, plan_attach_for_home, window_commands

CARD = "Resident@1a2b3c"


def _declaration(*units):
    return SimpleNamespace(units=[SimpleNamespace(name=n, kind=k) for n, k in units])


def _answer(units):
    return SimpleNamespace(model_dump=lambda: {"ok": True, "units": units})


def _probes(pane_name="Resident_1a2b3c"):
    chains = {500: [500, 1], 700: [700, 600, 500]}       # pane 700 descends from the unit

    def panes(env=None):
        return {700: pane_name} if env and env.get("TMUX_TMPDIR", "").endswith("Resident_1a2b3c.tmux") else {}

    return {"read_info": lambda pid: None, "verify": lambda pid, start: True,
            "ancestors": lambda pid: chains.get(pid, [pid]), "tmux_panes": panes}


def test_the_session_unit_is_the_declared_one_and_its_server_is_the_cards(tmp_path):
    asked = []

    def ask(card, request):
        asked.append((card, request))
        return _answer([{"unit": "seat", "state": "running", "pid": 500, "proc_start": "x"}])

    plan = plan_attach_for_home(tmp_path, card_of=lambda home: CARD, ask=ask, base=tmp_path,
                                load=lambda home, card: _declaration(("mail", "service"), ("seat", "session")),
                                **_probes())
    assert asked == [(CARD, {"op": "status"})]
    assert plan.kind == TMUX
    assert plan.argv[:2] == ["env", f"TMUX_TMPDIR={tmp_path / 'Resident_1a2b3c.tmux'}"]
    assert plan.argv[-3:] == ["-t", "=Resident_1a2b3c", "-d"]


def test_no_declared_session_unit_leaves_the_legacy_harness(tmp_path):
    plan = plan_attach_for_home(tmp_path, card_of=lambda home: CARD,
                                load=lambda home, card: _declaration(("mail", "service")),
                                ask=lambda card, request: None)
    assert plan is None


def test_a_daemon_that_does_not_answer_resolves_nothing(tmp_path):
    def ask(card, request):
        raise DaemonUnavailable("no usable daemon record")

    def panes(env=None):
        raise AssertionError("no tmux lookup without the daemon's answer: no fallback to a name")

    plan = plan_attach_for_home(tmp_path, card_of=lambda home: CARD, ask=ask, tmux_panes=panes,
                                load=lambda home, card: _declaration(("session", "session")))
    assert plan.kind == NONE
    assert "did not answer" in plan.reason and "no usable daemon record" in plan.reason


def test_the_window_is_named_by_card_unless_the_attach_is_read_only():
    argv = ["env", "TMUX_TMPDIR=/rt/R.tmux", "tmux", "-CC", "attach", "-t", "=Resident_1a2b3c", "-d"]
    cmds = window_commands(AttachPlan(TMUX, argv), CARD)
    prefix = ["env", "TMUX_TMPDIR=/rt/R.tmux", "tmux"]
    assert cmds == [prefix + ["rename-window", "-t", "=Resident_1a2b3c:", CARD],
                    prefix + ["set-window-option", "-t", "=Resident_1a2b3c:", "automatic-rename", "off"],
                    prefix + ["set-window-option", "-t", "=Resident_1a2b3c:", "allow-rename", "off"]]
    watching = argv[:-1] + ["-r"]
    assert window_commands(AttachPlan(TMUX, watching), CARD) == []
    assert window_commands(AttachPlan(NONE, reason="none"), CARD) == []
