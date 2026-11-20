"""MIS-0009 R09, R28: observation reads through protocol domains, and a marked page refuses capture."""
import pytest

from macf.browser import cdp, guard


class FakeSession:
    def __init__(self):
        self.calls = []

    def send(self, method, params=None):
        self.calls.append(method)
        if method == "Accessibility.getFullAXTree":
            return {"nodes": [
                {"role": {"value": "RootWebArea"}, "name": {"value": "Inbox"}, "ignored": False},
                {"role": {"value": "heading"}, "name": {"value": "Inbox"}, "ignored": False},
                {"role": {"value": "option"}, "name": {"value": "A sender  A subject  9:01 AM"}, "ignored": False},
                {"role": {"value": "generic"}, "name": {"value": ""}, "ignored": False},
                {"role": {"value": "button"}, "name": {"value": "hidden"}, "ignored": True},
            ]}
        return {}


class FakePage:
    url = "https://mail.example.com/inbox"

    def __init__(self):
        self.evaluated = []

    def title(self):
        raise AssertionError("observation asked the page for its title (that runs script)")

    def evaluate(self, *a, **k):
        self.evaluated.append(a)
        raise AssertionError("observation ran script in the page")


def test_observation_runs_no_page_script():
    page, session = FakePage(), FakeSession()
    snap = cdp.observe(page, session)
    assert page.evaluated == []
    assert session.calls == ["Accessibility.getFullAXTree"]
    assert [(n["role"], n["name"]) for n in snap["nodes"]] == [("RootWebArea", "Inbox"), ("heading", "Inbox"),
                                                              ("option", "A sender  A subject  9:01 AM")]
    assert snap["title"] == "Inbox" and len(snap["digest"]) == 12


def test_marked_page_refuses_capture(tmp_path):
    with pytest.raises(guard.Refused):
        guard.check_capture(no_capture=True)
    assert guard.check_capture(no_capture=False) is None
