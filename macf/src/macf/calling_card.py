"""The calling card: an agent's name, one underscore, and its short id (MIS-0002-R157 to R166).

Every site that builds a card, reads one, or names something after one asks this module, so the
rules live in one place:

- **The form** (R157 to R159). ``Name_shortid``, capitals kept. The name is one ASCII letter and at
  most 23 more ASCII letters or digits, so it holds no ``_`` or ``-`` and the card's one underscore
  is always the separator. The short id is the first six hexadecimal characters of the agent's
  identity file, in lowercase.
- **Derived names** (R160 to R163). A case-sensitive target that doesn't require lowercase, such
  as a launchd label, a unit name, a path, a socket or a record, takes the card exactly. A target
  that requires lowercase, such as a Unix account or a mail local part, takes the card
  lowercased. A DNS label or certificate DNS name takes the lowercased card with its underscore
  replaced by a hyphen. The name's 24-character cap keeps a lowercased card within a 31-character
  account.
- **Reading a card** (R164 to R166). A card that is declared or configured, as in an identity
  file, a declaration, a configuration file or a newly submitted sender, is compared without
  regard to case, and any other form is refused, ``Name@shortid`` included, with the form expected.
  A reader of stored history maps ``Name@shortid`` to ``Name_shortid`` instead: event logs are
  append-only, and signatures kept under MIS-0004-R45 must still resolve.

Why an underscore: ``@`` keeps its usual meanings (``account@host``, mail) in the systems where
these names are used, and ``_`` is legal in Unix accounts and mail local parts. DNS and TLS names
refuse ``_``, which is why the DNS label has its own rule.
"""
import re
from typing import Optional, Tuple

SEPARATOR = "_"
NAME_MAX = 24
SHORTID_LEN = 6

#: The short id a best-effort identity carries when no identity file could be read. It is not
#: hexadecimal, so it can never be mistaken for a real card.
UNKNOWN = "unknown"

_NAME = r"[A-Za-z][A-Za-z0-9]{0,23}"
_SHORTID = r"[0-9a-f]{6}"
NAME_RE = re.compile(_NAME)
CARD_RE = re.compile(rf"(?P<name>{_NAME})_(?P<shortid>{_SHORTID})")
_OLD_CARD_RE = re.compile(rf"(?P<name>{_NAME})@(?P<shortid>{_SHORTID}|{UNKNOWN})")
_DECLARED_RE = re.compile(rf"(?P<name>{_NAME})_(?P<shortid>{_SHORTID})", re.IGNORECASE)


class CardError(ValueError):
    """A calling card, or a name for one, that doesn't follow the rules. The message says why and
    names the form expected."""


def name_problem(name: str) -> Optional[str]:
    """Why ``name`` can't be a calling card's name, or None when it can (R158)."""
    if not isinstance(name, str) or not name:
        return "a calling card needs a name"
    if NAME_RE.fullmatch(name):
        return None
    if "@" in name or "_" in name:
        return (f"a calling card's name holds no separator: {name!r} contains "
                f"{'@' if '@' in name else '_'}; the card adds its own underscore")
    if len(name) > NAME_MAX:
        return f"a calling card's name is at most {NAME_MAX} characters; {name!r} has {len(name)}"
    return (f"a calling card's name is one ASCII letter followed by at most 23 ASCII letters or "
            f"digits; {name!r} isn't")


def build(name: str, uuid: str) -> str:
    """The card for the agent named ``name`` whose identity file holds ``uuid`` (R157 to R159)."""
    problem = name_problem(name)
    if problem:
        raise CardError(problem)
    shortid = (uuid or "").strip()[:SHORTID_LEN].lower()
    if not re.fullmatch(_SHORTID, shortid):
        raise CardError(f"an identity file must begin with {SHORTID_LEN} hexadecimal characters; "
                        f"{(uuid or '').strip()[:SHORTID_LEN]!r} doesn't")
    return f"{name}{SEPARATOR}{shortid}"


def join(name: str, shortid: str) -> str:
    """A best-effort identity in the card's shape, unchecked: for a fallback name, or the
    ``unknown`` short id, where :func:`build` would refuse. Never use it for a declared card."""
    return f"{name}{SEPARATOR}{shortid}"


def is_card(text: str) -> bool:
    """Whether ``text`` is a calling card in the form (R157 to R159), exactly."""
    return isinstance(text, str) and CARD_RE.fullmatch(text) is not None


def is_unknown(card: Optional[str]) -> bool:
    """Whether ``card`` is the best-effort identity of an agent whose identity file couldn't be
    read, in either spelling: it must never be used to name or sign anything."""
    return bool(card) and (card.endswith(SEPARATOR + UNKNOWN) or card.endswith("@" + UNKNOWN))


def split(card: str) -> Tuple[str, str]:
    """``(name, shortid)`` of a card in the form; :class:`CardError` otherwise."""
    m = CARD_RE.fullmatch(card or "")
    if not m:
        raise CardError(f"{card!r} is not a calling card: expected Name_shortid, one ASCII letter "
                        f"and up to 23 letters or digits, an underscore, and six lowercase "
                        f"hexadecimal characters")
    return m.group("name"), m.group("shortid")


def read_declared(text: str) -> str:
    """A card as declared or configured (R164, R165), returned as written, or :class:`CardError`.

    Case is not part of what is checked, since the comparison that follows ignores it (R164). Any
    other form is refused with the form expected (R165), and the old ``Name@shortid`` is named as
    such, so whoever wrote it knows what to change."""
    t = (text or "").strip()
    old = _OLD_CARD_RE.fullmatch(t)
    if old:
        raise CardError(f"{t!r} is the old calling-card form: write it as "
                        f"{old.group('name')}{SEPARATOR}{old.group('shortid')}")
    if not _DECLARED_RE.fullmatch(t):
        raise CardError(f"{t!r} is not a calling card: expected Name_shortid, for example "
                        f"ExampleAgent_0a1b2c")
    return t


def same(a: str, b: str) -> bool:
    """Whether two cards name the same agent, compared without regard to case (R164)."""
    return (a or "").strip().casefold() == (b or "").strip().casefold()


def from_history(text: str) -> str:
    """A card as stored history spells it, in the current form (R166). ``Name@shortid`` becomes
    ``Name_shortid``; anything else, the current form included, comes back unchanged."""
    m = _OLD_CARD_RE.fullmatch((text or "").strip()) if isinstance(text, str) else None
    return f"{m.group('name')}{SEPARATOR}{m.group('shortid')}" if m else text


def is_agent(stored: object, card: str) -> bool:
    """Whether a card read from stored history, such as an event's ``agent``, names the agent
    whose card is ``card``. The old spelling is mapped (R166) and case is ignored (R164), so a
    daemon keeps its own past across the change: its entries, schedules and states."""
    return isinstance(stored, str) and same(from_history(stored), card)


def derived(card: str) -> str:
    """The name a case-sensitive target that doesn't require lowercase takes from the card: the
    card exactly (R160)."""
    return card


def lowercase(card: str) -> str:
    """The name a lowercase target takes from the card, such as a Unix account or a mail local
    part: the card lowercased, with no other change (R161). A new account is named this way
    (R162); an account that existed before keeps its name."""
    return card.lower()


def dns_label(card: str) -> str:
    """The DNS label or certificate DNS name the card forms: the lowercased card with its
    underscore replaced by a hyphen, and nothing else (R163)."""
    name, shortid = split(card)
    return f"{name.lower()}-{shortid}"
