"""`scope set` re-listing a paused task leaves it paused.

A pause carries a justification: the task waits on something outside the agent. Every
`scope set` used to un-pause it silently, so an agent adding one task to a sprint's scope
had to re-pause the waiting ones by hand each time, or the stop gate nagged it about work
it could not do.
"""
from macf.task.scope import replay_scope_events


def ev(event, **data):
    return {"event": event, "data": data}


def test_scope_set_keeps_a_paused_task_paused():
    state = replay_scope_events([
        ev("scope_activated", task_ids=["499", "513"]),
        ev("scope_paused", task_ids=["499"], justification="waits on the operator"),
        ev("scope_activated", task_ids=["499", "513", "516"]),   # a later scope set adding 516
    ])
    assert state == {"499": "paused", "513": "active", "516": "active"}


def test_unpausing_is_still_the_way_back():
    state = replay_scope_events([
        ev("scope_activated", task_ids=["499"]),
        ev("scope_paused", task_ids=["499"]),
        ev("scope_activated", task_ids=["499"]),
        ev("scope_unpaused", task_ids=["499"]),
    ])
    assert state == {"499": "active"}


def test_a_cleared_scope_starts_fresh():
    state = replay_scope_events([
        ev("scope_activated", task_ids=["499"]),
        ev("scope_paused", task_ids=["499"]),
        ev("scope_cleared"),
        ev("scope_activated", task_ids=["499"]),
    ])
    assert state == {"499": "active"}


def test_a_completed_task_listed_again_is_active_again():
    """Unchanged: only a pause survives activation."""
    state = replay_scope_events([
        ev("scope_activated", task_ids=["7"]),
        ev("scope_task_completed", task_id="7"),
        ev("scope_activated", task_ids=["7"]),
    ])
    assert state == {"7": "active"}
