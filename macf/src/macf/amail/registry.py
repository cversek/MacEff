"""The operator's registry: each MacEff agent's public keys, and each certificate the operator's
authority issued (MIS-0004 R42).

WHY A FILE ONLY THE OPERATOR CAN WRITE. Until now an agent's keys were declared in its own contact
list, which the agent can write. A key the agent declares for itself proves nothing to a broker or
a receiver: anything that can run as the agent can declare a key of its own choosing. So the keys
move to one file per system that only root can write, which the operator edits by hand or by his
install step, and which every broker and receiver reads.

WHY ONE FILE FOR BOTH. The repo owner chose it on #867: the agents' signing keys and the record of
each certificate his authority issues live together. A certificate is recorded by its name, serial
and expiry, never its key, so revocation has a source and nothing secret is in the file.

WHAT LOADING REFUSES, before anything reads a key from it:
- a file not owned by root, or one that group or others can write;
- a directory holding it that someone other than root could write, since whoever can write the
  directory can replace the file;
- an ancestor directory, up to ``/``, that someone other than root could write without the sticky
  bit, since whoever can write an ancestor can swap the path beneath it;
- a card that isn't ``Name_shortid`` (MIS-0002 R165), the same card twice in any case, an entry
  without its account or its keys, a key that isn't ``ed25519:<base64>``, the same key twice in an
  entry, or a validity window that isn't timezone-aware or ends before it starts;
- a certificate entry with anything but ``name``, ``serial`` and ``not_after``, so no key or secret
  can be filed there by mistake.

WHY KEYS CARRY WINDOWS (MIS-0004 R45). A key is either a bare ``ed25519:<base64>`` string, valid
from the start and not retired, or a mapping with ``valid_from`` and ``valid_until``. A key with
``valid_until`` is retired: it never signs, and it verifies only what the broker accepted inside its
window. The times are timezone-aware, because the broker's acceptance time is compared against them.

WHY AN ACCOUNT MAPS TO SEVERAL CARDS (MIS-0004 R46). On a shared login two cards declare one account,
and that is exactly what a receiver has to see, so ``cards_of_account`` returns every one.

Lookups compare cards without regard to case (MIS-0002 R164). The file is read per call, so an
edit takes effect at the next decision, as the contact list does.

Format (YAML)::

    agents:
      ExampleAgent_0a1b2c:
        account: exampleagent_0a1b2c
        keys:
          - "ed25519:<base64>"
          - key: "ed25519:<base64>"
            valid_from: 2026-11-08T00:00:00Z
            valid_until: 2027-11-08T00:00:00Z
    certificates:
      - name: exampleagent_0a1b2c
        serial: "3f9a..."
        not_after: 2036-11-08
"""
from __future__ import annotations

import datetime
import os
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from macf import calling_card

from .crypto import SigningError, parse_public_key

#: Where a system's registry lives unless the deployment declares another path.
DEFAULT_PATH = Path("/etc/maceff/registry.yaml")


