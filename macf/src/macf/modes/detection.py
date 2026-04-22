"""
Mode detection, emoji dashboard formatting, and behavioral triggers.

Three-layer mode system:
- Operational modes: AUTO_MODE, USER_IDLE, QUIET_MODE, LOW_CONTEXT
- Work modes: DISCOVER, BUILD, CURATE, CONSOLIDATE
- Recommender: Markov transition model (see recommender.py)

Policy spec: framework/policies/base/operations/mode_system.md v2.1
"""
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from ..agent_events_log import read_events
from ..utils.cycles import detect_auto_mode


# ============================================================================
# Mode Definitions
# ============================================================================

# Operational modes (detected from system state)
OPERATIONAL_MODES = {
    "AUTO_MODE":   {"emoji": "🤖", "order": 1},
    "USER_IDLE":   {"emoji": "😴", "order": 2},
    "QUIET_MODE":  {"emoji": "🔕", "order": 3},
    "LOW_CONTEXT": {"emoji": "🪫", "order": 4},
}

# Work modes (agent-declared via skills)
WORK_MODES = {
    "DISCOVER":     {"emoji": "🔍", "order": 10},
    "EXPERIMENT":   {"emoji": "🧪", "order": 11},
    "BUILD":        {"emoji": "🔨", "order": 12},
    "CURATE":       {"emoji": "📋", "order": 13},
    "CONSOLIDATE":  {"emoji": "✍️", "order": 14},
}

ALL_MODES = {**OPERATIONAL_MODES, **WORK_MODES}

# Skill map: work mode → skill name suffix
DEFAULT_SKILL_MAP = {
    "DISCOVER":     "exploratory-self-motivation",
    "EXPERIMENT":   "experimental-self-motivation",
    "BUILD":        "generative-self-motivation",
    "CURATE":       "curative-self-motivation",
    "CONSOLIDATE":  "consolidative-self-motivation",
}

# Default 5x5 Markov transition matrix (example values — tuned via experimentation)
# Natural cycle: DISCOVER → EXPERIMENT → BUILD → CURATE → CONSOLIDATE → DISCOVER
# BUILD is gated behind EXPERIMENT (direct DISCOVER→BUILD is low probability)
DEFAULT_TRANSITIONS = {
    "DISCOVER":     {"DISCOVER": 0.20, "EXPERIMENT": 0.40, "BUILD": 0.10, "CURATE": 0.25, "CONSOLIDATE": 0.05},
    "EXPERIMENT":   {"DISCOVER": 0.15, "EXPERIMENT": 0.10, "BUILD": 0.40, "CURATE": 0.25, "CONSOLIDATE": 0.10},
    "BUILD":        {"DISCOVER": 0.20, "EXPERIMENT": 0.20, "BUILD": 0.10, "CURATE": 0.40, "CONSOLIDATE": 0.10},
    "CURATE":       {"DISCOVER": 0.30, "EXPERIMENT": 0.15, "BUILD": 0.10, "CURATE": 0.10, "CONSOLIDATE": 0.35},
    "CONSOLIDATE":  {"DISCOVER": 0.45, "EXPERIMENT": 0.20, "BUILD": 0.15, "CURATE": 0.15, "CONSOLIDATE": 0.05},
}

DEFAULT_INITIAL = {"DISCOVER": 0.40, "EXPERIMENT": 0.20, "BUILD": 0.10, "CURATE": 0.20, "CONSOLIDATE": 0.10}

DEFAULT_MODIFIERS = {
    "USER_IDLE":   {"DISCOVER": 1.1, "EXPERIMENT": 1.1, "BUILD": 0.8, "CURATE": 0.9, "CONSOLIDATE": 1.0},
    "LOW_CONTEXT": {"DISCOVER": 0.2, "EXPERIMENT": 0.2, "BUILD": 0.1, "CURATE": 1.8, "CONSOLIDATE": 1.8},
}

DEFAULT_EPSILON = 0.05


