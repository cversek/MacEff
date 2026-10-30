#!/usr/bin/env python3
"""Probes for experiment 016, MIS-0004's container half.

Each subcommand runs inside the disposable container, as whichever account the harness chose,
and prints one JSON object per line. Nothing here trusts a name it didn't check.
"""
import argparse
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

SOCK = Path("/run/amail/broker.sock")
HOLD = Path("/run/amail-exp")
DOMAIN = "proto.local"


def out(**kw):
    print(json.dumps(kw, default=str), flush=True)


def addr(local):
    return local if "@" in local else f"{local}@{DOMAIN}"


def cmd_send(a):
    """Submit messages over the broker socket as this account, optionally claiming another sender."""
    from macf.amail.client import submit
    from macf.amail.models import Message
    for i in range(a.n):
        m = Message(sender=addr(a.claim or a.sender), to=[addr(t) for t in a.to], subject=f"{a.tag} {i}",
                    body=f"{a.tag} body {i}")
        if a.message_id:
            m.message_id = a.message_id
        try:
            r = submit((a.claim or a.sender).split("@")[0], m, SOCK)  # the claim is the agent's name
            out(kind="send", tag=a.tag, id=m.message_id, broker_id=r.get("message_id"), ok=bool(r.get("ok")),
                resp=json.dumps(r)[:600])
        except Exception as e:  # noqa: BLE001 - every refusal is data here
            out(kind="send", tag=a.tag, id=m.message_id, ok=False, error=f"{type(e).__name__}: {str(e)[:300]}")
        if a.gap:
            time.sleep(a.gap)


def cmd_raw(a):
    """One raw request on the socket, for requests the client wouldn't build."""
    from macf.amail.client import _roundtrip
    try:
        out(kind="raw", req=a.json, resp=json.dumps(_roundtrip(json.loads(a.json), SOCK, 10.0, "raw probe"))[:800])
    except Exception as e:  # noqa: BLE001
        out(kind="raw", req=a.json, error=f"{type(e).__name__}: {str(e)[:300]}")


def cmd_status(a):
    from macf.amail.client import status
    try:
        out(kind="status", resp=status(SOCK))
    except Exception as e:  # noqa: BLE001
        out(kind="status", error=f"{type(e).__name__}: {str(e)[:300]}")


def cmd_receiver(a):
    """The stand-in receiver unit: pull this seat's box into its own store, forever, unless the
    harness holds it with a flag file (the experiment's instrument, not an instruction channel)."""
    from macf.amail.client import ingest
    home, box, seat = Path(a.home), Path(a.box), a.seat
    out(kind="receiver_up", seat=seat, uid=os.getuid(), groups=os.getgroups())
    while True:
        if not (HOLD / f"hold-{seat}").exists():
            try:
                for r in ingest(home, box, agent=seat):
                    out(kind="ingest", seat=seat,
                        **{f"r_{k}": v for k, v in r.items() if isinstance(v, (str, int, float, bool, type(None)))})
            except Exception as e:  # noqa: BLE001 - a receiver that dies on one entry stops everything
                out(kind="ingest_error", seat=seat, error=f"{type(e).__name__}: {str(e)[:300]}")
        time.sleep(a.interval)


def cmd_ingest(a):
    """One ingest pass as this seat, as the code on main does it today."""
    from macf.amail.client import ingest
    for r in ingest(Path(a.home), Path(a.box), agent=a.seat):
        out(kind="ingest", seat=a.seat,
            **{f"r_{k}": v for k, v in r.items() if isinstance(v, (str, int, float, bool, type(None)))})


def cmd_store(a):
    """The message ids in this seat's own store, with the trust each carries."""
    from macf.amail import store
    msgs = store.read_all(Path(a.home))
    out(kind="store", seat=a.seat, n=len(msgs),
        items=[{"id": m.message_id, "subject": m.subject, "trust": getattr(m, "trust", None)} for m in msgs])


def cmd_stat(a):
    """The box and every entry in it, as this account sees them."""
    box = Path(a.box)
    try:
        st = os.stat(box)
        out(kind="box", box=str(box), uid=st.st_uid, gid=st.st_gid, mode=oct(stat.S_IMODE(st.st_mode)),
            setgid=bool(st.st_mode & stat.S_ISGID))
        names = sorted(os.listdir(box))
    except OSError as e:
        out(kind="box", box=str(box), error=f"{type(e).__name__}: {e.strerror}")
        return
    for n in names[: a.limit]:
        try:
            st = os.lstat(box / n)
            out(kind="entry", name=n, uid=st.st_uid, gid=st.st_gid, mode=oct(stat.S_IMODE(st.st_mode)),
                nlink=st.st_nlink, ino=st.st_ino, symlink=stat.S_ISLNK(st.st_mode),
                group_writable=bool(st.st_mode & stat.S_IWGRP))
        except OSError as e:
            out(kind="entry", name=n, error=e.strerror)
    out(kind="box_count", box=str(box), n=len(names))


