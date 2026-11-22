"""Idle-stop failsafe shared by the Stop hook's gates (scope, focus, burn).

A gate that blocks a Stop forces the agent to take another turn. If the agent has
nothing new to do, it re-checks the same state, the gate fires again, and the loop
spends context and the account's allowance until someone intervenes (BUG #1022).

The count of consecutive idle Stops lives in the agent's event log, one
``scope_gate_held`` event per blocked Stop. Each event carries ``remaining`` and the
fingerprints of every tool call seen during the episode. An episode starts at the
operator's prompt (or at ``reset()``); within it, a blocked Stop counts as progress
only when a tool call since the previous held Stop is NEW: a different call, or the
same call with a different result. Re-running a check whose answer has not changed
is not progress. That is what lets the failsafe end a churn loop of the kind where
every forced turn ran one cheap command to reset a counter that any tool call reset.

- No new call since the last held Stop: ``remaining`` drops by one.
- Only repeated calls with repeated results: ``remaining`` drops by one.
- Any new call or new result: ``remaining`` returns to COUNT_INIT.
- In budget mode ``conserve`` the first idle Stop fails open.

At 0 the gate fails open and the Stop passes.
"""

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable, Optional

COUNT_INIT = 5
HELD = "scope_gate_held"
RESET = "scope_gate_reset"
_EPISODE_START = ("user_prompt_submit_hook", RESET)
_MAX_SEEN = 100

# Clock times and epoch seconds change on every run without the answer changing.
_VOLATILE = re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?( ?[AP]M)?\b|\b1[6-9]\d{8}(\.\d+)?\b")


def _fingerprint(hook_input: dict) -> str:
    """One tool call as its tool, its input (minus the free-text description) and
    its result, with clock readings removed."""
    tool_input = dict(hook_input.get("tool_input") or {})
    tool_input.pop("description", None)
    response = hook_input.get("tool_response")
    if isinstance(response, dict) and ("stdout" in response or "stderr" in response):
        response = [response.get("stdout", ""), response.get("stderr", "")]
    text = json.dumps([hook_input.get("tool_name"), tool_input, response], sort_keys=True, default=str)
    return hashlib.sha256(_VOLATILE.sub("#", text).encode()).hexdigest()[:16]


@dataclass(frozen=True, kw_only=True)
class Episode:
    last_held: Optional[dict] = None          # the latest held Stop in this episode
    since: list = field(default_factory=list)  # fingerprints of calls made after it, oldest first
    seen: list = field(default_factory=list)   # fingerprints the episode had seen before it

    @property
    def previous(self) -> int:
        return int(self.last_held["data"].get("remaining", COUNT_INIT)) if self.last_held else COUNT_INIT


def _episode(events: Optional[Iterable[dict]] = None) -> Episode:
    """Walk back to the episode start: the latest held Stop, the fingerprints of tool
    calls made after it, and every fingerprint the episode had seen before it."""
    if events is None:
        from macf.agent_events_log import read_events
        events = read_events(reverse=True, only=(HELD, "tool_call_completed") + _EPISODE_START)
    last_held, since = None, []
    for e in events:
        name = e.get("event")
        if name in _EPISODE_START:
            break
        if name == HELD:
            last_held = e
            break
        if name == "tool_call_completed":
            since.append(_fingerprint(e.get("hook_input") or {}))
    since.reverse()
    seen = list((last_held or {}).get("data", {}).get("seen", []))
    return Episode(last_held=last_held, since=since, seen=seen)


def _conserving() -> bool:
    try:
        from macf.budget import current_mode
        return current_mode().get("mode") == "conserve"
    except (ImportError, OSError, ValueError) as e:
        print(f"⚠️ scope_gate_failsafe: budget mode unreadable ({e}); treating as normal", file=sys.stderr)
        return False


def current() -> int:
    """The count left in this episode, without changing it."""
    return _episode().previous


def reset() -> None:
    """Start a fresh episode at COUNT_INIT."""
    from macf.agent_events_log import append_event
    append_event(RESET, {"remaining": COUNT_INIT})


def decrement_and_check() -> tuple[int, bool]:
    """Record a blocked Stop and report whether the gate should fail open.

    Returns (remaining, fail_open). Called once per blocked Stop by whichever gate
    holds it, so the three gates share one count.
    """
    from macf.agent_events_log import append_event
    ep = _episode()
    since, seen, previous = ep.since, list(ep.seen), ep.previous
    known = set(seen)
    new = [f for f in since if f not in known]
    progressed = bool(new)
    if progressed:
        remaining = COUNT_INIT
    elif _conserving():
        remaining = 0
    else:
        remaining = max(0, previous - 1)
    for f in new:
        if f not in known:
            known.add(f)
            seen.append(f)
    append_event(HELD, {
        "remaining": remaining,
        "progressed": progressed,
        "calls": len(since),
        "repeated": len(since) - len(new),
        "seen": seen[-_MAX_SEEN:],
    })
    return remaining, remaining <= 0
