"""Fetching a received copy, so the criterion reads bytes nobody rendered."""
import pytest

from macf.amail import fetch as F


class _Client:
    """Records what was asked of the mailbox, so the TESTS can assert on the
    non-destructive properties rather than on the bytes coming back."""

    def __init__(self, found=True, raw=b"From: a@b\n\nbody"):
        self.found, self.raw = found, raw
        self.selected = None
        self.readonly = None
        self.fetch_spec = None
        self.logged_out = False

    def login(self, u, p): self.user = u
    def select(self, mailbox, readonly=False):
        self.selected, self.readonly = mailbox, readonly
        return ("OK", [b""])
    def search(self, charset, *criteria):
        return ("OK", [b"7" if self.found else b""])
    def fetch(self, num, spec):
        self.fetch_spec = spec
        return ("OK", [(b"7 (BODY[] {13}", self.raw)])
    def logout(self): self.logged_out = True


CRED = F.ImapCredential("imap.example.test", "reader@example.test", "secret")


def test_the_raw_bytes_come_back():
    c = _Client()
    raw = F.fetch_raw("<m1@ours.test>", CRED, client_factory=lambda h: c)
    assert raw == b"From: a@b\n\nbody"


def test_the_mailbox_is_opened_READ_ONLY():
    """A PROPERTY, NOT A DEFAULT. Selecting read-write and fetching sets the
    \\Seen flag, so the instrument would MUTATE THE THING IT MEASURES and a
    second reading would be of a mailbox the first reading changed."""
    c = _Client()
    F.fetch_raw("<m1@ours.test>", CRED, client_factory=lambda h: c)
    assert c.readonly is True


def test_the_fetch_PEEKS_rather_than_reading():
    """The other half of non-destructive. RFC822 sets \\Seen; BODY.PEEK[] does
    not. Read-only SELECT alone is not enough on every server."""
    c = _Client()
    F.fetch_raw("<m1@ours.test>", CRED, client_factory=lambda h: c)
    assert "PEEK" in c.fetch_spec


def test_a_missing_message_is_NOT_a_fetch_failure():
    """The mailbox opened and the message is not in it: an observation ABOUT
    THE MESSAGE. An outage says nothing about the message. Collapsing the two
    would let an outage read as absence, which is the silent-empty this project
    keeps finding."""
    c = _Client(found=False)
    with pytest.raises(F.NotFound):
        F.fetch_raw("<gone@ours.test>", CRED, client_factory=lambda h: c)


def test_a_broken_mailbox_is_a_fetch_failure_not_an_absence():
    def explode(host): raise OSError("connection refused")
    with pytest.raises(F.FetchError) as e:
        F.fetch_raw("<m1@ours.test>", CRED, client_factory=explode)
    assert not isinstance(e.value, F.NotFound)


def test_an_incomplete_credential_names_the_missing_half(tmp_path):
    p = tmp_path / "imap.cred"
    p.write_text("IMAP_HOST=imap.example.test\nIMAP_USER=reader@example.test\n")
    with pytest.raises(F.FetchError, match="IMAP_PASSWORD"):
        F.read_imap_credential(p)


def test_the_credential_never_prints_its_secret():
    """This object ends up in tracebacks, which is exactly where a password
    must not be."""
    assert "secret" not in repr(CRED)
    assert "6 chars" in repr(CRED)


def test_a_partial_credential_cannot_open_a_mailbox():
    c = _Client()
    with pytest.raises(F.FetchError, match="refusing to open"):
        F.fetch_raw("<m1@ours.test>", F.ImapCredential("h", "u", ""),
                    client_factory=lambda h: c)
    assert c.selected is None, "a mailbox was opened without a complete credential"


def test_the_mailbox_is_closed_even_when_the_fetch_fails():
    c = _Client(found=False)
    with pytest.raises(F.NotFound):
        F.fetch_raw("<gone@ours.test>", CRED, client_factory=lambda h: c)
    assert c.logged_out is True
