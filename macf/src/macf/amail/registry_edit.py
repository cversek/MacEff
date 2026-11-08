"""Changes to the operator's registry, shown before they are written (MIS-0004 R42, R45).

The registry is root's to write, and the operator asked that it be written by ``agent init`` and
by explicit commands, transparently and idempotently, never by hand-editing YAML. So every change
here is three separate acts:

- **A transform**, a pure function from the file's text to its new text: ``declare``, ``rotate``,
  ``retire``, ``cert_record``, ``cert_retire``. Run twice, it gives the same text, and when it has
  nothing to change it returns its input untouched, comments and all. Every result is held to the
  rules a load holds the file to (``registry.parse_text``), so nothing is shown that a reader would
  refuse.
- **A plan**: the current text, the new one and their diff. A plan with no change writes nothing.
- **Carrying it out**. Root (a container's start, or the operator) writes beside the file and
  renames it into place, then loads it as every reader does, ownership and ancestors included.
  Anyone else gets the change staged in a fresh temporary file, its sha256, and the one root step
  that installs exactly those bytes. A dry run shows the diff and writes nothing at all.

ROTATION FOLLOWS R45. The new key is declared from the moment of rotation, and every other key
still open is retired at that same moment. Mail the broker accepted before it verifies against the
old key, exactly one key verifies at any instant, and two keys never sign at once. A retired key
keeps its first end date: retiring it again changes nothing.
"""
from __future__ import annotations

import copy
import datetime
import difflib
import hashlib
import os
import shlex
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import yaml

from macf import calling_card

from .registry import Registry, RegistryError, parse_text


class RegistryEditError(ValueError):
    """A change the registry can't take, said before anything is shown or written."""


Change = Callable[[str], str]


# ---- the transforms ------------------------------------------------------------------------

def _load(text: str) -> Dict[str, Any]:
    try:
        parse_text(text)
    except RegistryError as e:
        raise RegistryEditError(f"the registry as it stands is refused, so it can't be changed: {e}") from e
    return copy.deepcopy(yaml.safe_load(text) or {})


def _dump(raw: Dict[str, Any]) -> str:
    text = yaml.safe_dump(raw, sort_keys=False, default_flow_style=False, allow_unicode=False)
    try:
        parse_text(text)
    except RegistryError as e:
        raise RegistryEditError(str(e)) from e
    return text


def _aware(at: datetime.datetime, what: str) -> datetime.datetime:
    if not isinstance(at, datetime.datetime) or at.utcoffset() is None:
        raise RegistryEditError(f"{what} needs a time with a timezone, such as 2026-11-08T00:00:00Z")
    return at


def _entry_name(raw: Dict[str, Any], card: str) -> Optional[str]:
    for declared in (raw.get("agents") or {}):
        if calling_card.same(declared, card):
            return declared
    return None


