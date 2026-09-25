"""The version a running checkout reports is the checkout's, not the install's.

An editable install writes its metadata once. A version bump that arrives by git
leaves every hook header and event stamp carrying the old number, plausibly, with
nothing to prompt a reader to doubt it.
"""

import pytest

from macf import _version


def _pyproject(tmp_path, body):
    path = tmp_path / "pyproject.toml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.parametrize("raw, stamped", [("0.6.1-dev", "0.6.1.dev0"), ("0.6.0", "0.6.0")])
def test_a_checkout_reports_its_own_version_spelled_like_the_metadata(tmp_path, raw, stamped):
    path = _pyproject(tmp_path, f'[project]\nname = "macf"\nversion = "{raw}"\n')
    assert _version.checkout_version(path) == stamped


def test_only_this_projects_version_is_read(tmp_path):
    """An unrelated pyproject, or a version key outside [project], is not ours."""
    other = _pyproject(tmp_path, '[project]\nname = "other"\nversion = "9.9.9"\n')
    assert _version.checkout_version(other) is None
    tool_only = _pyproject(tmp_path, '[tool.x]\nversion = "9.9.9"\n[project]\nname = "macf"\n')
    assert _version.checkout_version(tool_only) is None


def test_the_checkout_wins_over_a_stale_install(tmp_path, monkeypatch):
    """The symptom: the install says 0.5.1.dev0, the checkout says 0.6.1-dev."""
    monkeypatch.setattr(_version, "installed_version", lambda: "0.5.1.dev0")
    monkeypatch.setattr(_version, "_CHECKOUT_PYPROJECT",
                        _pyproject(tmp_path, '[project]\nname = "macf"\nversion = "0.6.1-dev"\n'))
    assert _version.resolve_version() == "0.6.1.dev0"

    monkeypatch.setattr(_version, "_CHECKOUT_PYPROJECT", tmp_path / "absent.toml")
    assert _version.resolve_version() == "0.5.1.dev0", "a wheel install lost its only source"


def test_version_names_a_stale_install(monkeypatch, capsys):
    """Corrected silently, a stale install would stay invisible to anything that
    still reads the metadata directly. --version says so instead."""
    from macf import cli
    monkeypatch.setattr(cli, "installed_version", lambda: "0.5.1.dev0")
    monkeypatch.setattr(cli, "_editable_source_suffix", lambda: " (main @ abc1234)")
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    out = capsys.readouterr().out
    assert f"{cli._ver} (main @ abc1234; installed metadata says 0.5.1.dev0)" in out


def test_no_module_keeps_its_own_copy_of_the_lookup():
    """Three copies of the lookup is how the hook headers would have stayed stale
    while the package attribute was fixed. Comparing values cannot catch a copy
    on a machine where the install happens to be current, so check the source:
    only the resolver may ask the installed metadata for this package."""
    import ast
    from pathlib import Path
    root = Path(_version.__file__).parent
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "_version.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            first = node.args[0]
            if name == "version" and isinstance(first, ast.Constant) and first.value == _version.PACKAGE:
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == [], f"a second version lookup: {offenders}"
