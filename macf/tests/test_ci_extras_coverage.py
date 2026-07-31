"""Every dependency the test suite imports must be one CI actually installs.

The motivating gap: `aiohttp` was declared in the `proxy` extra while CI
installed only `[test]`. The proxy tests could therefore never run — on any
branch, ever — and the failure surfaced as an opaque collection error that
read like the fault of whichever pull request happened to touch that area.

Checking at *runtime* ("can I import it?") would not have caught it, because a
developer's machine usually has the package. The check has to compare the
declaration in `pyproject.toml` against the install line in the workflow,
statically, so it fails the same way everywhere.
"""
import ast
import re
import sys
from pathlib import Path

import pytest

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10 — provided by the `test` extra
    import tomli as tomllib

MACF_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = MACF_ROOT / "pyproject.toml"
WORKFLOW = MACF_ROOT.parent / ".github" / "workflows" / "test.yml"

# Imports that are not third-party distributions: the package under test, and
# names resolved from the test tree itself.
LOCAL_ROOTS = {"macf", "conftest", "tests"}


def _installed_extras_from_workflow(text: str) -> set:
    """Extras named in the workflow's editable install of this package.

    Matches e.g. `pip install -e "./macf[test,proxy]"`.
    """
    extras = set()
    for m in re.finditer(r'pip install[^\n]*\[([^\]]+)\]', text):
        extras.update(part.strip() for part in m.group(1).split(","))
    return extras


def _top_level_imports(path: Path) -> set:
    """Top-level module names imported anywhere in a Python file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:  # pragma: no cover
        pytest.fail(f"could not parse {path}: {e}")

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import — local by definition
                continue
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def _module_to_distributions() -> dict:
    """Map top-level module name -> distribution names providing it."""
    from importlib.metadata import packages_distributions
    return packages_distributions()


def test_test_suite_imports_are_covered_by_ci_extras():
    """Fail the build on a dependency CI could never install.

    A test that cannot run is worse than a missing test: the suite reports a
    count that implies coverage it does not have.
    """
    assert PYPROJECT.exists(), f"missing {PYPROJECT}"
    if not WORKFLOW.exists():
        pytest.skip("no CI workflow in this checkout")

    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = config.get("project", {})
    optional = project.get("optional-dependencies", {})

    installed_extras = _installed_extras_from_workflow(
        WORKFLOW.read_text(encoding="utf-8"))
    assert installed_extras, (
        "could not find an extras-bearing `pip install -e` line in the CI "
        "workflow; this check cannot verify coverage without it"
    )

    def _dist_names(specs):
        # "aiohttp>=3.9.0" -> "aiohttp"; normalize for comparison
        return {re.split(r'[<>=!~\[; ]', s, 1)[0].strip().lower().replace("_", "-")
                for s in specs}

    available = _dist_names(project.get("dependencies", []))
    for extra in installed_extras:
        available |= _dist_names(optional.get(extra, []))

    declared_elsewhere = {}
    for extra, specs in optional.items():
        if extra in installed_extras:
            continue
        for dist in _dist_names(specs):
            declared_elsewhere.setdefault(dist, set()).add(extra)

    mod_to_dists = _module_to_distributions()
    stdlib = getattr(sys, "stdlib_module_names", set())

    problems = []
    for test_file in sorted((MACF_ROOT / "tests").glob("*.py")):
        for mod in sorted(_top_level_imports(test_file)):
            if mod in LOCAL_ROOTS or mod in stdlib:
                continue
            dists = {d.lower().replace("_", "-") for d in mod_to_dists.get(mod, [])}
            # A module we cannot attribute to a distribution is out of scope:
            # it is either vendored or not installed here, and the import
            # itself will fail loudly if it matters.
            if not dists:
                continue
            if dists & available:
                continue
            missing_from = sorted(set().union(
                *(declared_elsewhere.get(d, set()) for d in dists)
            )) if any(d in declared_elsewhere for d in dists) else []
            problems.append(
                f"  {test_file.name}: imports `{mod}` (distribution "
                f"{sorted(dists)}) which CI does not install"
                + (f" — it is declared in extra(s) {missing_from}, "
                   f"not in {sorted(installed_extras)}" if missing_from
                   else " — it is not declared in any extra")
            )

    assert not problems, (
        "Tests import dependencies the CI install does not provide, so those "
        "tests can never run in CI:\n" + "\n".join(problems) +
        f"\n\nFix by adding the extra to the workflow's install line "
        f"(currently installs {sorted(installed_extras)}) or by moving the "
        f"dependency into an installed extra."
    )
