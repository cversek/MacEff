"""What harness attach does once a name has resolved: here from the daemon, here from the
legacy harness, or handed off to a remote."""
import shlex

from macf.utils.attach import NONE, TMUX, AttachPlan
from macf.utils.attach_dispatch import decide
from macf.utils.remotes import Remote, RemotesConfig
from macf.utils.roster import RosterEntry

REMOTES = RemotesConfig(control=True, remotes=[
    Remote(name="seats", host="box", port=2224, login="seat", list_login="pa_one")])


def _entry(**over):
    fields = {"card": "Lumen2MacEff@3f9a1c", "moniker": "Lumen2MacEff", "uuid": "3f9a1c", "account": "pa_two",
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
    assert shlex.split(d.argv[8])[3:] == ["--card", "Lumen2MacEff@3f9a1c", "--control"]
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
    assert asked == ["Lumen2MacEff@3f9a1c"] and d.argv[-2:] == ["=L_3f9a1c", "-d"]


def test_a_slug_no_row_carries_still_attaches_by_its_exact_name(monkeypatch):
    from macf.utils import attach_dispatch as ad
    d = ad.legacy_by_slug("Other_aabbcc", control=False, read_only=False,
                          has_session=lambda target, env: target == "=Other_aabbcc",
                          environment=lambda agent: {"X": "1"})
    assert d.argv == ["tmux", "attach", "-t", "=Other_aabbcc", "-d"]
    assert d.before[0][-1] == "Other@aabbcc"
    monkeypatch.setattr(ad.sys, "platform", "darwin")
    gone = ad.legacy_by_slug("Other_aabbcc", control=False, read_only=False,
                             has_session=lambda target, env: False, environment=lambda agent: None)
    assert gone.exit_code == 1 and "systemctl" not in gone.message
