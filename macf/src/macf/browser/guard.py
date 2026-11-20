"""The rules an operator-browser command checks before it acts (MIS-0009 6.2-6.4).

Pure functions over plain values, so they are tested without a browser. Every refusal raises Refused with a
sentence that names the rule, because an agent that can't tell which rule stopped it looks for a way around.
Nothing here is a boundary: the operator's permission rules are (MIS-0009-R39).
"""
import hashlib
import re
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urlparse


class Refused(Exception):
    """A browser act the rules refuse. The message says which rule, and what the operator can do."""


class Unavailable(Exception):
    """The browser capability can't run here (the extra is missing, or no debugging endpoint answers)."""


### irreversible controls (R17, R18)

# Imperative labels that start a control's accessible name. Anchored at the start, with a word boundary, so
# "Deleted Items", "Sender" and "Posting policy" are ordinary controls and "Send", "Delete" and "Post comment" are not.
IRREVERSIBLE = re.compile(
    r"^\s*(send|submit|post|publish|delete|pay|purchase|buy|place order|confirm|accept|approve|request approval|"
    r"sign and submit|unsubscribe)\b", re.I)

# Keyboard chords that send or submit in common web applications, normalized to lowercase "mod+key" form.
IRREVERSIBLE_CHORDS = {"control+enter", "meta+enter", "control+shift+enter", "meta+shift+enter", "alt+s"}


def check_activation(role: str, name: str, operator_said: Optional[str]) -> Optional[str]:
    """Refuse an irreversible control without the operator's words; return the words when they came."""
    if not IRREVERSIBLE.search(name or ""):
        return None
    if not (operator_said or "").strip():
        raise Refused(f"{role} {name.strip()!r} is an irreversible control: it needs the operator's words for "
                      f"this act (--operator-said), and the operator takes it otherwise (MIS-0009-R17)")
    return operator_said.strip()


def _norm_chord(chord: str) -> str:
    return "+".join(part.strip().lower() for part in chord.split("+"))


def check_chord(chord: str, operator_said: Optional[str]) -> Optional[str]:
    """A keyboard shortcut for an irreversible control is that control (R18)."""
    if _norm_chord(chord) not in IRREVERSIBLE_CHORDS:
        return None
    if not (operator_said or "").strip():
        raise Refused(f"the chord {chord} sends or submits in common applications: it needs the operator's "
                      f"words (MIS-0009-R18)")
    return operator_said.strip()


### credentials (R19)

CREDENTIAL_AUTOCOMPLETE = {"current-password", "new-password", "one-time-code", "cc-number", "cc-csc", "cc-exp"}
CREDENTIAL_NAMES = re.compile(r"pass(word|code|phrase)|otp|secret|token|\bpin\b|cvv|cvc", re.I)


def check_fill_target(attrs: dict) -> None:
    """Refuse to type into a password field or a field the page marks for credentials."""
    kind = (attrs.get("type") or "").lower()
    auto = (attrs.get("autocomplete") or "").lower().split()
    named = " ".join(str(attrs.get(k) or "") for k in ("name", "id", "aria-label"))
    if kind == "password" or CREDENTIAL_AUTOCOMPLETE.intersection(auto) or CREDENTIAL_NAMES.search(named):
        raise Refused("this field takes a credential: the person enters credentials, never the agent "
                      "(MIS-0009-R19)")


### host scope and tabs (R05-R07)

def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def host_in_scope(url: str, hosts: Iterable[str]) -> bool:
    """Is the URL's host one of the declared hosts? "*.example.com" also matches its subdomains."""
    host = host_of(url)
    for declared in hosts:
        declared = declared.lower().strip()
        if declared.startswith("*."):
            if host == declared[2:] or host.endswith(declared[1:]):
                return True
        elif host == declared:
            return True
    return False


def tabs_in_scope(tabs: List[dict], hosts: List[str]) -> List[dict]:
    """The tabs whose host is in scope. Titles are never consulted (R06)."""
    if not hosts:
        raise Refused("no host scope: name the hosts this command may touch with --host (MIS-0009-R05)")
    return [t for t in tabs if host_in_scope(t["url"], hosts)]


def select_tab(tabs: List[dict], hosts: List[str], index: Optional[int] = None,
               interact: bool = False) -> Optional[dict]:
    """The tab a command uses. A named tab must be in scope. Unnamed, an interaction uses only a tab the agent
    opened (R07); an observation may read the first tab in scope. None when there is nothing to use."""
    scoped = tabs_in_scope(tabs, hosts)
    if index is not None:
        for t in scoped:
            if t["index"] == index:
                return t
        raise Refused(f"tab {index} is not on a host in scope {hosts} (MIS-0009-R05)")
    candidates = [t for t in scoped if t.get("ours")] if interact else (
        [t for t in scoped if t.get("ours")] or scoped)
    return candidates[0] if candidates else None


### targets, change and navigation (R10, R11, R14)

def check_target(count: int, visible: bool, enabled: bool, what: str) -> None:
    """Act only on one target that is visible and enabled now."""
    if count == 0:
        raise Refused(f"no {what} on the page")
    if count > 1:
        raise Refused(f"{count} matches for {what}: name it more exactly")
    if not visible:
        raise Refused(f"{what} is not visible: hidden elements are never driven (MIS-0009-R10)")
    if not enabled:
        raise Refused(f"{what} is disabled")


def change_report(before: dict, after: dict) -> dict:
    """What an act changed: address, title and visible-text digest, each as [before, after] when different."""
    report = {"changed": False}
    for key in ("url", "title", "digest"):
        if before.get(key) != after.get(key):
            report[key] = [before.get(key), after.get(key)]
            report["changed"] = True
    return report


def check_navigation(fields: List[dict], discard: bool) -> None:
    """Refuse to leave a page whose form holds unsaved input, unless the call discards it."""
    dirty = [f for f in fields if (f.get("value") or "") != (f.get("default") or "")]
    if dirty and not discard:
        raise Refused(f"{len(dirty)} form field(s) hold unsaved input: leaving would lose or post it; "
                      f"say --discard to leave anyway (MIS-0009-R14)")


### capture and downloads (R15, R16, R28)

def check_capture(no_capture: bool) -> None:
    if no_capture:
        raise Refused("this page is marked as showing secrets: no screenshots (MIS-0009-R28)")


def check_destination(dest, agent_home) -> Path:
    """A destination for the operator's files: never inside the agent's home (R16, R27)."""
    dest = Path(dest).expanduser().resolve()
    home = Path(agent_home).expanduser().resolve()
    if dest == home or home in dest.parents:
        raise Refused(f"{dest} is inside the agent's home: the operator's files go elsewhere (MIS-0009-R16)")
    return dest


def save_download(download, dest_dir, agent_home) -> dict:
    """Save a download caught as a browser event into dest_dir, and return its receipt with the sha256."""
    dest_dir = check_destination(dest_dir, agent_home)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(download.suggested_filename or "download").name or "download"
    path = dest_dir / name
    download.save_as(str(path))
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def digest(texts: Iterable[str]) -> str:
    """A short digest of a page's visible text, to tell whether an act changed it."""
    return hashlib.sha256("\n".join(texts).encode()).hexdigest()[:12]
