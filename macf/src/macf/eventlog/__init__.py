"""Generic structured-event JSONL analyzer (BUG #1069).

Provides EventLogAnalyzer + free helpers for any JSONL log that follows the
common shape:

    {"ts": ISO8601, "request_id": str, "phase": str, ...domain_data}

Two concrete domain logs use this shape today:
- Hermes delegations.jsonl (~/.hermes/logs/) — phases: started/completed/timeout/...
- Telegram restart-events.jsonl — phases: spawn/exit/...

Adapters configure the started-phase name, success field, and elapsed field;
the analyzer handles percentile + histogram + tail logic generically.
"""
from .analyzer import (
    EventLogAnalyzer,
    parse_since,
    DEFAULT_STARTED_PHASE,
    DEFAULT_SUCCESS_FIELD,
    DEFAULT_ELAPSED_FIELD,
)

__all__ = [
    "EventLogAnalyzer",
    "parse_since",
    "DEFAULT_STARTED_PHASE",
    "DEFAULT_SUCCESS_FIELD",
    "DEFAULT_ELAPSED_FIELD",
]
