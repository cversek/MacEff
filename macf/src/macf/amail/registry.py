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
- a card that isn't ``Name_shortid`` (MIS-0002 R165), the same card twice in any case, an entry
  without its account or its keys, or a key that isn't ``ed25519:<base64>``;
- a certificate entry with anything but ``name``, ``serial`` and ``not_after``, so no key or secret
  can be filed there by mistake.

Lookups compare cards without regard to case (MIS-0002 R164). The file is read per call, so an
edit takes effect at the next decision, as the contact list does.

Format (YAML)::

    agents:
      ExampleAgent_0a1b2c:
        account: exampleagent_0a1b2c
        keys: ["ed25519:<base64>"]
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
from typing import Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from macf import calling_card

from .crypto import SigningError, parse_public_key

#: Where a system's registry lives unless the deployment declares another path.
DEFAULT_PATH = Path("/etc/maceff/registry.yaml")


class RegistryError(ValueError):
    """The registry can't be trusted or read. Never fall back to the agent's own declarations."""


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentEntry(_Closed):
    account: str = Field(min_length=1, max_length=64)
    keys: List[str] = Field(min_length=1)

    @field_validator("keys")
    @classmethod
    def _keys_parse(cls, keys: List[str]) -> List[str]:
        for k in keys:
            try:
                parse_public_key(k)
            except SigningError as e:
                raise ValueError(str(e)) from e
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

    def keys_for(self, card: str) -> List[str]:
        """The public keys the operator declared for *card*; empty when it declares none."""
        entry = self._entry(card)
        return list(entry.keys) if entry else []

    def account_of(self, card: str) -> Optional[str]:
        """The account the operator declared as holding *card*'s key, or None."""
        entry = self._entry(card)
        return entry.account if entry else None

    def card_of_account(self, account: str) -> Optional[str]:
        """The card whose key the operator declared as held by *account*, or None."""
        for declared, entry in self.load().agents.items():
            if entry.account == account:
                return declared
        return None

    def certificates(self) -> List[CertificateEntry]:
        """Each certificate the operator's authority issued, by name, serial and expiry."""
        return list(self.load().certificates)
