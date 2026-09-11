"""Scan a hand-carried bundle before it leaves the host.

The broker scrubs every message that passes through it (see its `_scrub`), so
mail sent by ``amail send`` is gated at the enforcement point. A bundle that a
human zips and carries -- over a chat app, on a stick, in a shared folder --
never touches the broker, and so passes no gate at all. That path is the one
this covers.

It runs the same patterns the broker's scrub runs, from ``macf.opsec``, rather
than a second list. A gate whose vocabulary drifts from the one beside it is
worse than no second gate, because the two disagree and neither says so.

Three outcomes are distinguished, because they need different responses.

A CREDENTIAL finding is key or token material and the bundle must not leave,
full stop.

A CONTEXT finding is private vocabulary -- a framework name, an agent moniker,
an internal task number. Whether that may travel depends entirely on where the
bundle is going, and the tool does not know. Between two agents of this
framework it is the legitimate content of the message; in a bundle bound for a
public repository or a third party it is a leak. So it is reported and does not
block, and `--strict` is how a caller says the destination is foreign.

That separation was not in the first version, and running it against bundles
that had really been carried is what exposed it: every one was refused, over
twenty findings apiece, and not one was a credential. A gate that calls an
agent moniker credential-class is not being careful, it is being wrong, and its
readers learn to skim it -- which costs more than the check was worth.

An UNSCANNABLE file is one this gate could not read -- a PDF, an archive, an
image. That is not a pass; it is an absence of evidence, which the operator
decides about rather than the tool deciding silently.
"""
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

#: Read at most this much of any one file. A credential is small and lives near
#: the top of the files that carry one; a multi-megabyte attachment would
#: otherwise dominate the scan for no gain.
MAX_SCAN_BYTES = 1 << 20


def _entries(target: Path) -> Iterator[Tuple[str, bytes]]:
    """Yield (name, first MAX_SCAN_BYTES) for every file in a directory or zip."""
    if target.is_dir():
        for f in sorted(target.rglob("*")):
            if f.is_file():
                with open(f, "rb") as fh:
                    yield str(f.relative_to(target)), fh.read(MAX_SCAN_BYTES)
        return
    if zipfile.is_zipfile(target):
        with zipfile.ZipFile(target) as z:
            for info in z.infolist():
                if not info.is_dir():
                    with z.open(info) as fh:
                        yield info.filename, fh.read(MAX_SCAN_BYTES)
        return
    raise ValueError(f"not a directory or a zip archive: {target}")


def _is_credential(label: str, secret_labels: set) -> bool:
    """Kept for callers; the shared predicate lives in macf.opsec so every gate agrees."""
    from macf.opsec import is_credential_label
    return label in secret_labels or is_credential_label(label, {"secret_class": []})


def scan_bundle(target: Path, *, profile: Optional[Dict[str, Any]] = None,
                env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Scan every file in a bundle, splitting credential from context findings.

    Findings carry the file and the category and never the matched text, for
    the reason the scanner's own Finding type gives: a refusal travels into
    logs and messages, and a gate that quotes what it caught has moved the
    disclosure into the record of having prevented it.
    """
    from macf.opsec import DEFAULT_PROFILE, compiled_checks, scan_text

    prof = profile if profile is not None else DEFAULT_PROFILE
    secret_labels = set(prof.get("secret_class", []))
    checks = compiled_checks(profile, env)
    credentials: List[Dict[str, Any]] = []
    context: List[Dict[str, Any]] = []
    unscannable: List[str] = []
    scanned = 0
    for name, blob in _entries(target):
        result = scan_text(blob, part=name, checks=checks)
        if result.unscanned:
            unscannable.append(name)
            continue
        scanned += 1
        seen = set()
        for f in result.findings:
            if (f.part, f.label) in seen:
                continue
            seen.add((f.part, f.label))
            row = {"file": f.part, "label": f.label}
            (credentials if _is_credential(f.label, secret_labels) else context).append(row)
    return {"target": str(target), "files_scanned": scanned,
            "files_unscannable": len(unscannable), "unscannable": unscannable,
            "credentials": credentials, "context": context,
            "clean": not credentials and not context and not unscannable}
