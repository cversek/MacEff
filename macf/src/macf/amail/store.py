"""Maildir delivery — the authoritative local store.

A standard Maildir in the agent's home, deliberately NOT under the framework's
artifact tree: an account may be provisioned without that tree entirely, and mail
inside it would make correspondence a framework-only capability.

Delivery uses the Maildir tmp/->new/ rename, which is the whole reason Maildir
exists: a reader scanning new/ never observes a half-written file, because rename
within a filesystem is atomic. Writing straight into new/ would race every reader.
"""
from __future__ import annotations

import itertools
import os
import socket
import threading
import time
from pathlib import Path
from typing import List, Optional

from .models import Message

SUBDIRS = ("tmp", "new", "cur")


def maildir_for(home: Path) -> Path:
    return Path(home) / "Maildir"


def _assert_real_dir(p: Path) -> None:
    """Refuse to treat a symlink as a directory.

    O_NOFOLLOW guards only the FINAL path component. The mailbox is agent-owned,
    so an agent can replace `Maildir/new` — or `Maildir` itself — with a symlink
    and redirect a broker-uid write outside the mailbox entirely, or aim a
    chmod at someone else's file. mkdir(exist_ok=True) accepts a symlinked
    directory silently, which is how this went unnoticed.
    """
    if p.is_symlink():
        raise OSError(f"refusing to use '{p}': it is a symlink, not a directory")
    if p.exists() and not p.is_dir():
        raise OSError(f"refusing to use '{p}': not a directory")


def _open_dir(name: str, dir_fd: Optional[int] = None) -> int:
    """Open a directory as a descriptor, refusing a symlink at that component.

    Every subsequent operation is done relative to the returned descriptor, so
    the inode verified here is the inode written to. Opening by name and then
    writing by name is a check, not a constraint — the name can be swapped in
    between. Round 6 won exactly that race against the quarantine path in 47
    iterations while the same attack against the descriptor-based delivery path
    failed 0-for-200k, which is the difference this helper exists to make
    uniform.
    """
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)


def ensure_maildir(home: Path) -> Path:
    d = maildir_for(home)
    _assert_real_dir(d)
    for sub in SUBDIRS:
        _assert_real_dir(d / sub)
    for sub in SUBDIRS:
        (d / sub).mkdir(mode=0o700, parents=True, exist_ok=True)
        _assert_real_dir(d / sub)
    d.chmod(0o700)
    return d


_counter = itertools.count()
_counter_lock = threading.Lock()


def _unique_name() -> str:
    """Maildir's uniqueness convention: time.pid_counter.host.

    The counter is NOT decorative. Maildir names are second-granular, so without
    it two deliveries inside the same second collide — and because delivery ends
    in a rename, the second silently OVERWRITES the first. Mail disappears with no
    error anywhere. A broker delivering a thread writes several messages in well
    under a second, so this is the common case rather than a rare race.

    Locked because the broker serves agents on threads; two threads reading the
    same counter value would reintroduce exactly the collision.
    """
    with _counter_lock:
        seq = next(_counter)
    return f"{int(time.time())}.{os.getpid()}_{seq}.{socket.gethostname()}"


def deliver(home: Path, message: Message) -> Path:
    """Write a message into the recipient's Maildir. Returns the final path.

    Called by the BROKER, never by a peer agent — which is why no agent needs
    read or write access to another agent's mailbox. That access requirement was
    the actual blocker the previous convention hit, and widening permissions to
    solve it would have been the wrong direction.
    """
    d = ensure_maildir(home)
    name = _unique_name()

    # DIRECTORY FILE DESCRIPTORS, not paths.
    #
    # Checking a directory by name and then opening by name is a check, not a
    # constraint: the name can be swapped between the two, and an audit won the
    # race in about 15k attempts. O_NOFOLLOW only ever guarded the final
    # component. Resolving each directory ONCE to a descriptor and doing every
    # subsequent operation relative to it removes the window — the fd refers to
    # the inode that was verified, and renaming the name afterwards cannot
    # redirect it.
    # Anchored at the Maildir itself, then tmp/ and new/ RELATIVE to that
    # descriptor. Opening "…/Maildir/tmp" by full path leaves the `Maildir`
    # component resolvable by name after it was checked; anchoring removes that
    # window too, so no component of the path is trusted twice.
    md_fd = _open_dir(str(d))
    try:
        tmp_fd = _open_dir("tmp", dir_fd=md_fd)
        try:
            new_fd = _open_dir("new", dir_fd=md_fd)
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=tmp_fd)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(message.serialize())
                except BaseException:
                    try:
                        os.unlink(name, dir_fd=tmp_fd)
                    except OSError:
                        pass
                    raise
                # Atomic, and both endpoints are the verified inodes.
                os.rename(name, name, src_dir_fd=tmp_fd, dst_dir_fd=new_fd)
            finally:
                os.close(new_fd)
        finally:
            os.close(tmp_fd)
    finally:
        os.close(md_fd)
    return d / "new" / name


