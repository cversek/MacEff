"""The Linux outer tier: a systemd user unit per primal daemon (MIS-0002-R03, R04, R06).

Named apart from ``test_pd_render.py``, where the macOS rendering's tests live, so the two
platforms' pull requests do not collide.
"""
import configparser
import json

import pytest

from macf.pd import interface as pdi
from macf.platform import systemd

CARD = "Resident@1a2b3c"
ARGV = ["/usr/bin/python3", "-m", "macf.pd", "/home/resident"]


def _parsed(text):
    parser = configparser.ConfigParser(strict=True, interpolation=None)
    parser.optionxform = str  # systemd keys are case-sensitive
    parser.read_string(text)
    return parser


def test_outer_tier_restarts_pd():
    """MIS-0002-R03: restarted whenever it exits, and never given up on."""
    unit = _parsed(systemd.render_pd_user_unit(CARD, ARGV, "/home/resident")[1])
    assert unit["Service"]["Restart"] == "always"  # clean exits too, not only failures
    # In [Unit], where current systemd reads it; in [Service] it is ignored, and the
    # daemon would stay down after a burst of quick exits.
    assert unit["Unit"]["StartLimitIntervalSec"] == "0"
    assert "StartLimitIntervalSec" not in unit["Service"]


def test_identifier():
    """MIS-0002-R06: the unit is named by the step 1 interface, from the calling card."""
    path, _ = systemd.render_pd_user_unit(CARD, ARGV, "/home/resident")
    assert path == "/home/resident/.config/systemd/user/maceff_pd-Resident_1a2b3c.service"
    assert path.endswith(pdi.systemd_unit(CARD))


def test_the_unit_holds_no_agent_configuration(tmp_path):
    """MIS-0002-R04: no declaration, no environment, nothing but how to start the daemon."""
    declaration = {"version": 1, "agent": "Resident", "units": [
        {"name": "broker", "command": ["amail-broker", "--secret-flag"], "account": "resident",
         "restart": "always", "liveness_interval_s": 15, "memory_limit_mb": 64,
         "environment": {"TOKEN_FILE": "/run/secret"}}]}
    _, text = systemd.render_pd_user_unit(CARD, ARGV, "/home/resident")
    unit = _parsed(text)
    keys = {k for section in unit.sections() for k in unit[section]}
    assert not keys & {"Environment", "EnvironmentFile", "PassEnvironment", "SetCredential", "LoadCredential"}
    for value in ("amail-broker", "--secret-flag", "TOKEN_FILE", "/run/secret", json.dumps(declaration)):
        assert value not in text


@pytest.mark.parametrize("arg,quoted", [
    ("/home/a b/agent", '"/home/a b/agent"'),
    ("50%", "50%%"),
    ("$HOME", '"$$HOME"'),
    ('say "hi"', '"say \\"hi\\""'),
    ("macf.pd", "macf.pd"),
])
def test_exec_start_quotes_what_systemd_would_read_otherwise(arg, quoted):
    """A path with a space must stay one argument, and % and $ must not expand."""
    assert systemd.exec_quote(arg) == quoted
    _, text = systemd.render_pd_user_unit(CARD, ["/usr/bin/python3", arg], "/h")
    assert f"ExecStart=/usr/bin/python3 {quoted}\n" in text


def test_systemctl_verbs_are_closed_and_user_scoped():
    unit = pdi.systemd_unit(CARD)
    assert systemd.systemctl_argv("enable", unit) == ["systemctl", "--user", "enable", "--now", unit]
    assert systemd.systemctl_argv("daemon-reload") == ["systemctl", "--user", "daemon-reload"]
    with pytest.raises(ValueError):
        systemd.systemctl_argv("mask", unit)
    with pytest.raises(ValueError):
        systemd.systemctl_argv("stop")


def test_an_empty_program_is_refused():
    with pytest.raises(ValueError):
        systemd.render_pd_user_unit(CARD, [], "/home/resident")


def test_linger_is_reported_and_an_unreadable_answer_says_so(monkeypatch, capsys):
    """Linger is the operator's switch: read it, never flip it, and never read a failure as no."""
    class Done:
        def __init__(self, out):
            self.stdout, self.stderr = out, ""
    for out, want in (("Linger=yes\n", True), ("Linger=no\n", False), ("", None)):
        monkeypatch.setattr(systemd.subprocess, "run", lambda *a, _o=out, **k: Done(_o))
        assert systemd.linger_enabled("resident") is want

    def missing(*a, **k):
        raise FileNotFoundError("loginctl")
    monkeypatch.setattr(systemd.subprocess, "run", missing)
    assert systemd.linger_enabled("resident") is None
    assert "cannot read linger for resident" in capsys.readouterr().err


def test_linger_reads_a_user_with_no_session_as_no_and_says_when_it_cannot_tell(monkeypatch, capsys):
    import subprocess
    from macf.platform import systemd

    def answer(stdout, stderr, code):
        return lambda *a, **k: subprocess.CompletedProcess(a, code, stdout, stderr)
    monkeypatch.setattr(systemd.subprocess, "run", answer("", "Failed to get user: User ID 65534 is not logged in or lingering\n", 1))
    assert systemd.linger_enabled("nobody") is False
    monkeypatch.setattr(systemd.subprocess, "run", answer("", "Access denied\n", 1))
    assert systemd.linger_enabled("x") is None
    assert "Access denied" in capsys.readouterr().err
