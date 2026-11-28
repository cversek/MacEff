"""What harness attach does once a name has resolved: here from the daemon, here from the
legacy harness, or handed off to a remote."""
import shlex

import pytest

from macf.utils.attach import NONE, TMUX, AttachPlan
from macf.utils.attach_dispatch import decide
from macf.utils.remotes import Remote, RemotesConfig
from macf.utils.roster import RosterEntry

REMOTES = RemotesConfig(control=True, remotes=[
    Remote(name="seats", host="box", port=2224, login="seat", list_login="pa_one")])


def _entry(**over):
    fields = {"card": "Lumen2MacEff_3f9a1c", "moniker": "Lumen2MacEff", "uuid": "3f9a1c", "account": "pa_two",
              "display_name": "Lumen2", "session_kind": "daemon", "state": "running", "home": "/home/pa_two",
              "endpoint": "local"}
    fields.update(over)
    return RosterEntry.model_validate(fields)


def _local(plan=None, has=True, **kw):
    return dict(plan_for_home=lambda home, **k: plan(home, **k) if callable(plan) else plan,
                has_session=lambda target, env: has, environment=lambda agent: {"X": "1"}, **kw)


def test_a_remote_agent_is_handed_off_by_card_as_its_seat():
    d = decide(_entry(endpoint="seats"), REMOTES, control=None, read_only=False, **_local())
    assert d.argv[:8] == ["ssh", "-t", "-l", "pa_two", "-p", "2224", "--", "box"]
    assert shlex.split(d.argv[8])[3:] == ["--card", "Lumen2MacEff_3f9a1c", "--control"]
    gone = decide(_entry(endpoint="elsewhere"), REMOTES, control=None, read_only=False, **_local())
    assert gone.exit_code == 1 and "elsewhere" in gone.message


def test_a_daemon_session_attaches_from_its_plan_and_names_the_window():
    seen = {}

    def plan(home, **kw):
        seen.update(kw, home=str(home))
        return AttachPlan(TMUX, ["env", "TMUX_TMPDIR=/rt/M.tmux", "tmux", "-CC", "attach", "-t", "=M_3f9a1c", "-d"])

    d = decide(_entry(), REMOTES, control=None, read_only=False, **_local(plan))
    assert seen == {"home": "/home/pa_two", "read_only": False, "control": True}   # control from the declaration
    assert d.argv[-3:] == ["-t", "=M_3f9a1c", "-d"]
    assert [c[3:5] for c in d.before] == [["rename-window", "-t"], ["set-window-option", "-t"],
                                          ["set-window-option", "-t"]]
    decide(_entry(), REMOTES, control=False, read_only=False, **_local(plan))
    assert seen["control"] is False                                                # the flag wins


def test_a_declared_session_that_cannot_be_resolved_is_said_not_guessed():
    d = decide(_entry(), REMOTES, control=None, read_only=False,
               **_local(AttachPlan(NONE, reason="the primal daemon did not answer: no record")))
    assert d.exit_code == 1 and "did not answer" in d.message and not d.argv


def test_no_session_unit_falls_to_the_legacy_session_by_exact_name():
    d = decide(_entry(session_kind="legacy"), REMOTES, control=False, read_only=True, **_local(None))
    assert d.argv == ["tmux", "attach", "-t", "=Lumen2MacEff_3f9a1c", "-r"] and d.env == {"X": "1"}
    assert d.before == []                                    # an onlooker renames nothing
    missing = decide(_entry(session_kind="legacy"), REMOTES, control=False, read_only=False,
                     **_local(None, has=False))
    assert missing.exit_code == 1 and "No tmux session 'Lumen2MacEff_3f9a1c'" in missing.message


def test_a_daemon_with_no_home_known_resolves_from_the_daemon_alone():
    """A second agent on one login: no home row, so no declaration; the daemon still
    resolves it (R100), never a fallback to the name (Ira on #806)."""
    asked = []

    def by_card(card, **kw):
        asked.append(card)
        return AttachPlan(TMUX, ["env", "TMUX_TMPDIR=/rt/L.tmux", "tmux", "attach", "-t", "=L_3f9a1c", "-d"])

    d = decide(_entry(home=None, reasons={"home": "no home row"}), REMOTES, control=False,
               read_only=False, plan_for_card=by_card, **_local(None, has=False))
    assert asked == ["Lumen2MacEff_3f9a1c"] and d.argv[-2:] == ["=L_3f9a1c", "-d"]


