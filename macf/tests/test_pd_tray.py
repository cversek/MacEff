"""The tray's model: one icon over all agents, an entry per calling card, acts through each primal daemon.

Written against the amendment of MIS-0002-R69 and R72 the operator decided (one icon, a
menu entry per agent, the icon alerting on the union of their statuses).
"""
import json

import pytest

from macf.tray.model import act_request, entry, most_urgent, union


def _resp(*pairs):
    return {"ok": True, "units": [{"unit": u, "state": s, "since": 0.0} for u, s in pairs]}


def test_icon_per_card():
    """One entry per calling card, in card order, each with its own status."""
    st = union([entry("IraMacEff@ee9a78", _resp(("session", "running"))),
                entry("ClaudeTheBuilder@6c888f", _resp(("session", "running"), ("broker", "stopped")))])
    assert [e.card for e in st.entries] == ["ClaudeTheBuilder@6c888f", "IraMacEff@ee9a78"]
    assert [e.status for e in st.entries] == ["running", "running"]
    assert st.icon == "running" and not st.alerting


def test_two_agents_with_one_card_are_refused():
    with pytest.raises(ValueError):
        union([entry("A@1", _resp(("s", "running"))), entry("A@1", _resp(("s", "stopped")))])


def test_waiting_icon():
    """A session waiting on a person changes its entry and, through the union, the icon."""
    before = union([entry("A@1", _resp(("session", "running"))), entry("B@2", _resp(("session", "running")))])
    after = union([entry("A@1", _resp(("session", "waiting_on_a_person"))), entry("B@2", _resp(("session", "running")))])
    assert before.icon == "running" and not before.alerting
    assert after.icon == "waiting_on_a_person" and after.alerting
    assert after.caused_by == ["A@1"]
    assert after.entries[0].label == "A@1: waiting on a person"


def test_union_order_failed_outranks_unreachable_outranks_waiting():
    assert most_urgent(["running", "waiting_on_a_person", "failed"]) == "failed"
    st = union([entry("A@1", None), entry("B@2", _resp(("session", "waiting_on_a_person")))])
    assert st.icon == "unreachable" and st.caused_by == ["A@1"]
    assert most_urgent(["running", "a-state-nobody-defined"]) == "unreachable"
    assert most_urgent([]) is None


def test_a_refusing_daemon_is_unreachable_with_its_reason():
    e = entry("A@1", {"ok": False, "error": "peer is not the daemon's user"})
    assert e.status == "unreachable" and "peer" in e.error


def test_acts_through_pd():
    """Each act is a control request asked by the operator; compaction and anything else is refused."""
    req = json.loads(act_request("restart", "session"))
    assert req == {"op": "restart", "unit": "session", "asked_by": {"kind": "operator"}, "reason": "asked from the tray"}
    for bad in ("compact", "type", "kill"):
        with pytest.raises(ValueError):
            act_request(bad, "session")


def test_the_layer_does_not_import_the_tray():
    """MIS-0002-R68: no persistent-layer module names the tray package."""
    import pathlib
    import macf
    root = pathlib.Path(macf.__file__).parent
    offenders = [str(p.relative_to(root)) for p in root.rglob("*.py")
                 if "tray" not in p.parts and ("macf.tray" in p.read_text(errors="ignore") or "from ..tray" in p.read_text(errors="ignore"))]
    assert offenders == []
