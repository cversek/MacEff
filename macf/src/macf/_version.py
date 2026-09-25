"""The framework's version, as the running code knows it.

The installed metadata is written once, when the package is installed. For a
wheel that is the truth. For an editable install it goes stale the first time a
version bump arrives by ``git pull`` or a branch switch rather than a reinstall:
the code is live, the number is not, and every hook header and event-log stamp
carries the old one. A stamp that is wrong in a plausible way is worse than a
missing one, because nothing prompts a reader to doubt it.

So when this module was imported from a source checkout, the checkout's own
``pyproject.toml`` is read instead. Anything unexpected about that file falls
back to the installed metadata; nothing here raises, because every hook imports
it.
"""

import re
import sys
from importlib.metadata import PackageNotFoundError, version as _dist_version
from pathlib import Path
from typing import Optional

PACKAGE = "macf"

# macf/src/macf/_version.py -> macf/pyproject.toml in a checkout. In a wheel the
# same path lands in the interpreter's lib directory, where the name check below
# rejects whatever is (almost certainly not) there.
_CHECKOUT_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

_KEY = re.compile(r'(name|version)\s*=\s*"([^"]*)"')
_DEV = re.compile(r"[-_.]?dev(\d*)$")


def installed_version() -> str:
    """What the installed metadata says."""
    try:
        return _dist_version(PACKAGE)
    except PackageNotFoundError:
        return "0.0.0-unknown"


def _normalise(raw: str) -> str:
    """Spell a dev version the way installed metadata does: ``0.6.1-dev`` ->
    ``0.6.1.dev0``, so a checkout and a wheel stamp the same string. Dev is the
    only pre-release form this project has used; anything else is returned as
    written rather than guessed at."""
    return _DEV.sub(lambda m: f".dev{m.group(1) or 0}", raw)


def checkout_version(pyproject: Optional[Path] = None) -> Optional[str]:
    """``[project].version`` of the source checkout, or None when there is none.

    Reads two keys from one table, which needs no TOML parser: the standard
    library has none before 3.11 and this project supports 3.10.
    """
    path = pyproject or _CHECKOUT_PYPROJECT
    if not path.is_file():
        return None  # installed from a wheel: no checkout, which is not an error
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        # A checkout whose pyproject cannot be read is a real fault, and the
        # fallback (installed metadata) may be the stale number this module
        # exists to avoid, so say so rather than degrade quietly.
        print(f"⚠️ MACF: could not read {path} for the version, "
              f"using installed metadata: {e}", file=sys.stderr)
        return None

    fields = {}
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if in_project:
            match = _KEY.match(stripped)
            if match:
                fields.setdefault(match.group(1), match.group(2))

    if fields.get("name") != PACKAGE or not fields.get("version"):
        return None
    return _normalise(fields["version"])


def resolve_version() -> str:
    """The checkout's version when running from one, else the installed one."""
    return checkout_version() or installed_version()


VERSION = resolve_version()