def deliver_raw(home: Path, raw: bytes, sidecar: str) -> Path:
    """Deliver internet mail: raw RFC 822 bytes, exactly as transport-verified.

    Spec F6.1: foreign mail is NOT re-wrapped in the agent-bundle format --
    doing so would sign an authorship claim about a message the broker did not
    author. The raw bytes go into new/ untouched (so any later hash check still
    matches the transport-verified value), and the verified provenance rides in
    a SIDECAR at Maildir/sidecars/<name>.json -- the spec's common-denominator
    index (F6.3), one per delivery.

    Same descriptor discipline as deliver(), for the same adversarially-proven
    reason: the mailbox is agent-owned, and a name checked then reused is a
    race an audit has already won once.
    """
    d = ensure_maildir(home)
    side = d / "sidecars"
    _assert_real_dir(side)
    side.mkdir(mode=0o700, parents=True, exist_ok=True)
    _assert_real_dir(side)
    name = _unique_name()

    md_fd = _open_dir(str(d))
    try:
        tmp_fd = _open_dir("tmp", dir_fd=md_fd)
        try:
            new_fd = _open_dir("new", dir_fd=md_fd)
            try:
                side_fd = _open_dir("sidecars", dir_fd=md_fd)
                try:
                    # Sidecar FIRST: a message in new/ whose sidecar is missing
                    # would be mail without provenance, which downstream reads
                    # as less trustworthy than it is. If the message write then
                    # fails, the error path removes the sidecar too -- an
                    # orphan sidecar is not "collectable later", it is a leak
                    # this function created and must clean up itself.
                    sfd = os.open(f"{name}.json",
                                  os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                  0o600, dir_fd=side_fd)
                    with os.fdopen(sfd, "w", encoding="utf-8") as f:
                        f.write(sidecar)
                    try:
                        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=tmp_fd)
                        try:
                            with os.fdopen(fd, "wb") as f:
                                f.write(raw)
                        except BaseException:
                            try:
                                os.unlink(name, dir_fd=tmp_fd)
                            except OSError:
                                pass
                            raise
                        os.rename(name, name, src_dir_fd=tmp_fd, dst_dir_fd=new_fd)
                    except BaseException:
                        try:
                            os.unlink(f"{name}.json", dir_fd=side_fd)
                        except OSError:
                            pass
                        raise
                finally:
                    os.close(side_fd)
            finally:
                os.close(new_fd)
        finally:
            os.close(tmp_fd)
    finally:
        os.close(md_fd)
    return d / "new" / name


def read_all(home: Path, include_seen: bool = True) -> List[Message]:
    """Every message in the mailbox, ordered per the policy's sort key.

    Order comes from (date, message_id) — not from filenames, not from a counter,
    and not from directory listing order, which is unspecified.
    """
    d = maildir_for(home)
    if not d.exists():
        return []
    boxes = ["new"] + (["cur"] if include_seen else [])
    out: List[Message] = []
    for box in boxes:
        p = d / box
        if not p.is_dir():
            continue
        for f in p.iterdir():
            if not f.is_file():
                continue
            try:
                out.append(Message.deserialize(f.read_text()))
            except (OSError, ValueError):
                # A malformed file is skipped rather than fatal: one bad message
                # must not make the whole mailbox unreadable.
                continue
    return sorted(out, key=lambda m: m.sort_key())


def thread(home: Path, thread_id: str) -> List[Message]:
    return [m for m in read_all(home) if m.thread_id == thread_id]


def find(home: Path, message_id: str) -> Optional[Message]:
    for m in read_all(home):
        if m.message_id == message_id:
            return m
    return None


def quarantine(home: Path, message: Message, reason: str) -> Path:
    """Retain mail from an unlisted sender without delivering it to the inbox.

    Retained rather than rejected: rejecting at the transport boundary reveals
    which addresses exist, and legitimately forwarded mail can arrive from an
    unexpected envelope sender. Quarantine keeps the evidence and keeps the
    decision reversible.
    """
    from .models import _hdr

    d = maildir_for(home)
    q = d / "quarantine"
    _assert_real_dir(d)
    _assert_real_dir(q)
    q.mkdir(mode=0o700, parents=True, exist_ok=True)
    _assert_real_dir(q)
    name = _unique_name()

    # DIRECTORY FILE DESCRIPTORS, for the same reason delivery uses them.
    #
    # This path previously did _assert_real_dir() and then os.open(str(q / name)).
    # O_NOFOLLOW guards only the FINAL component, so `Maildir` and `quarantine`
    # were re-resolved by name after being checked, and round 6 won that race in
    # 47 iterations — coercing a broker-uid write to an arbitrary broker-writable
    # location, which turns quarantine into delivery and defeats §6.1 outright.
    #
    # The guards above are kept: they refuse a symlink that is ALREADY in place
    # with a message naming it, which the descriptors alone would report only as
    # a bare ELOOP. Belt and braces, cheap, and the error text is the difference
    # between a diagnosable refusal and a puzzling one.
    md_fd = _open_dir(str(d))
    try:
        q_fd = _open_dir("quarantine", dir_fd=md_fd)
        try:
            # The reason is derived from the message's own claimed sender, which is
            # attacker-controlled — so it gets the same header sanitisation as any
            # other interpolated value. Quarantined mail is the LAST place to relax
            # that: it is hostile by assumption, and a reader inspecting it is the
            # intended victim.
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=q_fd)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"X-Amail-Quarantine-Reason: {_hdr(reason)}\n"
                        + message.serialize())
        finally:
            os.close(q_fd)
    finally:
        os.close(md_fd)
    return q / name
