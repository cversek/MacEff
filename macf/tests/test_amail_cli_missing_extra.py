"""Without the amail extra, `macf_tools amail ...` says so plainly (cversek/MacEff#843).

The package refuses to import and its message names the install command; the CLI
used to bury that under a traceback chain.
"""
import sys
from unittest.mock import patch

import pytest


def test_amail_without_the_extra_prints_the_remedy_not_a_traceback(capsys):
    from macf.cli import main
    saved = {k: v for k, v in sys.modules.items() if k.startswith("macf.amail")}
    with patch.dict(sys.modules, {"cryptography": None}):
        for name in saved:
            del sys.modules[name]
        try:
            with pytest.raises(SystemExit) as exited:
                main(["amail", "status"])
        finally:
            sys.modules.update(saved)
    assert exited.value.code == 1
    err = capsys.readouterr().err
    assert "pip install 'macf[amail]'" in err
    assert "Traceback" not in err
