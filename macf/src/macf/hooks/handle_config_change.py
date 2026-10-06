#!/usr/bin/env python3
"""
handle_config_change - ConfigChange hook runner.

Records every change to a settings file's permission rules as one event, so a widened or
narrowed allowlist is countable from the agent's event log (autonomous_operation 5.5).

Claude Code runs this hook about a second after a settings file changes during a session,
and tells it only which file and which kind (user, project, local, policy or skills). It
does not say what changed. So the hook keeps the rules it last saw for each file and diffs
against them. That copy is a cache for diffing, never the record: the record is the
``permission_rules_changed`` event. A file seen for the first time is recorded as a
``permission_rules_baseline`` event, since there is nothing to diff it against.

The hook never blocks a change and adds nothing to the model's context.
"""
import hashlib
import json
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from macf.agent_events_log import append_event, get_log_path
from macf.hooks.hook_logging import log_hook_event

BUCKETS = ("allow", "ask", "deny")
CHANGED_EVENT = "permission_rules_changed"
BASELINE_EVENT = "permission_rules_baseline"


def read_rules(path: Path) -> Optional[dict]:
    """The permission rules in a settings file: each bucket's rules and the default mode.

    None when the file cannot be read or parsed, so an unreadable file is never
    recorded as "every rule removed".
    """
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None  # noqa: MACEFF003 - None is the documented "unreadable" value; both callers skip on it, so an unreadable file is never diffed as every rule removed
    perms = data.get("permissions") or {}
    if not isinstance(perms, dict):
        perms = {}
    rules = {b: sorted({str(r) for r in (perms.get(b) or [])}) for b in BUCKETS}
    rules["defaultMode"] = perms.get("defaultMode")
    return rules


def diff_rules(old: dict, new: dict) -> dict:
    """Rules added and removed per bucket, and a default-mode change; empty when none."""
    out: Dict[str, Any] = {}
    for b in BUCKETS:
        before, after = set(old.get(b) or []), set(new.get(b) or [])
        if after - before:
            out.setdefault("added", {})[b] = sorted(after - before)
        if before - after:
            out.setdefault("removed", {})[b] = sorted(before - after)
    if old.get("defaultMode") != new.get("defaultMode"):
        out["default_mode"] = {"from": old.get("defaultMode"), "to": new.get("defaultMode")}
    return out


def _cache_path(settings_path: Path) -> Path:
    key = hashlib.sha256(str(settings_path.resolve()).encode()).hexdigest()[:16]
    return get_log_path().parent / "permission_rules_seen" / f"{key}.json"


def settings_files(cwd: Optional[str] = None) -> list:
    """The settings files a session reads permission rules from: user, project and local."""
    import os
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    base = Path(cwd or os.getcwd())
    return [config_dir / "settings.json", base / ".claude" / "settings.json",
            base / ".claude" / "settings.local.json"]


def seed_baselines(paths, session_id: Optional[str] = None) -> int:
    """At session start: baseline each settings file not seen before, and diff the rest.

    The first change during a session is then a diff, not a baseline, and a change made
    while no session ran is recorded with source ``between_sessions`` instead of being
    folded into the next in-session change. Returns how many events were recorded.
    """
    recorded = 0
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        rules = read_rules(path)
        if rules is None:
            continue
        cache = _cache_path(path)
        common = {"file_path": str(path), "session_id": session_id}
        try:
            old = json.loads(cache.read_text())
        except (OSError, ValueError):
            old = None
        if old is None:
            append_event(BASELINE_EVENT, {"source": "session_start", **common,
                                          "counts": {b: len(rules[b]) for b in BUCKETS},
                                          "default_mode": rules.get("defaultMode")})
            recorded += 1
        else:
            change = diff_rules(old, rules)
            if not change:
                continue
            append_event(CHANGED_EVENT, {"source": "between_sessions", **common, **change})
            recorded += 1
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rules))
    return recorded


def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    try:
        data = json.loads(stdin_json) if stdin_json else {}
        file_path = data.get("file_path")
        source = data.get("source", "unknown")
        if not file_path:
            return {"continue": True}
        path = Path(file_path)
        new = read_rules(path)
        if new is None:
            return {"continue": True}

        cache = _cache_path(path)
        old = None
        try:
            old = json.loads(cache.read_text())
        except (OSError, ValueError):
            pass

        common = {"source": source, "file_path": str(path),
                  "session_id": data.get("session_id")}
        if old is None:
            append_event(BASELINE_EVENT, {**common,
                                          "counts": {b: len(new[b]) for b in BUCKETS},
                                          "default_mode": new.get("defaultMode")})
        else:
            change = diff_rules(old, new)
            if change:
                append_event(CHANGED_EVENT, {**common, **change})

        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(new))
        return {"continue": True}

    except Exception as e:
        log_hook_event({
            "hook_name": "config_change",
            "event_type": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        return {"continue": True}


if __name__ == "__main__":
    import sys
    try:
        output = run(sys.stdin.read())
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"continue": True}))
        print(f"Hook error: {e}", file=sys.stderr)
    sys.exit(0)
