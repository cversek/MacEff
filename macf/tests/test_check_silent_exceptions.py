"""The pre-commit check for silent exception handling.

A handler that cleans up and re-raises swallows nothing, and `except
BaseException:` is the right catch for it, since a partial write must be undone
whatever interrupted it. The check used to flag that idiom as a bare catch, so
any commit touching a file that uses it was refused. These tests pin both
halves: the idiom passes, and every handler that can still fall through
silently is flagged.

The samples are lists of quoted lines, because the check reads files line by
line and would otherwise find its own samples in this file.
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_silent_exceptions.py"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("check_silent_exceptions", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _flags(checker, tmp_path, lines):
    f = tmp_path / "sample.py"
    f.write_text("\n".join(lines) + "\n")
    return [reason for _, _, reason in checker.check_file(str(f))]


def test_cleanup_then_reraise_is_not_silent(checker, tmp_path):
    assert _flags(checker, tmp_path, [
        "def write(path, data):",
        "    try:",
        "        path.write_text(data)",
        "    except BaseException:",
        "        try:",
        "            path.unlink()",
        "        except OSError:",
        "            pass",
        "        raise",
    ]) == []


def test_cleanup_without_the_reraise_is_still_flagged(checker, tmp_path):
    assert _flags(checker, tmp_path, [
        "def write(path, data):",
        "    try:",
        "        path.write_text(data)",
        "    except BaseException:",
        "        path.unlink()",
    ]) == ["bare catch without binding"]


def test_a_raise_only_on_one_branch_is_still_flagged(checker, tmp_path):
    """The raise is the handler's last line but not its last statement: when
    `strict` is false the handler falls through silently."""
    assert _flags(checker, tmp_path, [
        "def write(path, data, strict):",
        "    try:",
        "        path.write_text(data)",
        "    except Exception:",
        "        path.unlink()",
        "        if strict:",
        "            raise",
    ]) == ["bare catch without binding"]


def test_swallowing_and_unused_bindings_are_still_flagged(checker, tmp_path):
    assert _flags(checker, tmp_path, [
        "try:",
        "    work()",
        "except Exception:",
        "    pass",
        "try:",
        "    work()",
        "except:",
        "    pass",
        "try:",
        "    work()",
        "except (OSError, ValueError) as e:",
        "    pass",
    ]) == ["bare catch without binding", "bare catch without binding",
           "'e' bound but never used in except body"]
