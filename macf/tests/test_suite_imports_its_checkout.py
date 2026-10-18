"""The suite tests the source beside it, not whichever checkout the package was installed
from. pytest.ini's pythonpath does this; the test says so loudly where it doesn't hold."""
from pathlib import Path

import macf


def test_the_suite_imports_the_source_beside_it():
    src = Path(__file__).resolve().parents[1] / "src"
    assert Path(macf.__file__).resolve().is_relative_to(src), (
        f"macf was imported from {macf.__file__}, not from {src}, "
        "so this run tests another checkout's code")
