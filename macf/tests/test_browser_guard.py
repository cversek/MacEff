"""MIS-0009 6.4: irreversible controls need the operator's words; credentials and tokens are never touched."""
import re
from pathlib import Path

import pytest

from macf.browser import guard


@pytest.mark.parametrize("name", ["Send", "Submit", "Post comment", "Publish", "Delete", "Pay now",
                                  "Confirm", "Accept", "Request approval", "  send  "])
def test_irreversible_needs_operator_words(name):
    with pytest.raises(guard.Refused) as e:
        guard.check_activation(role="button", name=name, operator_said=None)
    assert "operator" in str(e.value)
    # the operator's words for the act let it through, and come back for the record
    assert guard.check_activation(role="button", name=name, operator_said="submit it") == "submit it"


@pytest.mark.parametrize("name", ["Next", "New mail", "Deleted Items", "Sender", "Posting policy", "Search",
                                  "Inbox", "Download", "Reply"])
def test_ordinary_controls_pass(name):
    assert guard.check_activation(role="button", name=name, operator_said=None) is None


@pytest.mark.parametrize("chord", ["Control+Enter", "Meta+Enter", "control+enter", "Alt+S", "Control+Shift+Enter"])
def test_shortcut_treated_as_control(chord):
    with pytest.raises(guard.Refused):
        guard.check_chord(chord, operator_said=None)
    assert guard.check_chord("Enter", operator_said=None) is None
    assert guard.check_chord("Tab", operator_said=None) is None


@pytest.mark.parametrize("attrs", [{"type": "password"}, {"autocomplete": "current-password"},
                                   {"autocomplete": "one-time-code"}, {"autocomplete": "cc-number"},
                                   {"name": "user_password"}, {"id": "passcode"}])
def test_credential_fields_refused(attrs):
    with pytest.raises(guard.Refused):
        guard.check_fill_target(attrs)
    assert guard.check_fill_target({"type": "text", "name": "subject"}) is None


def test_no_cookie_storage_token_access():
    """The backend's source never reaches for cookies, storage state or web storage (R20)."""
    src = "".join(p.read_text() for p in Path(guard.__file__).parent.rglob("*.py"))
    for forbidden in (r"\.cookies\(", r"storage_state", r"localStorage", r"sessionStorage", r"add_cookies",
                      r"Network\.getCookies", r"Storage\.get"):
        assert not re.search(forbidden, src), forbidden