# ============================================================================
# Mode Detection
# ============================================================================

def detect_active_modes(session_id: str, token_info: dict) -> Set[str]:
    """
    Detect all currently active modes across both layers.

    Returns set of mode names (e.g., {"AUTO_MODE", "USER_IDLE", "DISCOVER"}).
    """
    modes = set()

    # --- Operational modes ---

    # AUTO_MODE: existing detection from cycles.py
    try:
        auto_mode, _ = detect_auto_mode(session_id)
        if auto_mode:
            modes.add("AUTO_MODE")
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: AUTO_MODE detection failed: {e}", file=sys.stderr)

    # USER_IDLE: compare current time against last user activity
    try:
        idle_timeout = int(os.environ.get("MACF_USER_IDLE_TIMEOUT_MINS", "10"))
        last_activity = _get_last_user_activity_timestamp(session_id)
        if last_activity and (time.time() - last_activity) > idle_timeout * 60:
            modes.add("USER_IDLE")
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: USER_IDLE detection failed: {e}", file=sys.stderr)

    # QUIET_MODE: explicit event OR auto with USER_IDLE
    try:
        quiet_explicit = _detect_quiet_mode_event(session_id)
        quiet_on_idle = os.environ.get("MACF_QUIET_ON_IDLE", "false").lower() == "true"
        if quiet_explicit or (quiet_on_idle and "USER_IDLE" in modes):
            modes.add("QUIET_MODE")
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: QUIET_MODE detection failed: {e}", file=sys.stderr)

    # LOW_CONTEXT: check CL level
    try:
        low_cl = int(os.environ.get("MACF_LOW_CONTEXT_CL", "5"))
        cl_level = token_info.get("cl_level", 100)
        if isinstance(cl_level, (int, float)) and cl_level <= low_cl:
            modes.add("LOW_CONTEXT")
    except (ValueError, TypeError) as e:
        print(f"⚠️ MACF: LOW_CONTEXT detection failed: {e}", file=sys.stderr)

    # --- Work mode ---
    try:
        work_mode = _get_current_work_mode()
        if work_mode and work_mode in WORK_MODES:
            modes.add(work_mode)
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: work mode detection failed: {e}", file=sys.stderr)

    return modes


# Matches `macf_tools mode set-work <MODE>` in a shell command, allowing for
# chaining, subshells, and leading path prefixes. The MODE token uses A-Z/_
# so typos don't accidentally widen the match to arbitrary identifiers.
_SET_WORK_RE = re.compile(r'\bmacf_tools\s+mode\s+set-work\s+([A-Z_]+)\b')
_UNSET_WORK_RE = re.compile(r'\bmacf_tools\s+mode\s+unset-work\b')


def anticipate_mode_change(tool_name: str, tool_input: dict, current_modes: Set[str]) -> Set[str]:
    """Reflect a pending mode change in the dashboard BEFORE the tool runs.

    PreToolUse fires before the Bash tool executes, so a just-invoked
    `mode set-work X` hasn't emitted its event yet. Without this, the
    dashboard shows the old mode for one more tool call. This is a
    heuristic over tool_input — it catches the common direct invocation
    but can miss commands built dynamically (eval-style) or output from
    subprocesses. Failing to match just leaves behavior unchanged (the
    next tool call will pick up the real event-log state).

    Invalid mode tokens are ignored so typos can't widen the set.
    """
    if tool_name != "Bash":
        return current_modes
    cmd = tool_input.get("command") or ""
    work_mode_names = set(WORK_MODES)
    m = _SET_WORK_RE.search(cmd)
    if m:
        new_mode = m.group(1)
        if new_mode in work_mode_names:
            return (current_modes - work_mode_names) | {new_mode}
    if _UNSET_WORK_RE.search(cmd):
        return current_modes - work_mode_names
    return current_modes


# ============================================================================
# Emoji Dashboard
# ============================================================================

