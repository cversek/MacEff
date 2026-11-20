"""MIS-0009 6.2: a command acts only within its host scope, chooses tabs by host, and leaves the operator's tabs alone."""
import pytest

from macf.browser import guard

TABS = [
    {"index": 0, "url": "https://mail.example.com/inbox", "title": "Inbox", "ours": False},
    {"index": 1, "url": "https://chat.example.org/?q=mail.example.com", "title": "mail.example.com search", "ours": False},
    {"index": 2, "url": "https://mail.example.com/drafts", "title": "Drafts", "ours": True},
]


def test_out_of_scope_tab_refused():
    assert guard.host_in_scope("https://mail.example.com/x", ["mail.example.com"])
    assert guard.host_in_scope("https://eu.mail.example.com/x", ["*.mail.example.com"])
    assert not guard.host_in_scope("https://mail.example.com.evil.net/x", ["mail.example.com"])
    assert not guard.host_in_scope("https://chat.example.org/?q=mail.example.com", ["mail.example.com"])
    with pytest.raises(guard.Refused):
        guard.select_tab(TABS, ["mail.example.com"], index=1)


def test_tab_matched_by_host_not_title():
    found = guard.tabs_in_scope(TABS, ["mail.example.com"])
    assert [t["index"] for t in found] == [0, 2]   # the tab whose title and query mention the host is not one of them


def test_operator_tab_not_driven_unless_named():
    # with no tab named, an interaction may only use a tab the agent opened
    assert guard.select_tab(TABS, ["mail.example.com"], index=None, interact=True)["index"] == 2
    # the operator's own tab is driven only when the call names it
    assert guard.select_tab(TABS, ["mail.example.com"], index=0, interact=True)["index"] == 0
    only_operator = [TABS[0]]
    assert guard.select_tab(only_operator, ["mail.example.com"], index=None, interact=True) is None
    # observation may read the operator's tab
    assert guard.select_tab(only_operator, ["mail.example.com"], index=None, interact=False)["index"] == 0


def test_empty_scope_refused():
    with pytest.raises(guard.Refused):
        guard.tabs_in_scope(TABS, [])
