"""Contact lists — who an agent is permitted to send to.

Two rules from the amail policy are enforced here rather than documented:

1. A contact entry names a correspondent and NEVER records how to reach one.
   Reachability is runtime state; encoding it in configuration means every
   topology change becomes an edit to every contact list, and guarantees drift.
   Any entry carrying a host/transport hint is rejected at load.

2. Changes take effect without a rebuild — the list is read from disk per
   decision, not cached at process start.

What this does NOT control is as important as what it does: it bounds the
RECIPIENT SET, not the content. An agent induced to disclose something can still
disclose it to a permitted correspondent.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import (BaseModel, ConfigDict, ValidationError, field_validator,
                      model_validator)

from .crypto import SigningError, parse_public_key
from typing import Any, Dict, List, Optional, Tuple, Union


class ContactListError(ValueError):
    """Raised when a contact list is malformed. Never fall back to permissive."""


# Keys that would encode a route rather than an identity.
_ROUTE_KEYS = {"host", "hostname", "transport", "via", "route", "network", "tailnet", "relay"}


class ContactEntry(BaseModel):
    """One correspondent an agent may write to.

    Fields:
        address  the correspondent's address; normalised to lowercase.
        key      Ed25519 public key, or a list of them. A bare string is
                 accepted for the single-key case.
        keys     alias for `key`; at most one of the two may be given.
        push     push-wake grant. Whether the address may hold the grant at
                 all is the inbound module's derivation; this layer only
                 guarantees the field is a boolean.

    Unknown fields are rejected. In an authorisation file a misspelled key
    would otherwise read as authorised and silently not be.
    """

    model_config = ConfigDict(extra="forbid")

    address: str
    key: Optional[Union[str, List[str]]] = None
    keys: Optional[Union[str, List[str]]] = None
    push: Optional[bool] = None
    #: Free text, ignored by every consumer. Declared rather than allowed by
    #: laxness so that a misspelled `notes:` is still refused.
    note: Optional[str] = None

    @model_validator(mode="after")
    def _declared_null_is_not_absent(self):
        """A field written as `null` is DECLARED, and must not read as absent.

        `Optional[...] = None` cannot tell "not provided" from "provided as
        null" — both arrive as None. For `key` that difference is
        security-relevant: a declared-but-null key read as keyless moves a
        correspondent from SUSPECT to UNVERIFIED by configuration rather than by
        evidence. `model_fields_set` carries what the file actually wrote.
        """
        for field in ("key", "keys"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(
                    f"contact '{self.address}' declares '{field}' as null. "
                    f"Omit it to mean 'no key'; null means a key was intended "
                    f"and is missing.")
        return self

    @field_validator("address")
    @classmethod
    def _normalise_address(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not v:
            raise ValueError("contact entry has an empty address")
        return v

    @field_validator("key", "keys")
    @classmethod
    def _declared_keys_are_usable(cls, v):
        """Normalise to a list and reject unusable key material.

        Parsed here rather than at first use: a malformed key found while
        classifying a message would put broken configuration inside a security
        decision. A declared-but-empty key is an error, not "keyless" — the two
        mean different things to the classifier.
        """
        if v is None:
            return v
        declared = [v] if isinstance(v, str) else v
        if not declared or not all(isinstance(x, str) and x.strip() for x in declared):
            raise ValueError(
                "contact key must be a string or a non-empty list of strings")
        for k in declared:
            try:
                parse_public_key(k)
            except SigningError as ex:
                raise ValueError(f"contact key is unusable: {ex}") from ex
        return declared

    @classmethod
    def reject_routes(cls, raw: Dict[str, Any], agent: str) -> None:
        """Refuse an entry carrying reachability, with a reason.

        `extra="forbid"` would refuse these anyway, but as "unknown field",
        which does not tell the deployer what to do instead.
        """
        offending = _ROUTE_KEYS & {k.lower() for k in raw}
        if offending:
            raise ContactListError(
                f"contact entry for '{agent}' records reachability "
                f"({', '.join(sorted(offending))}). A contact names a "
                "correspondent, never a route — the broker decides how "
                "to deliver at send time.")


class ContactBook:
    """Per-agent contact lists, loaded fresh on every check."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._cache: Optional[Tuple[Tuple[int, int, int], Any]] = None

    def _load(self) -> Dict[str, List[str]]:
        return self._load_full()[0]

    def _load_full(self) -> Tuple[Dict[str, List[str]], Dict[Tuple[str, str], List[str]], Dict[Tuple[str, str], bool]]:
        """Parsed fresh whenever the FILE changes, not once per process.

        v1.1 moved Ed25519 key parsing inside this function, which is re-entered
        once or twice per recipient — so cost became O(recipients x keys in the
        whole deployment), and the REFUSAL path, the one an attacker can trigger
        at will, was the more expensive of the two. That inverts the rule an
        earlier round established: authorisation must precede the expensive work.

        The cache key is (inode, mtime_ns, size), so an edit takes effect
        immediately and the policy's "changes take effect without a rebuild"
        still holds. Caching on process start would break it; caching on
        identity does not.
        """
        try:
            st = self.path.stat()
            stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
        except OSError:
            stamp = None
        if stamp is not None and self._cache is not None and self._cache[0] == stamp:
            return self._cache[1]
        parsed = self._parse()
        if stamp is not None:
            self._cache = (stamp, parsed)
        return parsed

    def _parse(self) -> Tuple[Dict[str, List[str]], Dict[Tuple[str, str], List[str]], Dict[Tuple[str, str], bool]]:
        if not self.path.exists():
            # Fail closed. An absent contact list is not an empty restriction;
            # it means the deployment is not configured, and sending under that
            # condition is exactly what the allowlist exists to prevent.
            raise ContactListError(
                f"contact list not found at {self.path} — refusing to send with no policy"
            )
        try:
            raw = yaml.safe_load(self.path.read_text())
        except (OSError, yaml.YAMLError) as e:
            raise ContactListError(f"contact list at {self.path} is unreadable: {e}") from e

        if not isinstance(raw, dict):
            raise ContactListError("addressing config must be a mapping")

        # Contacts are nested under the agent they belong to, in the addressing
        # config. A separate file keyed by the same agent names could disagree
        # with the one that defines those agents.
        agents = raw.get("agents")
        if not isinstance(agents, dict):
            raise ContactListError(
                f"{self.path} has no 'agents' mapping — refusing to send with "
                f"no policy")

        book: Dict[str, List[str]] = {}
        keys: Dict[Tuple[str, str], List[str]] = {}
        push: Dict[Tuple[str, str], bool] = {}
        for agent, spec in agents.items():
            if not isinstance(spec, dict):
                raise ContactListError(f"agent '{agent}' must be a mapping")
            entries = spec.get("contacts", [])
            if not isinstance(entries, list):
                raise ContactListError(f"contacts for '{agent}' must be a list")
            addrs: List[str] = []
            for e in entries:
                if isinstance(e, dict):
                    # Reachability gets its own message ahead of the schema's
                    # generic unknown-field error, which would not say what to
                    # do instead.
                    ContactEntry.reject_routes(e, agent)
                    try:
                        entry = ContactEntry.model_validate(e)
                    except ValidationError as ex:
                        raise ContactListError(
                            f"contact entry for '{agent}' is invalid: {ex}") from ex
                    if entry.key is not None and entry.keys is not None:
                        raise ContactListError(
                            f"contact entry for '{entry.address}' declares both "
                            f"'key' and 'keys'; use one")
                    addr = entry.address
                    addrs.append(addr)
                    # Absent and present-but-empty are different facts: a
                    # declared-but-empty key is rejected by the validator rather
                    # than read as keyless, which would move a correspondent
                    # from SUSPECT to UNVERIFIED by configuration instead of by
                    # evidence.
                    declared = entry.key if entry.key is not None else entry.keys
                    if declared is not None:
                        # Scoped by (agent, address), never address alone: two
                        # agents may know the same correspondent under different
                        # keys, and merging would let one agent's contact list
                        # decide what another agent is willing to believe.
                        keys[(agent, addr)] = list(declared)
                    # PUSH-WAKE GRANT: permits this correspondent's inbound mail
                    # to WAKE the recipient agent, rather than waiting to be
                    # collected on the agent's next cycle. Default is no grant;
                    # exceptions are rare and deliberate.
                    #
                    # THE RISK IS INSIDE THE ALLOWLIST, NOT OUTSIDE IT. A
                    # stranger cannot abuse this — a stranger is not a contact.
                    # The case this bounds is two AGENTS who can wake each other:
                    # every individual wake is authorised, and the aggregate is a
                    # self-sustaining loop that no human is watching and that
                    # nothing in a per-message authorisation check can see. An
                    # allowlist bounds WHO may communicate; it does not bound the
                    # DYNAMICS between two parties who are both permitted.
                    #
                    # TODO: the wake mechanism is SPECIFIED-NOT-BUILT (V9/V10,
                    # the separate inbound gate). The field is recorded and
                    # carried; nothing consumes it yet. A reader must not infer
                    # from its presence that waking works today.
                    #
                    # This layer only guarantees the field is an honest boolean.
                    # Whether an address may hold the grant at all is the inbound
                    # module's derivation (the agent-namespace check).
                    if entry.push is not None:
                        push[(agent, addr)] = entry.push
                elif isinstance(e, str):
                    addrs.append(e.strip().lower())
                else:
                    raise ContactListError(
                        f"contact entry for '{agent}' must be a string or a mapping")
            book[agent] = addrs
        return book, keys, push

    def contacts_for(self, agent: str) -> List[str]:
        return self._load().get(agent, [])

    def keys_for(self, agent: str, correspondent: str) -> List[str]:
        """Public keys this agent has declared for that correspondent.

        Empty means "no key declared", which is a different fact from "the key
        did not verify" and the classifier treats them differently. Keyed by
        (agent, address) rather than by address alone: two agents may know the
        same correspondent under different keys, and merging them would let one
        agent's contact list decide what another agent is willing to believe.
        """
        _, keys, _ = self._load_full()
        return keys.get((agent, (correspondent or "").strip().lower()), [])

    def push_granted(self, agent: str, correspondent: str) -> bool:
        """True when the contacts file grants push-wake for this correspondent.

        A GRANT, not an eligibility: whether the address may hold the grant at
        all is the inbound module's derivation (agent-namespace check, audit
        backstop), which runs at every decision. Read per-decision like
        everything else here, so revoking push takes effect without a restart.
        """
        _, _, push = self._load_full()
        return push.get((agent, (correspondent or "").strip().lower()), False)

    def push_grants(self) -> Dict[Tuple[str, str], bool]:
        """Every (agent, address) push grant in the file, for boot/derivation
        sweeps -- the inbound module's refuse-to-start check needs the full
        set, not one lookup."""
        _, _, push = self._load_full()
        return dict(push)

    def permits(self, agent: str, recipient: str) -> bool:
        """True when `agent` may send to `recipient`.

        Case-insensitive on the address, because mail addresses are, and a
        restriction that can be stepped around by capitalising a letter is not one.
        """
        return recipient.strip().lower() in self.contacts_for(agent)

    def refuse_reason(self, agent: str, recipient: str) -> Optional[str]:
        """None when permitted; otherwise a message the agent can act on.

        Refusals are returned rather than swallowed: an agent that cannot tell a
        message was refused learns to believe mail was delivered.
        """
        if self.permits(agent, recipient):
            return None
        known = self.contacts_for(agent)
        if not known:
            return f"'{agent}' has no contacts declared; every recipient is refused"
        return (
            f"'{recipient}' is not in the contact list for '{agent}' "
            f"({len(known)} permitted)"
        )
