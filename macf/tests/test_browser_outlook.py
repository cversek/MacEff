"""MIS-0009 6.7: the mail plugin reads and drafts, never sends. Snapshots here are synthetic, with invented names."""
import inspect
import re

import pytest

from macf.browser import guard
from macf.browser.plugins import outlook

ROWS = [
    {"role": "option", "name": "Unread Pat Example Weekly notes Here are the notes 8:44 AM", "convid": "AAQkA1"},
    {"role": "option", "name": "Sam Sample Re: Workbook Attached is the file 2 attachments Wed 11/18", "convid": "AAQkA2"},
]


def test_no_send_verb():
    assert "send" not in outlook.PLUGIN.verbs
    assert outlook.PLUGIN.irreversible == ("discard",)   # discarding a draft needs the operator's words
    src = inspect.getsource(outlook)
    assert "get_by_role(\"button\", name=\"Send\"" not in src and "'Send'" not in src


def test_rows_parsed_from_snapshot():
    rows = outlook.parse_rows(ROWS)
    assert rows[0]["id"] == "AAQkA1" and rows[0]["unread"] is True
    assert rows[1]["unread"] is False and rows[1]["attachments"] is True
    assert "Workbook" in rows[1]["label"]


def test_text_set_by_value():
    """Subject and message are set by value; only recipient addresses are typed, as plain characters."""
    src = inspect.getsource(outlook.draft)
    assert 'subject.fill(args.subject)' in src and 'body.fill(text)' in src
    typed = re.findall(r"keyboard\.type\(([^,)]+)", src)
    assert typed == ["address"]                       # nothing but recipient addresses is ever typed
    assert "press_sequentially" not in src and "keyboard.press" not in src
    assert "field.fill(address)" not in src           # filling a well wiped recipients already resolved


def test_draft_left_in_drafts():
    src = inspect.getsource(outlook.draft)
    assert "Drafts" in src
    assert outlook.DRAFT_SAVED_PATTERN.search("Draft saved at 10:42 AM")


def test_missing_control_named():
    nodes = [{"role": "button", "name": "New mail"}]
    assert outlook.find_control(nodes, "button", "New mail")
    with pytest.raises(guard.Refused) as e:
        outlook.find_control(nodes, "searchbox", "Search")
    assert "Search" in str(e.value) and "searchbox" in str(e.value)


def test_attachment_name_from_label():
    assert outlook.attachment_name("WeekFiveData.xlsx Open 40 KB") == "WeekFiveData.xlsx"
    assert outlook.attachment_name("Lab Report 5.docx 1 MB") == "Lab Report 5.docx"
    assert outlook.attachment_name("notes") == "notes"
