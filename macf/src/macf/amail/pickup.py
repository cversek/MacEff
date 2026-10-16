"""Where an agent's mail waits for it: the broker's pickup box, ``<handoff>/<agent>``.

The broker delivers accepted mail into ``handoff_dir/<agent>/`` (``amail.inbound``), and
``amail list`` ingests from that same box, naming it from the agent's amail settings. A
watcher that guesses the box instead of reading it watches an empty directory and never
says so: the primal daemon once looked in ``<home>/amail/pickup``, a path no deployment
creates, and detected no mail on any host or seat.

So everything that watches for mail resolves the box here, by the rule ``amail list`` uses:

1. the agent's ``.maceff/amail.json``, when it names both ``handoff`` and ``agent``;
2. else ``MACF_AMAIL_HANDOFF`` (default ``/var/lib/amail/handoff``) and ``MACEFF_AGENT_NAME``
   from the environment;
3. else ``<home>/amail/pickup``, the old guess, so a watcher still has a path; ``how`` says
   so, and the caller should say it too.
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
    """``(box, how)``: the agent's pickup box and which rule named it."""
    env = os.environ if env is None else env
    cfg = _settings(agent_home)
    if cfg.get("handoff") and cfg.get("agent"):
        return Path(cfg["handoff"]) / str(cfg["agent"]), FROM_SETTINGS
    agent = env.get("MACEFF_AGENT_NAME", "")
    if agent:
        return Path(env.get("MACF_AMAIL_HANDOFF") or DEFAULT_HANDOFF) / agent, FROM_ENVIRONMENT
    return Path(agent_home) / "amail" / "pickup", GUESSED


def pickup_box(agent_home: Path, env: Optional[Mapping[str, str]] = None) -> Path:
    """The agent's pickup box (``resolve_pickup_box`` without the rule)."""
    return resolve_pickup_box(agent_home, env)[0]