class RegistryError(ValueError):
    """The registry can't be trusted or read. Never fall back to the agent's own declarations."""


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class KeyEntry(_Closed):
    """One declared key, with the window it is valid in (MIS-0004 R45)."""
    key: str
    valid_from: Optional[datetime.datetime] = None
    valid_until: Optional[datetime.datetime] = None

    @field_validator("key")
    @classmethod
    def _key_parses(cls, key: str) -> str:
        try:
            parse_public_key(key)
        except SigningError as e:
            raise ValueError(str(e)) from e
        return key

    @field_validator("valid_from", "valid_until")
    @classmethod
    def _aware(cls, t: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if t is not None and t.utcoffset() is None:
            raise ValueError(f"{t.isoformat()} has no timezone; write it with one, such as Z")
        return t

    @model_validator(mode="after")
    def _ordered(self) -> "KeyEntry":
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must come after valid_from")
        return self

    @property
    def retired(self) -> bool:
        """A key with an end date is retired: it never signs (R45)."""
        return self.valid_until is not None

    def valid_at(self, when: datetime.datetime) -> bool:
        return ((self.valid_from is None or self.valid_from <= when)
                and (self.valid_until is None or when < self.valid_until))


class AgentEntry(_Closed):
    account: str = Field(min_length=1, max_length=64)
    keys: List[KeyEntry] = Field(min_length=1)

    @field_validator("keys", mode="before")
    @classmethod
    def _bare_or_mapping(cls, keys: Any) -> Any:
        if not isinstance(keys, list):
            return keys
        return [{"key": k} if isinstance(k, str) else k for k in keys]

    @field_validator("keys")
    @classmethod
    def _each_once(cls, keys: List[KeyEntry]) -> List[KeyEntry]:
        seen = set()
        for k in keys:
            if k.key in seen:
                raise ValueError(f"the key {k.key[:20]}... is declared twice")
            seen.add(k.key)
        return keys


class CertificateEntry(_Closed):
    name: str = Field(min_length=1, max_length=64)
    serial: str = Field(min_length=1, max_length=64, pattern=r"^[0-9A-Fa-f:]+$")
    not_after: datetime.date


class _RegistryFile(_Closed):
    agents: Dict[str, AgentEntry] = Field(default_factory=dict)
    certificates: List[CertificateEntry] = Field(default_factory=list)


def check_owner(path: Path, root_uid: int = 0) -> None:
    """Refuse a registry that anyone but root could write, directly or by replacing it."""
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError as e:
        raise RegistryError(f"the registry {path} can't be read: {e}") from e
    if not stat.S_ISREG(st.st_mode):
        raise RegistryError(f"the registry {path} is not a regular file")
    if st.st_uid != root_uid:
        raise RegistryError(f"the registry {path} is owned by uid {st.st_uid}, not root: only the "
                            f"operator may write it (MIS-0004 R42)")
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RegistryError(f"the registry {path} is writable by group or others "
                            f"(mode {stat.S_IMODE(st.st_mode):o}); make it 644 (MIS-0004 R42)")
    parent = Path(path).parent
    pst = os.stat(parent)
    if pst.st_uid != root_uid or pst.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RegistryError(f"the directory {parent} holding the registry could be written by "
                            f"someone other than root, who could replace the file (MIS-0004 R42)")
    # Every ancestor, up to /: whoever can write one can swap the path beneath it. A sticky
    # world-writable directory such as /tmp lets no one rename another's entry, so it passes.
    for ancestor in Path(os.path.abspath(parent)).parents:
        ast = os.stat(ancestor)
        writable = ast.st_mode & (stat.S_IWGRP | stat.S_IWOTH) and not ast.st_mode & stat.S_ISVTX
        if ast.st_uid not in (root_uid, 0) or writable:
            raise RegistryError(f"the directory {ancestor} above the registry could be written by "
                                f"someone other than root, who could swap the path to it (MIS-0004 R42)")


class Registry:
    """The operator's registry at *path*, checked and read per call."""

    def __init__(self, path: Union[str, Path] = DEFAULT_PATH, *, root_uid: int = 0):
        self.path = Path(path)
        self.root_uid = root_uid

    def load(self) -> _RegistryFile:
        check_owner(self.path, self.root_uid)
        try:
            raw = yaml.safe_load(self.path.read_text()) or {}
        except (OSError, yaml.YAMLError) as e:
            raise RegistryError(f"the registry {self.path} can't be parsed: {e}") from e
        try:
            parsed = _RegistryFile.model_validate(raw)
        except ValidationError as e:
            raise RegistryError(f"the registry {self.path} is malformed: {e}") from e
        seen: Dict[str, str] = {}
        for card in parsed.agents:
            try:
                calling_card.read_declared(card)
            except calling_card.CardError as e:
                raise RegistryError(f"the registry {self.path}: {e}") from e
            folded = card.casefold()
            if folded in seen:
                raise RegistryError(f"the registry {self.path} declares {seen[folded]} and {card}, "
                                    f"which are the same card (MIS-0002 R164)")
            seen[folded] = card
        return parsed

    def _entry(self, card: str) -> Optional[AgentEntry]:
        for declared, entry in self.load().agents.items():
            if calling_card.same(declared, card):
                return entry
        return None

    def key_entries(self, card: str) -> List[KeyEntry]:
        """Every key the operator declared for *card*, with its window (R45); empty when none."""
        entry = self._entry(card)
        return list(entry.keys) if entry else []

    def keys_for(self, card: str, at: Optional[datetime.datetime] = None) -> List[str]:
        """The keys valid for *card* at *at* (now when not given): what current mail verifies against."""
        when = at or datetime.datetime.now(datetime.timezone.utc)
        return [k.key for k in self.key_entries(card) if k.valid_at(when)]

    def signing_keys(self, card: str, at: Optional[datetime.datetime] = None) -> List[str]:
        """The keys *card* may sign with at *at*: valid then, and not retired (R45)."""
        when = at or datetime.datetime.now(datetime.timezone.utc)
        return [k.key for k in self.key_entries(card) if k.valid_at(when) and not k.retired]

    def account_of(self, card: str) -> Optional[str]:
        """The account the operator declared as holding *card*'s key, or None."""
        entry = self._entry(card)
        return entry.account if entry else None

    def cards_of_account(self, account: str) -> List[str]:
        """Every card whose key the operator declared as held by *account*. More than one is a
        shared login, which a receiver must see (R46)."""
        return sorted(declared for declared, entry in self.load().agents.items()
                      if entry.account == account)

    def certificates(self) -> List[CertificateEntry]:
        """Each certificate the operator's authority issued, by name, serial and expiry."""
        return list(self.load().certificates)
