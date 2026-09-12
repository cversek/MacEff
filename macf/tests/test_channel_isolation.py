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


def _configured_home(tmp_path, monkeypatch):
    """A HOME whose user-level channel dir holds a token and a chat id.

    Project-level resolution is pointed at nothing so the user tier is the one
    under test. The values are fakes; nothing here can reach the network.
    """
    home = tmp_path / "home"
    d = home / ".claude" / "channels" / "telegram"
    d.mkdir(parents=True)
    (d / ".env").write_text("TELEGRAM_BOT_TOKEN=000000:fake-token-for-the-fixture\n")
    (d / "access.json").write_text('{"allowFrom": ["123456"]}\n')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("macf.utils.paths.find_project_root", lambda: None, raising=True)
    return home


@pytest.mark.live_telegram_config
def test_env_guard_refuses_even_when_files_resolve(tmp_path, monkeypatch):
    """The environment layer alone is enough: files present, resolver real, still None."""
    _configured_home(tmp_path, monkeypatch)
    monkeypatch.setenv("MACF_CHANNELS_DISABLED", "1")
    assert telegram.channels_disabled()
    assert telegram.resolve_telegram_config() is None, (
        "MACF_CHANNELS_DISABLED was set and the resolver still returned "
        "credentials -- a subprocess spawned by a test would message a person"
    )


@pytest.mark.live_telegram_config
def test_resolution_works_when_the_guard_is_absent(tmp_path, monkeypatch):
    """The positive polarity: with the guard unset, configured files resolve.

    Without this the test above proves nothing -- a resolver broken outright
    would pass it too.
    """
    _configured_home(tmp_path, monkeypatch)
    monkeypatch.delenv("MACF_CHANNELS_DISABLED", raising=False)
    assert not telegram.channels_disabled()
    assert telegram.resolve_telegram_config() == ("000000:fake-token-for-the-fixture", "123456")


@pytest.mark.live_telegram_config
@pytest.mark.parametrize("value,disabled", [
    ("1", True), ("true", True), ("yes", True), ("anything", True),
    ("0", False), ("false", False), ("no", False), ("", False),
])
def test_guard_value_vocabulary(monkeypatch, value, disabled):
    monkeypatch.setenv("MACF_CHANNELS_DISABLED", value)
    assert telegram.channels_disabled() is disabled


def test_every_test_inherits_the_guard_in_its_environment():
    """The fixture sets the variable, so children of any test inherit it."""
    import os
    assert os.environ.get("MACF_CHANNELS_DISABLED") == "1"


_CHILD = (
    "import json, sys\n"
    "from macf.channels.telegram import resolve_telegram_config\n"
    "print(json.dumps(resolve_telegram_config()))\n"
)


def _resolve_in_a_child(env):
    """Run the resolver in a fresh interpreter, the way a spawned hook would."""
    import os, subprocess, sys, json
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src"
    env = dict(env)
    env["PYTHONPATH"] = str(src) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, "-c", _CHILD], env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


@pytest.mark.live_telegram_config
def test_the_guard_crosses_the_subprocess_boundary(tmp_path, monkeypatch):
    """The failure this whole module exists for: a CHILD process.

    The in-process patch cannot reach a spawned interpreter; only the
    environment can. Both polarities in the child: configured files resolve
    when the variable is absent, and do not when it is set.
    """
    import os
    _configured_home(tmp_path, monkeypatch)
    base = {k: v for k, v in os.environ.items() if k != "MACF_CHANNELS_DISABLED"}
    assert _resolve_in_a_child(base) == ["000000:fake-token-for-the-fixture", "123456"], (
        "control failed: a child with configured files and no guard did not resolve"
    )
    assert _resolve_in_a_child({**base, "MACF_CHANNELS_DISABLED": "1"}) is None, (
        "a child inherited MACF_CHANNELS_DISABLED=1 and still resolved credentials"
    )
