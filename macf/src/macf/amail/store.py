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
import json
import os
import socket
import sys
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

    Always called AS THE MAILBOX OWNER: under the pickup-box model the
    recipient itself ingests from the broker's handoff box into its own
    store, so ownership is correct by construction and no caller ever
    writes across a uid boundary.
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



def bundle_sidecars_for(home: Path) -> Path:
    """Where ingest records its verdict for AGENT messages.

    A separate directory from `sidecars/` on purpose. The internet listing
    discriminates by sidecar presence in `sidecars/`, so writing bundle
    sidecars there would make every ingested agent message read as internet
    mail — re-creating the facet overlap that was just fixed, from the other
    direction. Same evidence, different index.
    """
    return maildir_for(home) / "bundle_sidecars"


def write_bundle_sidecar(home: Path, name: str, sidecar: str) -> Path:
    """Record the ingest verdict beside an agent message, owned by the agent."""
    d = bundle_sidecars_for(home)
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    p = d / f"{name}.json"
    p.write_text(sidecar)
    p.chmod(0o600)
    return p


def read_bundle_sidecar(home: Path, name: str) -> Optional[dict]:
    """The recorded ingest verdict for one agent message, or None."""
    p = bundle_sidecars_for(home) / f"{name}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: unreadable bundle sidecar {p.name}: {e}", file=sys.stderr)
        return None


def read_all(home: Path, include_seen: bool = True) -> List[Message]:
    """Every AGENT-BUNDLE message in the mailbox, ordered per the policy's
    sort key.

    Order comes from (date, message_id) — not from filenames, not from a counter,
    and not from directory listing order, which is unspecified.

    INTERNET MAIL IS EXCLUDED, by sidecar presence — the same discriminator
    read_internet() uses, so one delivery cannot appear in both facets.
    It has to be excluded explicitly because internet mail is stored as raw
    RFC 822 (spec F6.1: never re-wrapped, so the transport-verified hash
    still matches), and raw mail parses well enough here to impersonate a
    bundle: From/To/Subject line up, the body survives, and only `thread-id`
    is missing — whereupon Message.__post_init__ MINTS one from the current
    clock. That produced two live defects the operator caught by asking why
    the counts disagreed with reality: one internet message double-counted
    as a phantom "bundle" tagged unclassified, and a thread id that changed
    between two back-to-back listings. A thread identifier that changes each
    time you look at it cannot thread anything; both were the same defect,
    which is that this function's aperture was never narrowed to its own
    format.
    """
    d = maildir_for(home)
    if not d.exists():
        return []
    side = d / "sidecars"
    internet = {sc.stem for sc in side.glob("*.json")} if side.is_dir() else set()
    boxes = ["new"] + (["cur"] if include_seen else [])
    out: List[Message] = []
    for box in boxes:
        p = d / box
        if not p.is_dir():
            continue
        for f in p.iterdir():
            if not f.is_file() or f.name in internet:
                continue
            try:
                out.append(Message.deserialize(f.read_text()))
            except (OSError, ValueError):
                # A malformed file is skipped rather than fatal: one bad message
                # must not make the whole mailbox unreadable.
                continue
    return sorted(out, key=lambda m: m.sort_key())


def read_internet(home: Path) -> List[dict]:
    """Every internet-mail delivery in this mailbox, by its sidecar.

    Sidecar presence is what distinguishes internet mail from agent bundles
    in the shared Maildir — the sidecar IS the uniform index, so the listing
    is built from sidecars alone and never parses raw mail. A sidecar whose
    message file is missing is still listed, flagged, because a half-pair is
    evidence of an interrupted delivery and hiding evidence is how gaps go
    unexplained.
    """
    d = maildir_for(home)
    side = d / "sidecars"
    if not side.is_dir():
        return []
    out: List[dict] = []
    for sc in sorted(side.glob("*.json")):
        name = sc.stem
        try:
            meta = json.loads(sc.read_text())
        except (OSError, ValueError) as e:
            print(f"⚠️ MACF: unreadable sidecar {sc.name} (listed as "
                  f"damaged): {e}", file=sys.stderr)
            meta = {"damaged": str(e)}
        present = any((d / box / name).is_file() for box in ("new", "cur"))
        out.append({"name": name, "sidecar": meta, "message_present": present})
    return out


def find_internet(home: Path, ref: str) -> Optional[tuple]:
    """(raw bytes, sidecar dict) for one internet message, or None.

    `ref` is the delivery name or a prefix of the content sha256 — both are
    values the owner learned from their own listing, so neither is guessable
    authority over anyone else's mail (the home is already the caller's own).
    """
    for item in read_internet(home):
        sha = str(item["sidecar"].get("raw_sha256", ""))
        if item["name"] == ref or (ref and sha.startswith(ref)):
            d = maildir_for(home)
            for box in ("new", "cur"):
                p = d / box / item["name"]
                if p.is_file():
                    return p.read_bytes(), item["sidecar"]
            return None
    return None


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
