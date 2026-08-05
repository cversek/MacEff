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
    tmp_fd = os.open(str(d / "tmp"), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        new_fd = os.open(str(d / "new"), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
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

    q = maildir_for(home) / "quarantine"
    _assert_real_dir(maildir_for(home))
    _assert_real_dir(q)
    q.mkdir(mode=0o700, parents=True, exist_ok=True)
    _assert_real_dir(q)
    p = q / _unique_name()
    # The reason is derived from the message's own claimed sender, which is
    # attacker-controlled — so it gets the same header sanitisation as any other
    # interpolated value. Quarantined mail is the LAST place to relax that: it is
    # hostile by assumption, and a reader inspecting it is the intended victim.
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"X-Amail-Quarantine-Reason: {_hdr(reason)}\n" + message.serialize())
    return p
