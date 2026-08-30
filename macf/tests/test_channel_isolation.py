#!/usr/bin/env python3
"""The channel-isolation fixture is itself under test.

GH #330. An isolation fixture is a control, and a control nobody has watched
fail is a painted bulb. These two tests exist because the previous isolation
looked complete from the outside while covering one of two paths to the live
channel -- and the suite was green throughout.

Both polarities are required and neither suffices alone. The first test alone
would pass if the fixture broke Telegram config resolution permanently, which is
not isolation but breakage. The second alone would pass if the fixture did
nothing at all, since the credentials would resolve either way.
"""

import pytest

from macf.channels import telegram


def test_live_credentials_are_refused_by_default():
    """No test reaches live Telegram credentials without asking."""
    assert telegram.resolve_telegram_config() is None, (
        "a test resolved live Telegram credentials -- the isolation fixture is "
        "not covering this path, and hooks invoked from tests will message a "
        "real person"
    )


@pytest.mark.live_telegram_config
def test_the_opt_out_marker_actually_restores_resolution():
    """The escape hatch works, so the refusal above is discrimination.

    Asserts only that the REAL function runs, not that it finds credentials: a
    machine with no channel configured legitimately returns None here, and
    demanding a token would make this fail on every clean checkout and in CI.
    What is being proven is that the marker removes the patch.
    """
    assert telegram.resolve_telegram_config.__module__ == "macf.channels.telegram", (
        "the opt-out marker did not restore the real resolver -- the fixture is "
        "unconditional, so the default-refusal test above proves nothing"
    )
