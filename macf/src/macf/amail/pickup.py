"""Where an agent's mail waits for it: the broker's pickup box, ``<handoff>/<agent>``.

The broker delivers accepted mail into ``handoff_dir/<agent>/`` (``amail.inbound``), and
``amail list`` ingests from that same box, naming it from the agent's amail settings. A
watcher that guesses the box instead of reading it watches an empty directory and never
says so: the primal daemon once looked in ``<home>/amail/pickup``, a path no deployment
creates, and detected no mail on any host or seat.

So everything that watches for mail resolves the box here, by the rule ``amail list`` uses:

each of ``handoff`` and ``agent`` from the agent's ``.maceff/amail.json`` when the file has
it, else from the environment (``MACF_AMAIL_HANDOFF``, default ``/var/lib/amail/handoff``;
``MACEFF_AGENT_NAME``). With no agent name anywhere it falls back to ``<home>/amail/pickup``,
the old guess, so a watcher still has a path; ``how`` says so, and the caller should too.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping, Optional, Tuple

DEFAULT_HANDOFF = "/var/lib/amail/handoff"
#: ``how`` for each rule, in order.
FROM_SETTINGS, FROM_ENVIRONMENT, GUESSED = "amail.json", "environment", "guessed"


def _settings(agent_home: Path) -> dict:
    try:
        data = json.loads((Path(agent_home) / ".maceff" / "amail.json").read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_pickup_box(agent_home: Path,
                       env: Optional[Mapping[str, str]] = None) -> Tuple[Path, str]:
    """``(box, how)``: the agent's pickup box and where each part of its name came from.

    Each key on its own, exactly as ``amail list`` resolves them (``cli._amail_config``):
    a key present in ``amail.json`` wins, else the environment, else the default handoff.
    A host's settings often name only the handoff, and the agent comes from the shell; taking
    the two as a pair would watch the container default there and call it right. It is a
    guess only when no agent name is found anywhere.
    """
    env = os.environ if env is None else env
    cfg = _settings(agent_home)
    if "handoff" in cfg:
        handoff, h_from = str(cfg["handoff"]), FROM_SETTINGS
    else:
        handoff, h_from = env.get("MACF_AMAIL_HANDOFF", DEFAULT_HANDOFF), FROM_ENVIRONMENT
    if "agent" in cfg:
        agent, a_from = str(cfg["agent"] or ""), FROM_SETTINGS
    else:
        agent, a_from = env.get("MACEFF_AGENT_NAME", ""), FROM_ENVIRONMENT
    if not agent:
        return Path(agent_home) / "amail" / "pickup", GUESSED
    how = h_from if h_from == a_from else f"handoff from {h_from}, agent from {a_from}"
    return Path(handoff) / agent, how


def pickup_box(agent_home: Path, env: Optional[Mapping[str, str]] = None) -> Path:
    """The agent's pickup box (``resolve_pickup_box`` without the rule)."""
    return resolve_pickup_box(agent_home, env)[0]
