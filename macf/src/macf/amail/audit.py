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

import errno
import json
import os
import stat
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]


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
        self._lock = threading.Lock()
        #: A DESCRIPTOR HELD IN RESERVE, closed to make room when the process
        #: runs out and reopened afterwards.
        #:
        #: Round 10 measured the failure this prevents, and it is worse than the
        #: "a record is lost" it was first reported as. Under concurrency the fd
        #: budget is shared: one thread's delivery consumes the descriptors
        #: another thread's post-delivery audit write needs. The realised state
        #: was ~20 messages per run SITTING IN THE RECIPIENT'S MAILBOX, complete
        #: and readable, with no audit record, while the submitter was told the
        #: message was NOT sent. A retry then delivers twice with no trace of
        #: either. That is the log disagreeing with reality in the worst
        #: direction, on exactly the incident §3.3 exists to reconstruct.
        #:
        #: Sequentially it could not happen — delivery needs more descriptors
        #: than the audit write, so any budget permitting one permits the other.
        #: That is why it survived every non-concurrent test.
        self._spare_fd: Optional[int] = None
        #: Never renamed, so it identifies the same inode across a rotation. Held
        #: on the log file itself, the inter-process lock would be released to a
        #: second process the instant the rename happened — which is the window.
        self._lock_path = self.path.with_name(self.path.name + ".lock")
        self._reserve_spare()

    def _reserve_spare(self) -> None:
        if self._spare_fd is not None:
            return
        try:
            self._spare_fd = os.open(os.devnull, os.O_RDONLY)
        except OSError:
            self._spare_fd = None

    @contextmanager
    def _spare_released(self) -> Iterator[bool]:
        """Give back the reserved descriptor for the duration of a retry."""
        fd, self._spare_fd = self._spare_fd, None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            yield fd is not None
        finally:
            self._reserve_spare()

    @contextmanager
    def _open_lockfile(self) -> Iterator[Any]:
        """Open the lockfile, refusing anything that is not a regular file.

        THE LOCKFILE IS AN ATTACK SURFACE, and round 8 demonstrated three ways
        to use it. `open(path, "a")` on a path an agent controls will happily
        open whatever is there:

        - a **FIFO** with no reader blocks forever *while the shared threading
          lock is held*, so every other handler thread's audit write blocks
          behind it — and since every submission audits, one `mkfifo` silences
          all mail on the host, permanently.
        - a **directory** raises IsADirectoryError on every submission.
        - a **symlink** aims a broker-uid create wherever the agent chooses.

        O_NOFOLLOW refuses the symlink, O_NONBLOCK turns the FIFO into an
        immediate ENXIO instead of a hang, and the S_ISREG check refuses the
        directory and anything else exotic with a message that names the file.

        Failing here fails the audit write, which fails the submission. That is
        correct and deliberate: the record is mandatory, so no audit means no
        send. Refusing loudly beats both wedging and logging nothing.
        """
        fd = os.open(self._lock_path,
                     os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise OSError(
                    f"refusing to use '{self._lock_path}' as an audit lock: it is "
                    "not a regular file. Something replaced it, and taking a lock "
                    "on it could hang the broker or redirect a write.")
            try:
                os.fchmod(fd, 0o600)
            except OSError:
                pass
            f = os.fdopen(fd, "a")
        except BaseException:
            os.close(fd)
            raise
        try:
            yield f
        finally:
            f.close()

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        """Serialise rotate-then-append against every other writer.

        WITHOUT THIS, THE BOUNDED-RETENTION FIX DESTROYED THE EVIDENCE IT EXISTED
        TO PRESERVE. Two threads both observe size >= ceiling; the first renames
        the full log to `.1` and writes a one-line rotation marker; the second
        then renames THAT one-line file over `.1`, and the entire generation is
        gone. Measured at 7 lossy runs in 60 under ordinary concurrency, worst
        case 42 of 50 records lost — and the broker is multi-threaded by design,
        so this needed no attacker at all. An attacker only sharpens it: hold the
        log at the ceiling, then submit concurrently to rotate away the record of
        your own refused sends.

        Two locks, because there are two kinds of concurrent writer. The
        threading lock covers handler threads inside one broker. The advisory
        file lock covers separate broker processes, which this module's own write
        path already claims to support.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if fcntl is None:  # pragma: no cover - non-POSIX
                yield
                return
            with self._open_lockfile() as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

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
        # The lock spans BOTH operations. Locking them separately would leave
        # exactly the window it is meant to close: the loss happens between the
        # rename and the marker write, not inside either one.
        try:
            with self._exclusive():
                self._rotate_if_needed()
                self._write(record)
        except OSError as e:
            # OUT OF DESCRIPTORS IS NOT A REASON TO LOSE THE RECORD. Give the
            # reserved one back and try once more. If that still fails the
            # exception propagates, which fails the submission — correct, since
            # a delivery nobody can account for is worse than a refused one.
            if e.errno not in (errno.EMFILE, errno.ENFILE):
                raise
            with self._spare_released() as had_spare:
                if not had_spare:
                    raise
                with self._exclusive():
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

    def allowed(self, *, sender: str, recipients: List[str], message_id: str,
                rung: str, trust: Optional[Any] = None,
                authorship: Optional[str] = None) -> None:
        """`trust` is what a READER of the message can establish; `authorship` is
        what the BROKER established at submission.

        Both are recorded because they answer different questions and the second
        has nowhere else to live. The classification travels with the message in
        a header — but that header sits in the recipient's own mailbox, mode 700,
        rewritable by exactly the party an investigation would be about. The
        audit log is the one broker-owned record, so if the verdict is not here
        it is not anywhere an investigator can trust.
        """
        rec = {
            "decision": "allowed", "direction": "outbound", "sender": sender,
            "recipients": recipients, "message_id": message_id, "rung": rung,
        }
        if trust:
            rec["trust"] = trust
        if authorship:
            rec["authorship"] = authorship
        self._append(rec)

    def refused(self, *, sender: str, recipients: List[str], reason: str,
                message_id: Optional[str] = None) -> None:
        self._append({
            "decision": "refused", "direction": "outbound", "sender": sender,
            "recipients": recipients, "reason": reason, "message_id": message_id,
        })

    def inbound(self, *, sender: str, recipient: str, message_id: str,
                decision: str, reason: Optional[str] = None,
                trust: Optional[str] = None) -> None:
        rec = {
            "decision": decision, "direction": "inbound", "sender": sender,
            "recipients": [recipient], "message_id": message_id,
        }
        if reason:
            rec["reason"] = reason
        if trust:
            rec["trust"] = trust
        self._append(rec)

    def read(self, *, agent: str, operation: str,
             message_id: Optional[str] = None, count: Optional[int] = None,
             found: Optional[bool] = None) -> None:
        """Record that a mailbox was READ, and by whom.

        This exists because the argument for putting reads behind the broker was
        that a read going around it leaves no audit record and answers to no
        allowlist. Reads were then routed through the broker and still left no
        record -- the authorisation half of the argument implemented, the
        accountability half skipped. The gap was invisible in the test suite and
        obvious the first time a real deployment's log was read: three submission
        events and nothing at all for the reads that had just happened.

        `direction` is "mailbox" rather than inbound/outbound: nothing crosses a
        trust boundary here, which is exactly why this record is the only place
        the access is visible at all.
        """
        rec: Dict[str, Any] = {
            "decision": "read", "direction": "mailbox",
            "sender": agent, "operation": operation,
        }
        if message_id is not None:
            rec["message_id"] = message_id
        if count is not None:
            rec["count"] = count
        if found is not None:
            rec["found"] = found
        self._append(rec)

    def error(self, *, context: str, detail: str, sender: Optional[str] = None) -> None:
        """Operational failures belong here too — an outage with no trace is the
        exact gap this log exists to close.

        `sender` is the kernel-established identity where one was determined.
        A refusal record that does not say WHO was refused is a record an
        investigator cannot use, and §3.3 lists the sending identity as a
        minimum rather than an extra.
        """
        rec = {"decision": "error", "context": context, "detail": detail}
        if sender:
            rec["sender"] = sender
        self._append(rec)

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
