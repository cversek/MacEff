"""A supervised session sees the container-wide environment.

``MACEFF_ROOT_DIR`` and ``MACEFF_TZ`` were written only to ``/etc/environment``,
which PAM reads -- for an SSH login or ``su -``, and for nothing else. A
supervised Claude session is started by ``docker exec`` into tmux, never through
PAM, and its Bash tool runs non-login shells whose ``BASH_ENV`` is the agent's
own ``~/.bash_init.sh``. That file exported only per-agent variables, so every
supervised agent ran with ``MACEFF_ROOT_DIR`` unset: ``macf_tools`` warned
"MacEff root not found" and fell back to the current directory.

These tests source the rendered files in a real bash with an empty environment,
which is the only honest reproduction: the defect is about which file a shell
reads, and only a shell can answer that.
"""
import importlib.util
import subprocess
from pathlib import Path

import pytest

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"


@pytest.fixture
def start(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("maceff_start_containerenv", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "run_command", lambda *a, **k: None)
    monkeypatch.setattr(module, "log", lambda *a, **k: None)
    monkeypatch.setattr(module, "HOME_ROOT", tmp_path / "home")
    monkeypatch.setattr(module, "CONTAINER_ENV_SCRIPT", tmp_path / "container-env.sh")
    (tmp_path / "home" / "pa_x").mkdir(parents=True)
    return module


def _shell(home: Path, command: str) -> str:
    """Run a NON-login, non-interactive bash the way the Bash tool does."""
    out = subprocess.run(
        ["bash", "-c", command],
        capture_output=True, text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin",
             "BASH_ENV": str(home / ".bash_init.sh")},
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_container_env_script_carries_the_framework_keys(start):
    text = start.render_container_env_script("America/New_York", {})
    assert "export MACEFF_ROOT_DIR=/opt/maceff" in text
    assert "export MACEFF_TZ=America/New_York" in text


def test_container_env_script_carries_declared_keys_too(start):
    text = start.render_container_env_script(None, {"MACF_AMAIL_DOMAIN": "x.local"})
    assert "export MACEFF_ROOT_DIR=/opt/maceff" in text
    assert "export MACF_AMAIL_DOMAIN=x.local" in text
    assert "MACEFF_TZ" not in text


def test_supervised_shell_sees_the_root(start, tmp_path):
    start.CONTAINER_ENV_SCRIPT.write_text(start.render_container_env_script(None, {}))
    start.create_bash_init("pa_x", "x")
    home = start.HOME_ROOT / "pa_x"
    assert _shell(home, 'echo "${MACEFF_ROOT_DIR:-unset}"') == "/opt/maceff"


def test_nested_shell_sees_the_root(start, tmp_path):
    # .bash_init.sh points BASH_ENV at itself, so a shell started FROM the tool's
    # shell reads only that file. It must still arrive.
    start.CONTAINER_ENV_SCRIPT.write_text(start.render_container_env_script(None, {}))
    start.create_bash_init("pa_x", "x")
    home = start.HOME_ROOT / "pa_x"
    assert _shell(home, "bash -c 'echo \"${MACEFF_ROOT_DIR:-unset}\"'") == "/opt/maceff"


def test_vanilla_account_gets_no_maceff_context(start, tmp_path):
    start.CONTAINER_ENV_SCRIPT.write_text(start.render_container_env_script(None, {}))
    start.create_bash_init("pa_x", "x", vanilla=True)
    home = start.HOME_ROOT / "pa_x"
    assert _shell(home, 'echo "${MACEFF_ROOT_DIR:-unset}"') == "unset"
    assert start.vanilla_home_violations(home) == []


def test_absent_container_env_script_is_harmless(start, tmp_path):
    # A home provisioned before the script exists, or outside a container.
    start.create_bash_init("pa_x", "x")
    home = start.HOME_ROOT / "pa_x"
    assert _shell(home, 'echo "${MACEFF_AGENT_NAME}"') == "x"
