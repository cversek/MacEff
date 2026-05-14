#!/usr/bin/env python3
"""
handle_subagent_start - SubagentStart hook runner.

Bridges parent session's ``tool_use_id`` to subagent's ``agent_id``.

Sequence per subagent invocation:

1. Assistant invokes Agent tool.
2. PreToolUse:Agent fires synchronously; emits ``deleg_drv_started``
   with the parent's ``tool_use_id``. ``agent_id`` is NOT yet known
   (CC creates it inside AgentTool's dispatch downstream).
3. CC's AgentTool generates the ``agent_id`` and spawns the subagent.
4. **SubagentStart fires** when the subagent's ``query()`` loop begins.
   Payload carries ``agent_id`` + ``agent_type`` but NOT ``tool_use_id``.
5. This handler emits ``deleg_drv_subagent_booted`` joining the two
   namespaces (tool_use_id from the oldest unbridged started ↔ agent_id
   from this hook input).
6. SubagentStop later looks up the bridge by agent_id to recover the
   matching tool_use_id — parallel-safe.

This handler is observational; it never blocks subagent execution.
"""
import json
import sys
import traceback
from typing import Dict, Any

from macf.utils import (
    get_current_session_id,
    bridge_deleg_drv_to_agent,
)
from macf.hooks.hook_logging import log_hook_event
from macf.observability import Warning, emit_warning


def run(stdin_json: str = "", **kwargs) -> Dict[str, Any]:
    """Process SubagentStart hook input and emit the bridge event.

    Args:
        stdin_json: Raw JSON from CC. Expected fields:
            ``session_id`` (parent's), ``transcript_path``, ``cwd``,
            ``permission_mode``, ``hook_event_name='SubagentStart'``,
            ``agent_id``, ``agent_type``.

    Returns:
        ``{"continue": True}`` — never blocks subagent execution.
    """
    try:
        hook_input = json.loads(stdin_json) if stdin_json else {}

        log_hook_event("subagent_start", hook_input)

        session_id = hook_input.get("session_id") or get_current_session_id()
        agent_id = hook_input.get("agent_id", "")
        agent_type = hook_input.get("agent_type", "unknown")

        bridged = bridge_deleg_drv_to_agent(
            session_id=session_id,
            agent_id=agent_id,
            agent_type=agent_type,
        )

        # Telegram: brief boot-confirmation tag pairing tool_use_id_short
        # with agent_id. Provides a visible boundary marker on the
        # remote-observer stream between Started (parent-side) and
        # Complete (subagent-side).
        try:
            from macf.channels.telegram import send_telegram_notification
            tag = f"[{agent_type}|{agent_id[:8]}]" if agent_id else f"[{agent_type}]"
            note = "bridged" if bridged else "no matching started (orphan)"
            send_telegram_notification(
                f"{tag}\n{note}",
                prefix="\U0001f9ea DELEG_DRV Booted",
            )
        except (ImportError, OSError, ConnectionError) as e:
            emit_warning(Warning(
                source="subagent_start",
                kind="telegram_send_failed",
                detail=f"DELEG_DRV Booted telegram notification failed (non-blocking): {e}",
            ))

        return {"continue": True}

    except Exception as e:  # noqa: BLE001 — never block subagent execution
        print(f"Hook error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return {"continue": True}


if __name__ == "__main__":
    stdin_data = sys.stdin.read()
    result = run(stdin_data)
    print(json.dumps(result))
