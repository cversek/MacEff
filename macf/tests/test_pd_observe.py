"""Observation and attach (MIS-0002 R81-R102, R111).

This file starts with attach: R100 (attach_MUST_resolve_from_pd) and R101
(readout_MUST_say_nothing_attachable). Observation itself lands later.
"""
from dataclasses import dataclass

from macf.utils.attach import CLIENT, NONE, TMUX, plan_attach, readout_line


@dataclass
class _Info:
    session_id: str
    kind: str


def _resp(state="running", pid=4187, proc_start="Sat Oct 10 10:23:30 2026"):
    return {"ok": True, "units": [{"unit": "session", "state": state, "pid": pid,
                                   "proc_start": proc_start, "since": 0.0}]}


def _plan(response, info=None, verified=True, chain=(4187, 4120, 4094), panes=None, **kw):
    return plan_attach(response, "session",
                       read_info=lambda pid: info,
                       verify=lambda pid, start: verified,
                       ancestors=lambda pid: list(chain),
                       tmux_panes=lambda: dict(panes or {}), **kw)


def test_attach_resolves_from_pd():
    """The daemon's pid decides: a client-hosted session attaches through the client,
    a tmux one by exact session name, never by a name lookup."""
    hosted = _plan(_resp(), info=_Info("32149023-da95-480f-bb4a-866d6bc083a0", "bg"))
    assert hosted.kind == CLIENT
    assert hosted.argv == ["claude", "attach", "32149023-da95-480f-bb4a-866d6bc083a0"]

    in_tmux = _plan(_resp(), info=_Info("89f47c46-71a2", "interactive"), panes={4120: "IraMacEff_ee9a78"})
    assert in_tmux.kind == TMUX
    assert in_tmux.argv == ["tmux", "attach", "-t", "=IraMacEff_ee9a78", "-d"]
    ro = _plan(_resp(), info=None, panes={4094: "x"}, read_only=True, control=True)
    assert ro.argv == ["tmux", "-CC", "attach", "-t", "=x", "-r"]


def test_no_answer_is_not_a_name_lookup():
    """A daemon that does not answer resolves nothing, even with a tmux session of the agent's name."""
    plan = _plan(None, panes={4120: "IraMacEff_ee9a78"})
    assert plan.kind == NONE and "did not answer" in plan.reason
    refused = _plan({"ok": False, "error": "peer is not the daemon's user"})
    assert refused.kind == NONE and "peer" in refused.reason


def test_a_recycled_pid_is_not_attached():
    plan = _plan(_resp(), info=_Info("x", "bg"), verified=False)
    assert plan.kind == NONE and "no longer" in plan.reason


def test_nothing_attachable_said():
    """R101: a stopped unit, a missing unit and a bare terminal each say why there is nothing to attach to."""
    stopped = _plan(_resp(state="stopped", pid=None))
    assert stopped.kind == NONE and "stopped" in stopped.reason
    missing = _plan({"ok": True, "units": []})
    assert missing.kind == NONE and "no unit named 'session'" in missing.reason
    bare = _plan(_resp(), info=_Info("x", "interactive"), panes={})
    assert bare.kind == NONE and "not under tmux" in bare.reason
    assert readout_line(bare).startswith("Attach:       nothing attachable hosts this session (")
    assert "claude attach" in readout_line(_plan(_resp(), info=_Info("abc", "bg")))
