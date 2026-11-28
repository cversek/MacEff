"""macf.utils.__all__ names only what the package defines, so a star import works."""
import importlib


def test_every_exported_name_exists():
    utils = importlib.import_module("macf.utils")
    missing = [name for name in utils.__all__ if not hasattr(utils, name)]
    assert missing == []