def format_mode_indicators(modes: Set[str]) -> str:
    """
    Format active modes as emoji string for the status line.

    Operational modes first (🤖😴🔕🪫), space, then work mode (🔍🔨📋✍️).
    Returns empty string if no modes active.
    """
    if not modes:
        return ""

    op_emojis = []
    work_emoji = ""

    for name, info in sorted(ALL_MODES.items(), key=lambda x: x[1]["order"]):
        if name in modes:
            if name in OPERATIONAL_MODES:
                op_emojis.append(info["emoji"])
            elif name in WORK_MODES:
                work_emoji = info["emoji"]

    parts = []
    if op_emojis:
        parts.append("".join(op_emojis))
    if work_emoji:
        parts.append(work_emoji)

    return " " + " ".join(parts) if parts else ""


# ============================================================================
# Behavioral Triggers
# ============================================================================

def should_self_manage_closeout(modes: Set[str]) -> bool:
    """True when AUTO_MODE AND USER_IDLE both active (dual condition)."""
    return "AUTO_MODE" in modes and "USER_IDLE" in modes


def should_closeout_now(modes: Set[str]) -> bool:
    """True when closeout responsibility + LOW_CONTEXT."""
    return should_self_manage_closeout(modes) and "LOW_CONTEXT" in modes


def is_quiet(modes: Set[str]) -> bool:
    """True when QUIET_MODE active — suppress notifications."""
    return "QUIET_MODE" in modes


def get_current_work_mode(modes: Set[str]) -> Optional[str]:
    """Extract the active work mode from a mode set, or None."""
    for mode in modes:
        if mode in WORK_MODES:
            return mode
    return None


# ============================================================================
# Markov Transition Model
# ============================================================================

def load_transition_config() -> dict:
    """
    Load transition config from .maceff/mode_transitions.json.
    Falls back to hardcoded defaults if file doesn't exist.
    """
    try:
        from ..utils.paths import find_agent_home
        agent_home = find_agent_home()
        if agent_home:
            config_path = agent_home / ".maceff" / "mode_transitions.json"
            if config_path.exists():
                with open(config_path) as f:
                    return json.load(f)
    except (OSError, json.JSONDecodeError, ImportError) as e:
        print(f"⚠️ MACF: transition config load failed, using defaults: {e}", file=sys.stderr)

    return {
        "transitions": DEFAULT_TRANSITIONS,
        "initial": DEFAULT_INITIAL,
        "modifiers": DEFAULT_MODIFIERS,
        "epsilon": DEFAULT_EPSILON,
        "skill_map": DEFAULT_SKILL_MAP,
    }


def get_transition_distribution(
    current_work_mode: Optional[str],
    active_operational_modes: Set[str],
) -> Dict[str, float]:
    """
    Get the probability distribution for the next work mode.

    Uses the Markov transition matrix with operational mode modifiers.
    Returns dict of {work_mode: probability} summing to ~1.0.
    """
    config = load_transition_config()
    transitions = config.get("transitions", DEFAULT_TRANSITIONS)
    modifiers = config.get("modifiers", DEFAULT_MODIFIERS)
    initial = config.get("initial", DEFAULT_INITIAL)

    # Get base distribution from current state
    if current_work_mode and current_work_mode in transitions:
        dist = dict(transitions[current_work_mode])
    else:
        dist = dict(initial)

    # Apply operational mode modifiers
    for op_mode in active_operational_modes:
        if op_mode in modifiers:
            mod = modifiers[op_mode]
            for wm in dist:
                dist[wm] *= mod.get(wm, 1.0)

    # Renormalize
    total = sum(dist.values())
    if total > 0:
        dist = {k: v / total for k, v in dist.items()}

    return dist