def test_a_slug_no_row_carries_still_attaches_by_its_exact_name(monkeypatch):
    from macf.utils import attach_dispatch as ad
    d = ad.legacy_by_slug("Other_aabbcc", control=False, read_only=False,
                          has_session=lambda target, env: target == "=Other_aabbcc",
                          environment=lambda agent: {"X": "1"})
    assert d.argv == ["tmux", "attach", "-t", "=Other_aabbcc", "-d"]
    assert d.before[0][-1] == "Other_aabbcc"
    monkeypatch.setattr(ad.sys, "platform", "darwin")
    gone = ad.legacy_by_slug("Other_aabbcc", control=False, read_only=False,
                             has_session=lambda target, env: False, environment=lambda agent: None)
    assert gone.exit_code == 1 and "systemctl" not in gone.message


# ---- tmux control mode needs iTerm2 (#987) -----------------------------------------------------

def test_control_mode_is_refused_on_a_terminal_that_is_not_iterm2_and_the_alternative_is_named():
    from macf.utils.attach_dispatch import control_refusal
    argv = ["tmux", "-CC", "attach", "-t", "=Agent_abc123", "-d"]
    said = control_refusal(argv, {"TERM": "xterm-256color"})
    assert said and "--control" in said and "iTerm2" in said
    assert "--no-control" in said, "a declared control: true is overridden only by --no-control, so that is the advice"


@pytest.mark.parametrize("environ", [{"TERM_PROGRAM": "iTerm.app"}, {"LC_TERMINAL": "iTerm2"}])
def test_control_mode_is_allowed_on_iterm2_even_over_ssh(environ):
    from macf.utils.attach_dispatch import control_refusal
    assert control_refusal(["tmux", "-CC", "attach"], environ) is None


def test_a_plain_attach_and_an_ssh_hand_off_without_control_are_never_refused():
    from macf.utils.attach_dispatch import control_refusal
    assert control_refusal(["tmux", "attach", "-t", "=A", "-d"], {"TERM": "xterm"}) is None
    assert control_refusal(["ssh", "host", "macf_tools harness attach A"], {"TERM": "xterm"}) is None


def test_control_mode_inside_an_env_wrapper_or_an_ssh_command_string_is_still_seen():
    from macf.utils.attach_dispatch import control_refusal
    assert control_refusal(["env", "TMUX_TMPDIR=/x", "tmux", "-CC", "attach"], {"TERM": "xterm"})
    assert control_refusal(["ssh", "-t", "host", "tmux -CC attach -t =A"], {"TERM": "xterm"})


def test_the_override_lets_an_unrecognized_terminal_try_control_mode():
    from macf.utils.attach_dispatch import control_refusal
    assert control_refusal(["tmux", "-CC", "attach"], {"MACF_ATTACH_CONTROL": "force"}) is None


def _attach(monkeypatch, control, declared):
    """cmd_harness_attach on a terminal that is not iTerm2, with tmux's exec recorded, not run."""
    import argparse
    import types
    from macf import cli
    from macf.utils import attach_dispatch as ad
    from macf.utils import remotes, roster
    called = []
    monkeypatch.setattr(cli.os, "execvpe", lambda *a: called.append(a))
    monkeypatch.setenv("TERM", "xterm-256color")
    for var in ("TERM_PROGRAM", "LC_TERMINAL", "MACF_ATTACH_CONTROL"):
        monkeypatch.delenv(var, raising=False)

    def decide(entry, remotes_, control=None, **k):
        on = remotes_.control if control is None else control
        return ad.Decision(argv=["tmux"] + (["-CC"] if on else []) + ["attach", "-t", "=A", "-d"])
    monkeypatch.setattr(ad, "decide", decide)
    monkeypatch.setattr(roster, "local_roster", lambda probe=None: types.SimpleNamespace(entries=[_entry()], problems=[]))
    monkeypatch.setattr(remotes, "load_remotes", lambda *a, **k: RemotesConfig(control=declared, remotes=[]))
    args = argparse.Namespace(name=None, card=_entry().card, control=control, read_only=False, agent=None)
    return cli.cmd_harness_attach(args), called


def test_the_flag_refuses_before_it_execs_tmux(monkeypatch, capsys):
    """The hang was an exec of tmux -CC into a terminal that cannot speak it: nothing is printed and nothing
    returns. An explicit --control now says why and exits without the exec."""
    rc, called = _attach(monkeypatch, control=True, declared=False)
    assert rc == 2 and called == []
    assert "--no-control" in capsys.readouterr().err


def test_a_declared_default_falls_back_to_a_plain_attach_with_a_line_on_stderr(monkeypatch, capsys):
    """control: true was asked by nobody at this terminal, so refusing would leave the command unusable
    there: it attaches plainly and says so (the reviewer's suggestion on #1067)."""
    rc, called = _attach(monkeypatch, control=None, declared=True)
    assert len(called) == 1 and "-CC" not in called[0][1]
    assert "iTerm2" in capsys.readouterr().err


def test_no_control_attaches_plainly_under_a_declared_default(monkeypatch, capsys):
    rc, called = _attach(monkeypatch, control=False, declared=True)
    assert len(called) == 1 and "-CC" not in called[0][1] and capsys.readouterr().err == ""
