"""Append-only audit record for every amail decision.

Mandatory, not advisory, and the reason is a recorded failure: a communications
channel went silent for roughly forty-five minutes and afterwards neither the
agent nor the operator could reconstruct why, because the channel retained only
current state and had overwritten the evidence. A system that keeps nothing about
its own most user-visible failure cannot be debugged, and its silence is
indistinguishable from working.

REFUSALS ARE LOGGED AS CAREFULLY AS DELIVERIES. A refusal is the evidence the
control fired; a log containing only successes cannot distinguish "nothing was
refused" from "refusal logging is broken".
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


#: Rotate once the live log reaches this size, keeping one previous generation.
#: Total on-disk cost is therefore bounded at roughly twice this.
MAX_AUDIT_BYTES = 32 << 20  # 32 MiB


class AuditLog:
    """Append-only, with ONE deliberate compromise: bounded retention.

    Unbounded is the honest reading of "append-only", and it is also an
    availability attack. Every refusal is written by the broker, and any agent
    can produce refusals at will — round 6 measured ~280 bytes per refused
    submission with no cap on the total, on a volume shared by every account on
    the host. A log that fills the shared disk stops the broker, stops the other
    agents, and stops its own logging, so unbounded growth does not even
    preserve the record it was protecting.

    So: rotate at a ceiling, keep one previous generation, and — this is the
    part that keeps it honest — write a record saying rotation happened. A
    reader can then tell "nothing was refused before this point" apart from
    "the earlier evidence was rotated away", which is exactly the distinction
    this module's docstring says a log exists to preserve.
    """

    def __init__(self, path: Path, max_bytes: int = MAX_AUDIT_BYTES):
        self.path = Path(path)
        self.max_bytes = max_bytes

    def _rotate_if_needed(self) -> None:
        if self.max_bytes <= 0:
            return
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < self.max_bytes:
            return
        previous = self.path.with_name(self.path.name + ".1")
        try:
            os.replace(self.path, previous)
        except OSError:
            # Rotation failing must not stop the log from recording. Growing
            # past the ceiling is worse than the alternative of dropping records.
            return
        self._write({
            "decision": "rotated", "context": "audit",
            "detail": (f"log reached {size} bytes; previous generation moved to "
                       f"{previous.name}. Records before this line are in that "
                       f"file, and the generation before it is gone."),
        })

    def _append(self, record: Dict[str, Any]) -> None:
        self._rotate_if_needed()
        self._write(record)

    def _write(self, record: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        line = json.dumps(record, sort_keys=True) + "\n"
        # Append mode + a single write call: concurrent brokers cannot interleave
        # partial lines, so the log stays parseable under contention.
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def allowed(self, *, sender: str, recipients: List[str], message_id: str, rung: str) -> None:
        self._append({
            "decision": "allowed", "direction": "outbound", "sender": sender,
            "recipients": recipients, "message_id": message_id, "rung": rung,
        })

    def refused(self, *, sender: str, recipients: List[str], reason: str,
                message_id: Optional[str] = None) -> None:
        self._append({
            "decision": "refused", "direction": "outbound", "sender": sender,
            "recipients": recipients, "reason": reason, "message_id": message_id,
        })

    def inbound(self, *, sender: str, recipient: str, message_id: str,
                decision: str, reason: Optional[str] = None) -> None:
        rec = {
            "decision": decision, "direction": "inbound", "sender": sender,
            "recipients": [recipient], "message_id": message_id,
        }
        if reason:
            rec["reason"] = reason
        self._append(rec)

    def error(self, *, context: str, detail: str) -> None:
        """Operational failures belong here too — an outage with no trace is the
        exact gap this log exists to close."""
        self._append({"decision": "error", "context": context, "detail": detail})

    def records(self) -> Iterator[Dict[str, Any]]:
        if not self.path.exists():
            return iter(())

        def _gen() -> Iterator[Dict[str, Any]]:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
        return _gen()

    def refusals(self) -> List[Dict[str, Any]]:
        return [r for r in self.records() if r.get("decision") == "refused"]
