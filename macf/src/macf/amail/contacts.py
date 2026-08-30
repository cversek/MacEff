"""Contact lists — who an agent is permitted to correspond with, and which way.

Every entry declares a DIRECTION, so who-may-write-to-me and who-I-may-write-to
are one field rather than two files. Two files keyed by the same agent names can
disagree; a field cannot disagree with itself.

The fourth direction, `neither`, is a REVOCATION RECORD rather than an absence.
Deleting a line says nothing afterwards — a reader cannot tell "never a
correspondent" from "was one, and is not now". A revoked entry states it, and
that turns the record into a detector: nothing in legitimate operation ever
addresses a revoked correspondent, so an attempt against one is a signal that
something is running on stale authority, not merely a refusal to count.

Three rules from the amail policy are enforced here rather than documented:

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

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import (BaseModel, ConfigDict, ValidationError, field_validator,
                      model_validator)

from .crypto import SigningError, parse_public_key
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

#: Which way a contact entry authorises correspondence.
#:
#: `neither` is not "no entry" — it is a correspondent explicitly withdrawn, and
#: it is the reason this is a four-valued field rather than two booleans. Two
#: booleans can both be false, but nothing distinguishes that from an entry
#: nobody has filled in yet.
Direction = Literal["inbound", "outbound", "both", "neither"]

#: Directions that authorise sending TO a correspondent, and receiving FROM one.
_SENDS_TO = {"outbound", "both"}
_ACCEPTS_FROM = {"inbound", "both"}


def normalise_address(value: Optional[str]) -> str:
    """The one way an address becomes a lookup key.

    Mail addresses are case-insensitive, so a restriction that can be stepped
    around by capitalising a letter is not one.

    THIS EXISTS AS A FUNCTION BECAUSE TWO SIDES MUST AGREE. The parse side
    normalises when it builds the keys; every lookup must normalise the same way
    or it misses. A drift between them does not raise — the dict simply has no
    such key — and the miss is not uniformly safe: a lookup that misses makes
    `permits` refuse (fail-closed, merely wrong) but makes `is_revoked` answer
    False, which retires the alert on exactly the correspondent the deployment
    withdrew. One function, so the two sides cannot disagree.
    """
    return (value or "").strip().lower()


@dataclass(frozen=True, kw_only=True)
class ParsedContacts:
    """One parse of the contact file, addressed BY NAME rather than by position.

    Returned instead of a tuple. A tuple couples every caller to the ARITY AND
    ORDER of this function: adding a field breaks each unpacking site, and
    REORDERING two fields of the same type breaks nothing visibly and silently
    swaps their meaning. Neither failure is reported where the change was made.

    This is the same defect the coding standards already name for filesystem
    paths (`.parent.parent.parent` hardcodes structure) and that the policy
    standards name for section-number references — position couples to a shape
    the callee is free to change. Names do not move when the shape does.

    `kw_only` so that CONSTRUCTION is name-based too, not only access. Without
    it the class is a tuple wearing field names: positional construction still
    compiles, still runs, and a dataclass does not check types at runtime — so
    two same-shaped fields could be swapped at the one site that builds this and
    every reader downstream would be confidently wrong. Enforcing the rule on
    the way out while merely expressing it on the way in leaves the hole open at
    the only place it can be introduced.
    """

    #: agent -> every address declared for it, in file order, ALL directions.
    #: Filtering is the caller's question; this is the raw declaration.
    by_agent: Dict[str, List[str]]
    #: (agent, address) -> declared Ed25519 keys
    keys: Dict[Tuple[str, str], List[str]]
    #: (agent, address) -> push-wake grant, only where the file stated one
    push: Dict[Tuple[str, str], bool]
    #: (agent, address) -> declared Direction. Absent means the pair is not in
    #: the file at all, which is a different fact from a declared "neither".
    direction: Dict[Tuple[str, str], str]

    @staticmethod
    def _key(agent: str, correspondent: str) -> Tuple[str, str]:
        """The lookup key for a correspondent OF a given agent.

        Scoped by (agent, address) rather than by address alone: two agents may
        know the same correspondent under different keys and different
        directions, and merging them would let one agent's contact list decide
        what another agent may do.

        Built here rather than at each call site for the reason the whole class
        exists — the key is itself a positional structure, so every site that
        assembles one by hand is coupled to its order and arity.
        """
        return (agent, normalise_address(correspondent))

    def keys_for(self, agent: str, correspondent: str) -> List[str]:
        return self.keys.get(self._key(agent, correspondent), [])

    def push_for(self, agent: str, correspondent: str) -> bool:
        return self.push.get(self._key(agent, correspondent), False)

    def direction_for(self, agent: str, correspondent: str) -> Optional[str]:
        """The declared direction, or None when the pair is not in the file.

        None and "neither" are returned differently ON PURPOSE: "not declared"
        and "declared as withdrawn" are the distinction the fourth value exists
        to carry, and collapsing them here would discard it before any caller
        could act on it.
        """
        return self.direction.get(self._key(agent, correspondent))


class ContactListError(ValueError):
    """Raised when a contact list is malformed. Never fall back to permissive."""


# Keys that would encode a route rather than an identity.
_ROUTE_KEYS = {"host", "hostname", "transport", "via", "route", "network", "tailnet", "relay"}


class ContactEntry(BaseModel):
    """One correspondent an agent may write to.

    Fields:
        address    the correspondent's address; normalised to lowercase.
        direction  REQUIRED. One of inbound / outbound / both / neither —
                   which way correspondence with this address is authorised.
                   `neither` records a withdrawn correspondent and refuses
                   both ways; see the module docstring for why that is a
                   value rather than a deletion.
        key        Ed25519 public key, or a list of them. A bare string is
                   accepted for the single-key case.
        keys       alias for `key`; at most one of the two may be given.
        push       push-wake grant. Whether the address may hold the grant at
                   all is the inbound module's derivation; this layer only
                   guarantees the field is a boolean.

    `direction` has NO DEFAULT, deliberately. Every other field here describes a
    correspondent; this one grants authority, and a default would let an entry
    enter the list without anyone stating what it may do. A permissive default
    would be worse still: it widens authority for every entry that omits the
    field, which is precisely the set nobody considered.

    Unknown fields are rejected. In an authorisation file a misspelled key
    would otherwise read as authorised and silently not be.
    """

    model_config = ConfigDict(extra="forbid")

    address: str
    direction: Direction
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
        return self._load_full().by_agent

    def _load_full(self) -> ParsedContacts:
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

    def _parse(self) -> ParsedContacts:
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
        direction: Dict[Tuple[str, str], str] = {}
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
                    direction[(agent, addr)] = entry.direction
                elif isinstance(e, str):
                    # A bare address cannot state a direction, and direction is
                    # the field that grants authority. Accepting the shorthand
                    # would mean inventing one, which is the permissive default
                    # this schema exists to refuse.
                    raise ContactListError(
                        f"contact entry '{e}' for '{agent}' is a bare address. "
                        f"Write it as a mapping with a 'direction' of inbound, "
                        f"outbound, both or neither — an entry that does not "
                        f"say which way it authorises correspondence is not a "
                        f"policy.")
                else:
                    raise ContactListError(
                        f"contact entry for '{agent}' must be a mapping")
            book[agent] = addrs
        return ParsedContacts(by_agent=book, keys=keys, push=push,
                              direction=direction)

    def contacts_for(self, agent: str, *, direction: str) -> List[str]:
        """Addresses this agent may correspond with IN THE GIVEN DIRECTION.

        `direction` is keyword-only and required: the caller must say which
        question it is asking. The undirected form answered "is this address in
        the list", which is the same answer to two different questions — and the
        separation lived only in a deployment pointing two consumers at two
        files.

        `neither` entries are in the list and appear in no direction, so they are
        refused by the ordinary path without a special case.
        """
        if direction not in ("outbound", "inbound"):
            raise ValueError(
                f"direction must be 'outbound' or 'inbound' to ask this "
                f"question, not {direction!r}")
        allowed = _SENDS_TO if direction == "outbound" else _ACCEPTS_FROM
        parsed = self._load_full()
        return [a for a in parsed.by_agent.get(agent, [])
                if parsed.direction_for(agent, a) in allowed]

    def declared_direction(self, agent: str, correspondent: str) -> Optional[str]:
        """The direction declared for this correspondent, or None if unlisted.

        Distinguishing "declared as `neither`" from "not declared at all" is the
        whole point of the fourth value, so this returns them differently.
        """
        return self._load_full().direction_for(agent, correspondent)

    def is_revoked(self, agent: str, correspondent: str) -> bool:
        """True when this correspondent is explicitly withdrawn.

        Callers should treat a hit as an ALERT rather than an ordinary refusal.
        Legitimate operation never addresses a revoked correspondent, so the
        false-positive rate is near zero by construction — which is what makes
        this worth raising rather than counting. It catches a consumer running
        on a stale allowlist, a replayed former relationship, and a compromised
        component reaching for a correspondent the deployment has cut off.
        """
        return self.declared_direction(agent, correspondent) == "neither"

    def keys_for(self, agent: str, correspondent: str) -> List[str]:
        """Public keys this agent has declared for that correspondent.

        Empty means "no key declared", which is a different fact from "the key
        did not verify" and the classifier treats them differently. Keyed by
        (agent, address) rather than by address alone: two agents may know the
        same correspondent under different keys, and merging them would let one
        agent's contact list decide what another agent is willing to believe.
        """
        return self._load_full().keys_for(agent, correspondent)

    def push_granted(self, agent: str, correspondent: str) -> bool:
        """True when the contacts file grants push-wake for this correspondent.

        A GRANT, not an eligibility: whether the address may hold the grant at
        all is the inbound module's derivation (agent-namespace check, audit
        backstop), which runs at every decision. Read per-decision like
        everything else here, so revoking push takes effect without a restart.
        """
        return self._load_full().push_for(agent, correspondent)

    def push_grants(self) -> Dict[Tuple[str, str], bool]:
        """Every (agent, address) push grant in the file, for boot/derivation
        sweeps -- the inbound module's refuse-to-start check needs the full
        set, not one lookup."""
        return dict(self._load_full().push)

    def permits(self, agent: str, correspondent: str, *, direction: str) -> bool:
        """True when this agent may correspond with this address THAT WAY.

        `direction` is required because the two questions have two answers. The
        undirected form took `recipient` and was called with a SENDER by the
        inbound path — one membership test standing in for both, with the
        separation living only in a deployment that pointed the two consumers at
        two different files.
        """
        return normalise_address(correspondent) in self.contacts_for(
            agent, direction=direction)

    def refuse_reason(self, agent: str, correspondent: str, *,
                      direction: str) -> Optional[str]:
        """None when permitted; otherwise a message the agent can act on.

        Refusals are returned rather than swallowed: an agent that cannot tell a
        message was refused learns to believe mail was delivered.

        A REVOKED correspondent gets its own reason, and that is the point of
        the fourth direction rather than a nicety. "Not in the list" and "was in
        the list and was withdrawn" send a reader to different places: the first
        to add a contact, the second to ask why it was removed and who is still
        trying to reach it. Collapsing them would discard the only signal that
        distinguishes a misconfiguration from a component running on stale
        authority.
        """
        if self.permits(agent, correspondent, direction=direction):
            return None
        if self.is_revoked(agent, correspondent):
            return (
                f"'{correspondent}' is REVOKED for '{agent}' — declared "
                f"'neither', so correspondence is withdrawn in both directions. "
                f"This is a withdrawn contact rather than an unknown one; if it "
                f"is being addressed, something is acting on stale authority.")
        known = self.contacts_for(agent, direction=direction)
        if not known:
            return (f"'{agent}' has no {direction} contacts declared; "
                    f"every correspondent is refused")
        return (
            f"'{correspondent}' is not in the {direction} contact list for "
            f"'{agent}' ({len(known)} permitted)"
        )
