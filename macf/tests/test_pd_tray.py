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


def test_two_agents_with_one_card_degrade_to_failed_without_blanking_the_tray():
    """A misinstall marks both claimants failed and alerts; every other agent still shows."""
    st = union([entry("A@1", _resp(("s", "running"))), entry("A@1", _resp(("s", "stopped"))),
                entry("B@2", _resp(("session", "waiting_on_a_person")))])
    assert st.icon == "failed" and st.alerting and st.caused_by == ["A@1", "A@1"]
    assert [e.status for e in st.entries] == ["failed", "failed", "waiting_on_a_person"]
    assert all("claim" in e.error for e in st.entries[:2])


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


def test_every_union_state_has_a_template_glyph():
    """One glyph per state the icon can show, at menu-bar size and @2x, drawn in black only.

    A macOS template image is read for its alpha alone, so any white in a glyph would
    tint like black and erase a knock-out; knock-outs are masks instead.
    """
    import pathlib
    import re
    import struct
    import macf.tray
    from macf.tray.model import URGENCY
    glyphs = pathlib.Path(macf.tray.__file__).parent / "glyphs"
    for state in URGENCY:
        if state == "declared":
            continue  # never the icon's state: a unit only declared has not been asked to run
        svg = (glyphs / f"{state}.svg").read_text()
        drawn = re.sub(r"<mask.*?</mask>", "", svg, flags=re.S)
        assert set(re.findall(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,6})"', drawn)) <= {"#000"}, state
        for name, side in ((f"{state}.png", 18), (f"{state}@2x.png", 36)):
            head = (glyphs / name).read_bytes()[:24]
            assert head[:8] == b"\x89PNG\r\n\x1a\n", name
            assert struct.unpack(">II", head[16:24]) == (side, side), name


# ---------------------------------------------------------------------------
# The controller: discovery from the outer tier, requests to each agent's own daemon
# ---------------------------------------------------------------------------

class _FakeSock:
    """Records what was sent; answers with one canned line."""

    def __init__(self, answer):
        self.sent = b""
        self._answer = (json.dumps(answer) + "\n").encode() if answer is not None else b""

    def sendall(self, data):
        self.sent += data

    def recv(self, n):
        out, self._answer = self._answer, b""
        return out

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _controller(answers, homes=None, peer_ok=True, paths_missing=False, sockets=None):
    from pathlib import Path
    from macf.tray.controller import Controller, Resolvers
    homes = homes if homes is not None else [Path(f"/agents/{c}") for c in answers]

    def paths():
        if paths_missing:
            raise ImportError("no interface")
        def card(home):
            if home.name.startswith("broken"):
                raise ValueError("names no agent")
            return home.name
        return Resolvers(card_of=card, control_socket=lambda c: Path(f"/run/{c}.control.sock"),
                         record_path=lambda c: Path(f"/run/{c}.json"))

    sockets = sockets if sockets is not None else {}

    def connect(path):
        card = path.name.split(".control")[0]
        if answers.get(card, "absent") == "absent":
            raise ConnectionRefusedError("nothing listening")
        sockets[card] = _FakeSock(answers[card])
        return sockets[card]

    return Controller(homes=lambda: homes, paths=paths,
                      peer_check=lambda s, rec: None if peer_ok else "the socket's peer is not the daemon",
                      connect=connect), sockets


def test_poll_asks_each_daemon_and_unions_their_answers():
    ctl, socks = _controller({"A@1": _resp(("session", "running")),
                              "B@2": _resp(("session", "waiting_on_a_person"))})
    st = ctl.poll()
    assert st.icon == "waiting_on_a_person" and st.caused_by == ["B@2"]
    assert json.loads(socks["A@1"].sent) == {"op": "status"}


def test_a_daemon_that_is_down_or_unverified_is_unreachable():
    ctl, _ = _controller({"A@1": "absent"})
    assert ctl.poll().entries[0].status == "unreachable"
    ctl, _ = _controller({"A@1": _resp(("session", "running"))}, peer_ok=False)
    e = ctl.poll().entries[0]
    assert e.status == "unreachable" and "peer" in e.error


def test_an_act_goes_only_to_that_agents_daemon():
    ctl, socks = _controller({"A@1": {"ok": True}, "B@2": {"ok": True}})
    ctl.discover()
    assert ctl.act("A@1", "restart", "session") == {"ok": True}
    assert json.loads(socks["A@1"].sent)["op"] == "restart" and "B@2" not in socks
    assert ctl.act("Z@9", "stop", "session")["ok"] is False


def test_discovery_problems_are_said_not_guessed():
    from pathlib import Path
    ctl, _ = _controller({}, homes=[Path("/agents/broken_home")])
    assert ctl.poll().entries == [] and "names no agent" in ctl.errors[0]
    ctl, _ = _controller({}, paths_missing=True)
    ctl.poll()
    assert ctl.errors == ["the primal daemon's interface is not installed"]


def test_installed_homes_come_from_the_launch_agents(tmp_path):
    import plistlib
    from macf.tray.controller import installed_homes
    (tmp_path / "maceff_pd.IraMacEff_ee9a78.plist").write_bytes(plistlib.dumps(
        {"Label": "maceff_pd.IraMacEff_ee9a78",
         "ProgramArguments": ["/usr/bin/python3", "-m", "macf.pd", "/Users/x/IRA"]}))
    (tmp_path / "maceff_pd.Odd_000000.plist").write_bytes(plistlib.dumps({"ProgramArguments": ["x"]}))
    (tmp_path / "com.other.plist").write_bytes(plistlib.dumps({"ProgramArguments": ["/usr/bin/python3", "-m", "macf.pd", "/no"]}))
    assert [str(h) for h in installed_homes(tmp_path)] == ["/Users/x/IRA"]


def test_two_homes_claiming_one_card_both_show_failed_and_take_no_acts():
    from pathlib import Path
    ctl, _ = _controller({"A@1": _resp(("session", "running"))},
                         homes=[Path("/agents/A@1"), Path("/other/A@1")])
    st = ctl.poll()
    assert [e.status for e in st.entries] == ["failed", "failed"] and st.alerting
    assert "two installed agents" in ctl.act("A@1", "stop", "session")["error"]
