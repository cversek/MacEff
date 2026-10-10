"""preamble-upgrade covers every declared agent, and says what it did to each (issue #388).

It used to upgrade one agent per call, defaulting to a username from common.sh, and a partial
upgrade on a multi-agent container looked exactly like a complete one. The scripts run here
against a stand-in `docker` that answers from a declared agent list and records each
`agent init`, and a stand-in `template-sync`.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "maceff_tools"

DOCKER = r'''#!/usr/bin/env bash
case "$1" in
  inspect) echo true ;;
  exec)
    shift
    if [ "$1" = "-u" ]; then
      user="$2"; echo "$user" >> "$INIT_LOG"
      [ "$user" = "${FAIL_USER:-}" ] && exit 1
      exit 0
    fi
    shift   # the container
    if [ "$1" = "id" ]; then exit 0; fi
    # the enumeration: the full form carries flavors, the preflight's names only
    case "$*" in
      *is_vanilla\ else*) printf '%b' "$AGENTS" ;;
      *) printf '%b' "$AGENTS" | awk -F'\t' '$2=="maceff"{print $1}' ;;
    esac ;;
esac
'''


@pytest.fixture
def tools(tmp_path):
    d = tmp_path / "maceff_tools"
    d.mkdir()
    for name in ("preamble-upgrade", "preamble-upgrade.preflight", "common.sh", "framework-upgrade"):
        shutil.copy2(TOOLS / name, d / name)
    for name in ("template-sync", "policy-sync", "assets-sync"):
        (d / name).write_text("#!/usr/bin/env bash\necho synced\n")
        (d / name).chmod(0o755)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "docker").write_text(DOCKER)
    (bin_ / "docker").chmod(0o755)
    log = tmp_path / "init.log"
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", INIT_LOG=str(log), CONTAINER_NAME="c",
               AGENTS="manny\\tmaceff\\nmanny2\\tmaceff\\nvisitor\\tvanilla\\n")
    env.pop("PA", None)

    def run(*args, script="preamble-upgrade", **extra):
        r = subprocess.run([str(d / script), *args], env={**env, **extra}, capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, timeout=60)
        inits = log.read_text().split() if log.exists() else []
        return r, inits
    return run


def test_all_agents_upgrades_every_declared_maceff_agent_and_names_each(tools):
    r, inits = tools("--all-agents", "--confirm-all-agents")
    assert r.returncode == 0, r.stderr
    assert inits == ["manny", "manny2"]
    assert "upgraded: manny\n" in r.stdout and "upgraded: manny2\n" in r.stdout
    assert "skipped:  visitor (vanilla)" in r.stdout
    assert "Preambles: 2 upgraded, 0 failed, 1 vanilla skipped." in r.stdout


def test_one_failure_does_not_stop_the_rest_and_is_named(tools):
    r, inits = tools("--all-agents", "--confirm-all-agents", FAIL_USER="manny")
    assert r.returncode != 0
    assert inits == ["manny", "manny2"]
    assert "FAILED:   manny" in r.stdout and "upgraded: manny2" in r.stdout


def test_the_breadth_needs_confirming_when_nobody_is_at_a_terminal(tools):
    r, inits = tools("--all-agents")
    assert r.returncode == 2 and "--confirm-all-agents" in r.stderr
    assert inits == []


def test_one_named_agent_needs_no_confirmation(tools):
    r, inits = tools("manny2")
    assert r.returncode == 0 and inits == ["manny2"]


def test_no_agent_is_assumed(tools):
    r, inits = tools()
    assert r.returncode == 2 and inits == []
    assert "manny" in r.stderr and "visitor (vanilla: never upgraded)" in r.stderr


def test_a_vanilla_account_or_an_undeclared_name_is_refused(tools):
    assert tools("visitor")[0].returncode == 2 and tools("visitor")[1] == []
    r, inits = tools("maceff_user001")
    assert r.returncode == 2 and "not an agent this deployment declares" in r.stderr and inits == []


def test_framework_upgrade_upgrades_every_agent(tools):
    r, inits = tools(script="framework-upgrade")
    assert r.returncode == 0, r.stdout + r.stderr
    assert inits == ["manny", "manny2"]


def test_the_preflight_refuses_a_declaration_with_no_maceff_agent(tools):
    r, _ = tools(script="preamble-upgrade.preflight", AGENTS="visitor\\tvanilla\\n")
    assert r.returncode == 1 and "declares no MacEff agent" in r.stderr