def sample_next_work_mode(
    current_work_mode: Optional[str],
    active_operational_modes: Set[str],
) -> Tuple[str, Dict[str, float]]:
    """
    Monte Carlo sample the next work mode from the Markov model.

    Returns (selected_mode, full_distribution).
    """
    config = load_transition_config()
    epsilon = config.get("epsilon", DEFAULT_EPSILON)

    # Epsilon exploration: completely random with small probability
    if random.random() < epsilon:
        work_modes = list(WORK_MODES.keys())
        selected = random.choice(work_modes)
        dist = get_transition_distribution(current_work_mode, active_operational_modes)
        return selected, dist

    # Normal Markov transition
    dist = get_transition_distribution(current_work_mode, active_operational_modes)
    modes = list(dist.keys())
    probs = [dist[m] for m in modes]

    # Weighted random selection
    selected = random.choices(modes, weights=probs, k=1)[0]
    return selected, dist


def get_skill_name_for_mode(work_mode: str, agent_prefix: str = "maceff") -> str:
    """
    Get the full skill name for a work mode transition.

    Resolution: agent-specific prefix first, framework default as fallback.
    """
    config = load_transition_config()
    skill_map = config.get("skill_map", DEFAULT_SKILL_MAP)
    suffix = skill_map.get(work_mode, "reflexive-self-motivation")
    return f"{agent_prefix}-{suffix}"


def format_recommendation(
    current_work_mode: Optional[str],
    selected_mode: str,
    distribution: Dict[str, float],
    agent_prefix: str = "maceff",
) -> str:
    """
    Format a gate point recommendation for the agent's systemMessage.
    """
    skill_name = get_skill_name_for_mode(selected_mode, agent_prefix)
    current = current_work_mode or "(none)"
    emoji = WORK_MODES.get(selected_mode, {}).get("emoji", "?")

    # Sort distribution by probability descending
    sorted_dist = sorted(distribution.items(), key=lambda x: -x[1])
    dist_str = " | ".join(
        f"{WORK_MODES.get(m, {}).get('emoji', '?')} {m} {p:.0%}"
        for m, p in sorted_dist
    )

    return (
        f"🎲 Markov recommender: {current} → {selected_mode} {emoji} (p={distribution.get(selected_mode, 0):.0%})\n"
        f"   Invoke: /{skill_name}\n"
        f"   Distribution: {dist_str}\n"
        f"   Override requires justification in task notes."
    )


# ============================================================================
# Internal Helpers
# ============================================================================

def _get_last_user_activity_timestamp(session_id: str) -> Optional[float]:
    """Get epoch timestamp of last user activity from event log.

    ONLY uses user_activity_detected events from Transcript Monitor.
    dev_drv_started was removed as a source because it fires on ALL
    UserPromptSubmit invocations — including system-generated ones
    (tool results, background notifications), causing false positives
    that reset the idle timer from the agent's own activity.

    Returns None when TM is not running (no false signals > wrong signals).
    """
    for event in read_events(limit=200, reverse=True):
        event_type = event.get("event", "")
        if event_type != "user_activity_detected":
            continue
        ts = event.get("timestamp")
        if ts:
            try:
                from datetime import datetime, timezone
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    epoch = dt.timestamp()
                elif isinstance(ts, (int, float)):
                    epoch = float(ts)
                else:
                    continue
                return epoch
            except (ValueError, TypeError):
                pass
    return None


def _detect_quiet_mode_event(session_id: str) -> bool:
    """Check if QUIET_MODE was explicitly set via mode_change event."""
    for event in read_events(limit=50, reverse=True):
        if event.get("event") == "mode_change":
            data = event.get("data", {})
            mode = data.get("mode", "")
            if mode == "QUIET_MODE":
                return data.get("enabled", True)
            # If we hit a non-QUIET mode_change, QUIET wasn't explicitly set
            if mode in ("AUTO_MODE", "MANUAL_MODE"):
                return False
    return False


def _get_current_work_mode() -> Optional[str]:
    """Get the current work mode from the most recent work_mode_change event."""
    for event in read_events(limit=50, reverse=True):
        if event.get("event") == "work_mode_change":
            return event.get("data", {}).get("mode")
    return None
