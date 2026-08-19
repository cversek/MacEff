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

import json
from pathlib import Path

from .crypto import SigningError, parse_public_key
from typing import Dict, List, Optional, Tuple


class ContactListError(ValueError):
    """Raised when a contact list is malformed. Never fall back to permissive."""


# Keys that would encode a route rather than an identity.
_ROUTE_KEYS = {"host", "hostname", "transport", "via", "route", "network", "tailnet", "relay"}


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
            raw = json.loads(self.path.read_text())
        except (OSError, ValueError) as e:
            raise ContactListError(f"contact list at {self.path} is unreadable: {e}") from e

        if not isinstance(raw, dict):
            raise ContactListError("contact list must be an object of agent -> [addresses]")

        book: Dict[str, List[str]] = {}
        keys: Dict[Tuple[str, str], List[str]] = {}
        push: Dict[Tuple[str, str], bool] = {}
        for agent, entries in raw.items():
            if not isinstance(entries, list):
                raise ContactListError(f"contacts for '{agent}' must be a list")
            addrs: List[str] = []
            for e in entries:
                if isinstance(e, dict):
                    offending = _ROUTE_KEYS & {k.lower() for k in e}
                    if offending:
                        raise ContactListError(
                            f"contact entry for '{agent}' records reachability "
                            f"({', '.join(sorted(offending))}). A contact names a "
                            "correspondent, never a route — the broker decides how "
                            "to deliver at send time."
                        )
                    if "address" not in e:
                        raise ContactListError(f"contact entry for '{agent}' has no address")
                    addr = str(e["address"]).strip().lower()
                    addrs.append(addr)
                    # `in`, not `or`. `e.get("key") or e.get("keys")` collapses
                    # every falsy value — "", null, 0, false, [] — to None, so a
                    # contact that DECLARED a key silently became keyless and the
                    # explicit "must be a non-empty list" guard below was
                    # unreachable. That downgrades SUSPECT to UNVERIFIED for that
                    # correspondent by configuration rather than by evidence,
                    # which is the one direction this module must never move in.
                    has_key = "key" in e or "keys" in e
                    declared = e.get("key", e.get("keys"))
                    if has_key:
                        if isinstance(declared, str):
                            declared = [declared]
                        if not isinstance(declared, list) or not declared or \
                                not all(isinstance(x, str) and x.strip() for x in declared):
                            raise ContactListError(
                                f"contact key for '{addr}' must be a string or a "
                                "non-empty list of strings")
                        for k in declared:
                            if not isinstance(k, str):
                                raise ContactListError(
                                    f"contact key for '{addr}' must be a string")
                            # Parsed at LOAD, not at first use. A malformed key
                            # discovered while classifying a message would leave
                            # the classifier deciding what to do about broken
                            # configuration, in the middle of a security
                            # decision. Refusing here means a deployment learns
                            # its config is wrong when it writes it.
                            try:
                                parse_public_key(k)
                            except SigningError as ex:
                                raise ContactListError(
                                    f"contact key for '{addr}' is unusable: {ex}"
                                ) from ex
                        keys[(agent, addr)] = list(declared)
                    # push-wake grant. Validated at LOAD
                    # like the keys, and for the same reason: a malformed
                    # grant discovered mid-authorization would put broken
                    # configuration inside a security decision. Whether the
                    # ADDRESS may hold the grant at all is the inbound
                    # module's derivation (agent-namespace check) -- this
                    # layer only guarantees the field is an honest boolean.
                    if "push" in e:
                        if not isinstance(e["push"], bool):
                            raise ContactListError(
                                f"contact 'push' for '{addr}' must be a boolean, "
                                f"got {type(e['push']).__name__}")
                        push[(agent, addr)] = e["push"]
                elif isinstance(e, str):
                    addrs.append(e.strip().lower())
                else:
                    raise ContactListError(f"contact entry for '{agent}' must be a string or object")
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
