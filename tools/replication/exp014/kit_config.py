"""Where the replication reads and writes. The runner (replicate.py) sets these from its arguments,
so nothing in the kit names one agent's home, transcript or corpus.

  MACF_KIT_OUT          the folder every step writes to (it holds private text: keep it local)
  MACF_KIT_HOME         the agent's home: agent/public/tasks, agent/public/roles, agent/public/ideas
  MACF_KIT_TRANSCRIPTS  session transcripts (.jsonl), os.pathsep-separated, in time order
  MACF_KIT_SNAPSHOT     a corpus snapshot written by `macf_tools knowledge eval --save-snapshot`
  MACF_KIT_END          an epoch: events at or after it are left out (default: no cut)
  MACF_KIT_PATTERNS     optional JSON file: {"origin": "regex", ...} for prompts a machine types
                        into the pane as if it were the operator (check-ins, mail clocks, wakes)
"""
import json
import os
import re
from pathlib import Path


def _env(name, default=None):
    value = os.environ.get(name, default)
    if value is None:
        raise SystemExit(f"{name} is not set: run the kit through replicate.py")
    return value


DATA = Path(_env("MACF_KIT_OUT"))
HOME = Path(_env("MACF_KIT_HOME"))
TRANSCRIPTS = [Path(p) for p in _env("MACF_KIT_TRANSCRIPTS").split(os.pathsep) if p]
SNAPSHOT = Path(_env("MACF_KIT_SNAPSHOT"))
END = float(_env("MACF_KIT_END", "inf"))
REPO = Path(__file__).resolve().parents[3]


def machine_patterns():
    """The deployment's own machine prompts, as (origin, compiled regex). Without a patterns file
    only the record's own origin fields classify, which misses machines that type into the pane."""
    path = os.environ.get("MACF_KIT_PATTERNS")
    if not path:
        return []
    return [(origin, re.compile(rx, re.I)) for origin, rx in json.loads(Path(path).read_text()).items()]
