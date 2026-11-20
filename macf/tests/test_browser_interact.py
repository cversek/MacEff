"""MIS-0009 6.3 and R24: visible targets only, a change report after each act, dirty forms kept, no random timing."""
import re
from pathlib import Path

import pytest

from macf.browser import guard


def test_hidden_or_disabled_target_refused():
    with pytest.raises(guard.Refused):
        guard.check_target(count=1, visible=False, enabled=True, what="Comment editor")
    with pytest.raises(guard.Refused):
        guard.check_target(count=1, visible=True, enabled=False, what="Next")
    with pytest.raises(guard.Refused):
        guard.check_target(count=0, visible=False, enabled=False, what="Next")
    with pytest.raises(guard.Refused) as e:
        guard.check_target(count=3, visible=True, enabled=True, what="Next")
    assert "3" in str(e.value)
    assert guard.check_target(count=1, visible=True, enabled=True, what="Next") is None


def test_change_report_after_act():
    before = {"url": "https://a.example/1", "title": "Unit 3", "digest": "9f2c"}
    after = {"url": "https://a.example/1", "title": "Unit 4", "digest": "41aa"}
    r = guard.change_report(before, after)
    assert r["changed"] is True and r["title"] == ["Unit 3", "Unit 4"] and "url" not in r
    same = guard.change_report(before, dict(before))
    assert same["changed"] is False


def test_dirty_form_navigation_refused():
    fields = [{"value": "", "default": ""}, {"value": "half a comment", "default": ""}]
    with pytest.raises(guard.Refused):
        guard.check_navigation(fields, discard=False)
    assert guard.check_navigation(fields, discard=True) is None
    assert guard.check_navigation([{"value": "x", "default": "x"}], discard=False) is None


def test_no_random_delay():
    src = "".join(p.read_text() for p in Path(guard.__file__).parent.rglob("*.py"))
    assert not re.search(r"^\s*(import random|from random)", src, re.M)
    assert "jitter" not in src.lower()
