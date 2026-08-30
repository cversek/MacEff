"""Fetching a RECEIVED copy, so the criterion reads bytes nobody rendered.

WHY THIS MODULE EXISTS. The outbound authentication criterion is only as good
as the copy it reads, and every reading taken before this arrived as text a
human copied out of a mail client. A client's "view source" is a RENDERING: it
may fold, reorder, or omit without saying so, and the reader cannot tell. That
doubt was raised, filed as a caveat, and then made normative by the peer as a
PROVENANCE requirement -- the copy must be retrieved from a mailbox we control,
read as raw source, and FETCHED BY THE READER rather than relayed or pasted.

This is the fetching half. It is deliberately small and deliberately dull: it
opens a mailbox, takes bytes, and closes. Everything interpretive lives in the
criterion, because a fetcher that also parses is a fetcher whose bugs look like
verdicts.

READ-ONLY, AND THAT IS A PROPERTY RATHER THAN A DEFAULT. Opening a mailbox
read-write and fetching a body sets the \\Seen flag, which MUTATES THE THING
BEING MEASURED -- the instrument would alter the evidence every time it read
it, and a second reading would then be of a mailbox the first reading changed.
Both the SELECT and the FETCH are peeking versions for exactly this reason.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


class FetchError(RuntimeError):
    """The copy could not be retrieved. NEVER confused with 'not found'.

    A mailbox that could not be opened and a message that is not in it are
    different facts: the first says nothing about the message and the second
    is evidence about it. Collapsing them would let an outage read as a
    missing message, which is the silent-empty this project keeps finding.
    """


class NotFound(FetchError):
    """The mailbox opened and the message is not in it. A real observation."""


@dataclass
class ImapCredential:
    """Host, user and secret. All three required, and `complete` exists for the
    same reason it does on the submission credential: a partial one is truthy,
    passes a naive check, and then fails at the far side where the diagnosis is
    somebody else's log."""

    host: str = ""
    user: str = ""
    password: str = ""

    @property
    def complete(self) -> bool:
        return bool(self.host and self.user and self.password)

    def __repr__(self) -> str:
        # NEVER the secret. This lands in tracebacks, which is precisely where
        # a password must not be.
        return (f"ImapCredential(host={self.host!r}, user={self.user!r}, "
                f"password=<{len(self.password)} chars>, complete={self.complete})")


def read_imap_credential(path: Optional[Path]) -> ImapCredential:
    """Read at FETCH time, from disk, every time -- never cached.

    Same rule and same reasoning as the submission credential: a cached secret
    outlives the file it came from, so rotating or pulling it during an
    incident would leave the reader still using the old one while the custody
    check that would have objected has already run.
    """
    if path is None:
        raise FetchError("no IMAP credential path configured; nothing to fetch with")
    try:
        text = Path(path).read_text()
    except OSError as e:
        print(f"⚠️ MACF: the IMAP credential could not be read ({e}); no "
              f"received copy can be fetched", file=sys.stderr)
        raise FetchError(f"IMAP credential unreadable: {e}") from e

    fields: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")  # noqa: MACEFF005 - str.partition's (before, sep, after) contract is fixed by the stdlib; there is no callee whose order can change
        fields[k.strip().upper()] = v.strip().strip("\"'")
    cred = ImapCredential(fields.get("IMAP_HOST", ""), fields.get("IMAP_USER", ""),
                          fields.get("IMAP_PASSWORD", ""))
    if not cred.complete:
        missing = [n for n, v in (("IMAP_HOST", cred.host), ("IMAP_USER", cred.user),
                                  ("IMAP_PASSWORD", cred.password)) if not v]
        raise FetchError(
            f"the IMAP credential is INCOMPLETE: {', '.join(missing)} absent or "
            f"empty. Naming which half is missing is the whole diagnostic; "
            f"'invalid credential' would send the reader to the wrong file.")
    return cred


def fetch_raw(correlation: str, credential: ImapCredential, *,
              mailbox: str = "INBOX", client_factory: Optional[Any] = None) -> bytes:
    """The raw bytes of one received copy, found by a CORRELATION TOKEN.

    THE FIRST VERSION KEYED ON OUR MESSAGE-ID AND THAT WAS WRONG, measured on
    the first real fetch. The reasoning read well -- the broker mints the
    message-id and the ledger records it, so the fetch and the record would be
    about the same object by construction -- and it rested on an assumption
    nobody checked: that our id appears in the copy that arrives.
    IT DOES NOT. The submission carries four fields and no headers, so the
    SENDING PROVIDER mints the RFC message-id. Searching a real mailbox for our
    internal id returns nothing at all.

    So the correlation key must be a value WE place in a field WE control and
    that SURVIVES to the receiver. The subject does; the caller puts the
    ledger's message-id in it, and this searches for that. The tie back to the
    record is then explicit rather than structural, which is weaker and is
    what is actually available -- saying so is better than a docstring that
    claims a guarantee the transport cannot give.

    THE SEARCH VALUE IS QUOTED. Unquoted multi-word criteria draw a BAD
    response from the server -- the first real search failed on exactly that,
    and a criterion the server cannot parse fails as a protocol error rather
    than as "not found", which is the distinction this module exists to keep.

    `client_factory` is injected so the SEQUENCE can be tested without a
    network. It is not a substitute for running against a real mailbox, and
    that distinction is the whole reason this module exists -- the two defects
    above were both invisible to a suite that was green.
    """
    if not credential or not credential.complete:
        raise FetchError("no complete IMAP credential; refusing to open a mailbox")

    if client_factory is None:
        import imaplib
        client_factory = lambda host: imaplib.IMAP4_SSL(host)  # noqa: E731

    # THE CONNECTION IS MADE INSIDE THE TRY. It was outside, so a refused
    # connection escaped as a raw OSError -- a caller catching FetchError
    # would have missed an outage entirely, and the one failure this module
    # exists to distinguish from absence would have crashed instead of being
    # reported. Found by the test for that distinction.
    client = None
    try:
        client = client_factory(credential.host)
        client.login(credential.user, credential.password)
        # READONLY: selecting read-write and fetching would set \Seen and
        # mutate the mailbox being measured.
        client.select(mailbox, readonly=True)
        typ, data = client.search(None, 'HEADER', 'Subject',
                                  '"%s"' % correlation.replace('"', ''))
        if typ != "OK" or not data or not data[0]:
            raise NotFound(
                f"no message carrying {correlation!r} in {mailbox!r}. The "
                f"mailbox opened and the message is not in it, which is an "
                f"observation about the message rather than about the fetch.")
        num = data[0].split()[0]
        # BODY.PEEK[] rather than RFC822: RFC822 sets \Seen. The peeking form
        # is what makes this instrument non-destructive.
        typ, parts = client.fetch(num, "(BODY.PEEK[])")
        if typ != "OK" or not parts or not parts[0]:
            raise FetchError(f"the message was found and could not be read back")
        raw = parts[0][1]
        if not isinstance(raw, (bytes, bytearray)):
            raise FetchError("the mailbox returned something that is not bytes; "
                             "refusing to guess at an encoding for evidence")
        return bytes(raw)
    except (NotFound, FetchError):
        raise
    except Exception as e:  # noqa: BLE001 - see docstring on FetchError
        # Any other failure is a FETCH failure, never a statement about the
        # message. Collapsing the two would let an outage read as absence.
        raise FetchError(f"could not fetch from {credential.host}: "
                         f"{type(e).__name__}: {e}") from e
    finally:
        try:
            if client is not None:
                client.logout()
        except Exception:  # noqa: BLE001 - a failed logout must not mask a result
            pass
