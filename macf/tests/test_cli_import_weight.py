"""The command line builds its parser without the heavy modules.

Every `macf_tools` call used to import pydantic (through the task package and the
roles models) and importlib.metadata (for the version) before it had parsed its
arguments: about 86 ms of a trivial command's 240. They are now imported by the
commands that use them. A fresh interpreter is the only honest place to check,
since the test process has long since imported everything.
"""
import json
import subprocess
import sys

HEAVY = ("pydantic", "macf.task", "macf.roles.models", "importlib.metadata", "macf.hooks")


def _fresh(code):
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_the_parser_builds_without_the_heavy_modules():
    loaded = _fresh("import json, sys, macf.cli as c; c._build_parser(); "
                    f"print(json.dumps([m for m in {HEAVY!r} if m in sys.modules]))")
    assert loaded == [], loaded


def test_the_roles_package_loads_its_models_on_first_use():
    seen = _fresh("import json, sys, macf.roles as r; before = 'pydantic' in sys.modules; "
                  "from macf.roles import Role, RoleStore; from macf.roles.models import ICON_SHELF; "
                  "print(json.dumps([before, 'pydantic' in sys.modules, Role.__name__, RoleStore.__name__, "
                  "ICON_SHELF is r.ICON_SHELF]))")
    assert seen == [False, True, "Role", "RoleStore", True], seen


def test_argparse_looks_up_its_own_strings_once():
    """Each gettext lookup stats the locale directories; the parser made ~5,300."""
    lookups = _fresh(
        "import gettext, json\n"
        "n = [0]\n"
        "real = gettext.gettext\n"
        "def counting(message):\n"
        "    n[0] += 1\n"
        "    return real(message)\n"
        "gettext.gettext = counting\n"
        "import macf.cli as c\n"
        "c._build_parser()\n"
        "print(json.dumps(n[0]))")
    assert lookups < 50, lookups