def _keys(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The entry's keys as mappings, bare ones expanded, so a window can be set on any of them."""
    entry["keys"] = [{"key": k} if isinstance(k, str) else k for k in entry.get("keys") or []]
    return entry["keys"]


def declare(text: str, card: str, account: str, key: str,
            valid_from: Optional[datetime.datetime] = None) -> str:
    """*key* declared for *card*, held by *account*: the entry made, or the key added to it."""
    raw = _load(text)
    name = _entry_name(raw, card)
    if name is None:
        calling_card.read_declared(card)
        raw.setdefault("agents", {})[card] = {"account": account, "keys": [
            key if valid_from is None else {"key": key, "valid_from": _aware(valid_from, "valid_from")}]}
        return _dump(raw)
    entry = raw["agents"][name]
    if entry.get("account") != account:
        raise RegistryEditError(f"{name} is declared on account {entry.get('account')!r}, not {account!r}; "
                                f"a key moves to another account by retiring it and declaring a new one")
    present = [k if isinstance(k, str) else k.get("key") for k in entry.get("keys") or []]
    if key in present:
        return text
    _keys(entry).append({"key": key} if valid_from is None
                        else {"key": key, "valid_from": _aware(valid_from, "valid_from")})
    return _dump(raw)


def rotate(text: str, card: str, new_key: str, at: datetime.datetime) -> str:
    """*new_key* valid for *card* from *at*, and every other open key retired at *at* (R45)."""
    _aware(at, "a rotation")
    raw = _load(text)
    name = _entry_name(raw, card)
    if name is None:
        raise RegistryEditError(f"{card} is not declared, so it has no key to rotate; declare it first")
    keys = _keys(raw["agents"][name])
    changed = False
    if new_key not in [k.get("key") for k in keys]:
        keys.append({"key": new_key, "valid_from": at})
        changed = True
    for k in keys:
        if k.get("key") == new_key or k.get("valid_until") is not None:
            continue
        if k.get("valid_from") is not None and k["valid_from"] >= at:
            raise RegistryEditError(f"a key of {name} starts at {k['valid_from'].isoformat()}, not before the "
                                    f"rotation at {at.isoformat()}, so it can't be retired then")
        k["valid_until"] = at
        changed = True
    return _dump(raw) if changed else text


def retire(text: str, card: str, key: str, at: datetime.datetime) -> str:
    """*key* of *card* retired at *at*: it signs nothing, and verifies only what was accepted
    before. A key already retired keeps its first end date."""
    _aware(at, "a retirement")
    raw = _load(text)
    name = _entry_name(raw, card)
    found = None
    if name is not None:
        found = next((k for k in _keys(raw["agents"][name]) if k.get("key") == key), None)
    if found is None:
        raise RegistryEditError(f"that key is not declared for {card}")
    if found.get("valid_until") is not None:
        return text
    found["valid_until"] = at
    return _dump(raw)


def cert_record(text: str, name: str, serial: str, not_after: datetime.date) -> str:
    """A certificate the operator's authority issued, by name, serial and expiry, never its key."""
    raw = _load(text)
    certs = raw.setdefault("certificates", [])
    for c in certs:
        if str(c.get("serial")).lower() == serial.lower():
            if c.get("name") == name and c.get("not_after") == not_after:
                return text
            raise RegistryEditError(f"serial {serial} is already recorded, for {c.get('name')!r} "
                                    f"expiring {c.get('not_after')}")
    certs.append({"name": name, "serial": serial, "not_after": not_after})
    return _dump(raw)


def cert_retire(text: str, serial: str, at: datetime.datetime) -> str:
    """The certificate with *serial* retired at *at*, before its expiry. A second retirement
    keeps the first time."""
    _aware(at, "a retirement")
    raw = _load(text)
    found = next((c for c in raw.get("certificates") or []
                  if str(c.get("serial")).lower() == serial.lower()), None)
    if found is None:
        raise RegistryEditError(f"no certificate with serial {serial} is recorded")
    if found.get("retired_at") is not None:
        return text
    found["retired_at"] = at
    return _dump(raw)


# ---- the plan, and carrying it out -------------------------------------------------------------

@dataclass
class Plan:
    path: Path
    current: str
    new: str

    @property
    def changed(self) -> bool:
        return self.new != self.current

    @property
    def diff(self) -> str:
        return "".join(difflib.unified_diff(self.current.splitlines(True), self.new.splitlines(True),
                                            fromfile=f"{self.path} (now)", tofile=f"{self.path} (after)"))


def plan(path: Union[str, Path], change: Change) -> Plan:
    """What *change* would make of the registry at *path* (absent counts as empty)."""
    path = Path(path)
    try:
        current = path.read_text()
    except FileNotFoundError:
        current = ""
    return Plan(path, current, change(current))


def root_step(staged: Path, target: Path, platform: str = sys.platform) -> str:
    """The one root step that installs the staged bytes at *target*: a root-owned directory, the
    file written beside the old one and renamed into place, so no reader sees half of it, then the
    check every reader makes."""
    group = "wheel" if platform == "darwin" else "root"
    q, d = shlex.quote, Path(target).parent
    beside = d / f".{Path(target).name}.new"
    return (f"sudo install -d -o root -g {group} -m 0755 {q(str(d))} && "
            f"sudo install -o root -g {group} -m 0644 {q(str(staged))} {q(str(beside))} && "
            f"sudo mv -f {q(str(beside))} {q(str(target))} && "
            f"macf_tools amail registry check --path {q(str(target))}")


def carry_out(p: Plan, *, dry_run: bool, is_root: Optional[bool] = None, root_uid: int = 0,
              staging_dir: Optional[Union[str, Path]] = None, platform: str = sys.platform,
              out: Callable[[str], None] = print) -> int:
    """Show *p*, then write it as root, stage it for root, or (a dry run) stop. 0, or 1 when a
    root write left a registry that won't load."""
    if not p.changed:
        out(f"✅ the registry {p.path} is already current; nothing to write")
        return 0
    out(p.diff.rstrip("\n"))
    if dry_run:
        out("dry run: nothing written, nothing staged")
        return 0
    if is_root is None:
        is_root = os.geteuid() == 0
    if is_root:
        p.path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        beside = p.path.parent / f".{p.path.name}.new"
        fd = os.open(beside, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        with os.fdopen(fd, "w") as f:
            f.write(p.new)
        os.chmod(beside, 0o644)
        os.replace(beside, p.path)
        try:
            Registry(p.path, root_uid=root_uid).load()
        except RegistryError as e:
            out(f"❌ written, but it won't load as readers load it: {e}")
            return 1
        out(f"✅ the registry {p.path} is written and loads")
        return 0
    fd, name = tempfile.mkstemp(prefix="maceff-registry.", suffix=".staged.yaml",
                                dir=str(staging_dir) if staging_dir else None)
    with os.fdopen(fd, "w") as f:
        f.write(p.new)
    os.chmod(name, 0o644)
    staged = Path(name)
    digest = hashlib.sha256(staged.read_bytes()).hexdigest()
    out(f"The registry is root's to write. The change is staged at {staged}  sha256 {digest}")
    out("Run as root:")
    out(f"  {root_step(staged, p.path, platform)}")
    return 0
