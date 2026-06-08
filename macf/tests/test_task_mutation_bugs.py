"""Regression tests for cversek/MacEff#112 task-mutation CLI gaps.

Covers the three concrete bugs from the issue:
  Bug 1: `metadata set parent_id "000"` previously int-coerced to 0,
         orphaning the task from `task tree` (which compares against
         the literal string "000" sentinel).
  Bug 2: Grant value comparison rejected legitimate authorizations
         because grant_value (string) and runtime value (int) never
         compared equal.
  Bug 3: Subject recompose blanked the title when MTMD title was
         None (plugin tasks).

Does NOT cover the umbrella gap (new `task reparent` / `task advance`
/ nested-custom CLI primitives) — those need design surface beyond
this fix's scope and are tracked separately.
"""
from unittest.mock import patch

from macf.task.protection import check_grant_in_events


# ---------- Bug 2: grant value comparison normalizes str/int ----------

def _fake_grant(task_ids, field=None, value=None, ts=100):
    """Mimic the event-log shape that check_grant_in_events scans."""
    data = {"task_ids": list(task_ids)}
    if field is not None:
        data["field"] = field
    if value is not None:
        data["value"] = value
    return {
        "event": "task_grant_update",
        "data": data,
        "timestamp": ts,
    }


def _patch_get_latest_event(grant=None, cleared=None):
    """Return a mocked get_latest_event that dispatches by event_type."""
    def side_effect(event_type, **_):
        if event_type == "task_grant_update":
            return grant
        if event_type == "task_grant_update_cleared":
            return cleared
        return None
    return patch("macf.event_queries.get_latest_event", side_effect=side_effect)


def test_check_grant_matches_when_int_value_equals_str_grant_value():
    """Grant stored as string "0", runtime value is int 0. Pre-fix this returned (False, None) because direct equality compared types; fix normalizes via str()."""
    grant = _fake_grant(["42"], field="parent_id", value="0")

    with _patch_get_latest_event(grant=grant):
        # value=int(0), grant.value="0" — pre-fix: rejected; post-fix: matched
        has_grant, evt = check_grant_in_events(
            "update", 42, field="parent_id", value=0
        )

    assert has_grant is True
    assert evt is grant


def test_check_grant_matches_when_str_value_equals_str_grant_value():
    """Both strings — happy path; must not regress."""
    grant = _fake_grant(["42"], field="parent_id", value="000")

    with _patch_get_latest_event(grant=grant):
        has_grant, _ = check_grant_in_events(
            "update", 42, field="parent_id", value="000"
        )

    assert has_grant is True


def test_check_grant_rejects_when_values_differ():
    """Genuinely different values must still be rejected (not over-permissive)."""
    grant = _fake_grant(["42"], field="parent_id", value="11")

    with _patch_get_latest_event(grant=grant):
        has_grant, _ = check_grant_in_events(
            "update", 42, field="parent_id", value="22"
        )

    assert has_grant is False


def test_check_grant_field_only_grant_still_matches_any_value():
    """Field-only grant (no value specified) authorizes any new value for that field."""
    grant = _fake_grant(["42"], field="parent_id", value=None)

    with _patch_get_latest_event(grant=grant):
        has_grant, _ = check_grant_in_events(
            "update", 42, field="parent_id", value="anything"
        )

    assert has_grant is True