def cmd_watch(a):
    """Sample the box for a while; report any entry ever seen writable by its group or others."""
    box, end, seen, bad, samples = Path(a.box), time.time() + a.seconds, set(), {}, 0
    while time.time() < end:
        samples += 1
        try:
            for n in os.listdir(box):
                try:
                    st = os.lstat(box / n)
                except FileNotFoundError:
                    continue
                seen.add(n)
                if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                    bad[n] = oct(stat.S_IMODE(st.st_mode))
        except OSError as e:
            out(kind="watch_error", error=e.strerror)
            return
    out(kind="watch", box=str(box), samples=samples, entries_seen=len(seen), n_writable=len(bad),
        writable=dict(list(bad.items())[:10]))


def cmd_plant(a):
    """As the recipient's own account, plant an entry the broker never wrote."""
    from macf.amail.models import Message
    box = Path(a.box)
    mid = f"msg-planted-{a.kind}"
    stem = f"{int(time.time())}-{mid}"
    m = Message(sender=addr("seat_b"), to=[addr("seat_a")], subject=f"PLANTED {a.kind}",
                body="written by the recipient's own account, not the broker", message_id=mid)
    payload = m.serialize().encode()
    side = {"kind": "bundle", "handed_off_at": "2026-10-30T00:00:00Z", "message_id": mid,
            "sender": addr("seat_b"), "recipient": addr("seat_a"), "raw_sha256": hashlib.sha256(payload).hexdigest(),
            "authorization": {"outcome": "deliver-pull", "reason": "planted"}, "broker_trust": "verified",
            "rung": "local", "origin_domain": DOMAIN}
    try:
        if a.kind == "owned":
            (box / f"{stem}.json").write_text(json.dumps(side))
            (box / f"{stem}.amsg").write_bytes(payload)
        elif a.kind == "symlink":
            t = Path(a.home) / "planted"
            t.mkdir(exist_ok=True)
            (t / "s.json").write_text(json.dumps(side))
            (t / "s.amsg").write_bytes(payload)
            os.symlink(t / "s.json", box / f"{stem}.json")
            os.symlink(t / "s.amsg", box / f"{stem}.amsg")
        elif a.kind == "hardlink":
            target = next((box / n for n in sorted(os.listdir(box)) if n.endswith(".amsg")
                           and os.lstat(box / n).st_uid != os.getuid()), None)
            if target is None:
                out(kind="plant", plant=a.kind, ok=False, error="no broker-owned entry to link")
                return
            os.link(target, box / f"{stem}.amsg")
        elif a.kind == "groupwritable":  # the control for E1's watch
            p = box / f"{stem}.ctl"
            p.write_text("control")
            os.chmod(p, 0o660)
        out(kind="plant", plant=a.kind, ok=True, stem=stem)
    except OSError as e:
        out(kind="plant", plant=a.kind, ok=False, error=f"{type(e).__name__}: {e.strerror}")


def cmd_r37(a):
    """The candidate R37 check: classify every pair through descriptors, trusting no name."""
    box_fd = os.open(a.box, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for n in sorted(os.listdir(box_fd)):
            if not n.endswith(".amsg"):
                continue
            parts = {}
            for part in (n, n[:-5] + ".json"):
                try:
                    fd = os.open(part, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=box_fd)
                except OSError as e:
                    parts[part] = f"refused: {e.strerror}"
                    continue
                st = os.fstat(fd)
                os.close(fd)
                if not stat.S_ISREG(st.st_mode):
                    parts[part] = "refused: not a regular file"
                elif st.st_uid != a.broker_uid:
                    parts[part] = f"refused: owned by uid {st.st_uid}, not the broker's"
                elif st.st_nlink != 1:
                    parts[part] = f"refused: {st.st_nlink} links"
                else:
                    parts[part] = "accept"
            out(kind="r37", entry=n, accept=all(v == "accept" for v in parts.values()), parts=parts)
    finally:
        os.close(box_fd)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("--sender", required=True)
    s.add_argument("--claim")
    s.add_argument("--to", nargs="+", required=True)
    s.add_argument("--n", type=int, default=1)
    s.add_argument("--tag", default="probe")
    s.add_argument("--message-id")
    s.add_argument("--gap", type=float, default=0.0)
    s = sub.add_parser("raw")
    s.add_argument("--json", required=True)
    sub.add_parser("status")
    for name in ("receiver", "ingest", "store"):
        s = sub.add_parser(name)
        s.add_argument("--seat", required=True)
        s.add_argument("--home", required=True)
        s.add_argument("--box", default="")
        s.add_argument("--interval", type=float, default=1.0)
    s = sub.add_parser("stat")
    s.add_argument("--box", required=True)
    s.add_argument("--limit", type=int, default=12)
    s = sub.add_parser("watch")
    s.add_argument("--box", required=True)
    s.add_argument("--seconds", type=float, default=10)
    s = sub.add_parser("plant")
    s.add_argument("--box", required=True)
    s.add_argument("--home", required=True)
    s.add_argument("--kind", choices=("owned", "symlink", "hardlink", "groupwritable"), required=True)
    s = sub.add_parser("r37")
    s.add_argument("--box", required=True)
    s.add_argument("--broker-uid", type=int, required=True)
    a = ap.parse_args()
    globals()[f"cmd_{a.cmd}"](a)


if __name__ == "__main__":
    sys.exit(main())
