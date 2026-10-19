"""Agents' own entries: ids, and when an entry fires (design 2 and 3)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from macf.channels.maceff_channel import NoticeRecord
from macf.pd.entries import ENTRY_ID, new_entry_id, parse_when

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 19, 14, 0, tzinfo=NEW_YORK)


def test_an_entry_id_is_opaque_and_the_channel_takes_it():
    """An id carries no calling card, whose @ the channel's record refuses (#734's class), and
    every id made fits the record's pattern."""
    ids = {new_entry_id() for _ in range(200)}
    assert len(ids) == 200 and all(ENTRY_ID.match(i) for i in ids)
    for i in list(ids)[:20]:
        NoticeRecord(source="pd_run_failed", arrival_id=i, read_at=0.0, sent_at=0.0)


def test_each_shape_says_when_it_fires():
    """An instant, a time from now, tomorrow at a time, a cron and a recurrence, each read in the
    entry's zone. A relative time is fixed when the entry is made."""
    def first(text, **kw):
        return parse_when(text, NEW_YORK, NOW, **kw).next_after(NOW).astimezone(UTC).isoformat()
    assert first("2026-10-20T06:30") == "2026-10-20T10:30:00+00:00"
    assert first("in 20m") == "2026-10-19T18:20:00+00:00"
    assert first("in 3d") == "2026-10-22T18:00:00+00:00"
    assert first("tomorrow 06:30") == "2026-10-20T10:30:00+00:00"
    assert first("cron:0 9 * * 1-5") == "2026-10-20T13:00:00+00:00"
    assert first("rrule:FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1",
                 start=datetime(2026, 10, 1, 17, 0, tzinfo=NEW_YORK)) == "2026-10-30T21:00:00+00:00"
    once = parse_when("in 20m", NEW_YORK, NOW)
    assert once.next_after(once.at) is None                 # a one-shot fires once


@pytest.mark.parametrize("text, says", [
    ("next tuesday", "not a time an entry reads"),
    ("2026-10-19T09:00", "not in the future"),
    ("in 0m", "not in the future"),
    ("tomorrow 25:00", "names no time of day"),
    ("rrule:FREQ=YEARLY", "not supported"),
])
def test_a_time_it_cannot_read_is_refused_by_name(text, says):
    with pytest.raises(ValueError, match=says):
        parse_when(text, NEW_YORK, NOW)
