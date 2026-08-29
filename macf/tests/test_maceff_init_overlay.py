"""The parent-repo overlay must not drop what a deployment declares.

`maceff-init` copies the submodule's framework/ recursively, then applies the
parent repo's framework/ on top. The second pass used to be six hand-written
paths, and anything else was dropped with nothing said -- so a deployment's own
customization got worse treatment than the upstream default it exists to
override.

The shape is what makes it expensive: the file works when placed by hand, gets
committed to the parent repo in what looks like the right place, and vanishes
on the one command whose purpose is reproducibility. Nothing records a
decision, so the reader concludes it was never applied and looks elsewhere.

These tests drive the real script in a scratch deployment rather than reading
it, because the property is what ends up on disk.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "maceff_tools" / "maceff-init"

pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="maceff-init not present")


@pytest.fixture
def deployment(tmp_path):
    """A parent repo with MacEff as a submodule, which is the only shape that
    triggers the overlay at all."""
    sub = tmp_path / "MacEff"
    (sub / "maceff_tools").mkdir(parents=True)
    # the submodule-context detector requires BOTH of these to exist
    (sub / "framework" / "policies" / "base").mkdir(parents=True)
    (sub / "framework" / "templates").mkdir(parents=True)
    (sub / "framework" / "policies" / "base" / "p.md").write_text("upstream\n")
    (sub / "framework" / "templates" / "t.md").write_text("upstream\n")

    dest = sub / "maceff_tools" / "maceff-init"
    shutil.copy2(SCRIPT, dest)
    dest.chmod(0o755)

    (tmp_path / "framework").mkdir()
    return tmp_path


def _run(deployment):
    proc = subprocess.run([str(deployment / "MacEff" / "maceff_tools" / "maceff-init"),
                           "--force-overwrite"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout + proc.stderr, deployment / "MacEff" / ".maceff" / "framework"


# --- the defect -----------------------------------------------------------

def test_entry_outside_the_historical_list_survives(deployment):
    """A directory the old enumeration did not know about must be copied.

    `shell/` is not a hypothetical: it is where the framework's supervised
    launcher lives, and it postdates the six-path list. A deployment overriding
    it would have lost the override on the next init.
    """
    (deployment / "framework" / "shell").mkdir()
    (deployment / "framework" / "shell" / "50-harness.sh").write_text("deployment\n")
    (deployment / "framework" / "custom.yaml").write_text("deployment\n")

    _out, fw = _run(deployment)

    assert (fw / "shell" / "50-harness.sh").read_text() == "deployment\n"
    assert (fw / "custom.yaml").read_text() == "deployment\n"


def test_historically_covered_paths_still_overlay(deployment):
    """The six that always worked must keep working -- this is a fix, not a
    rewrite, and a generalisation that broke them would be a worse bug."""
    (deployment / "framework" / "env.d").mkdir()
    (deployment / "framework" / "env.d" / "10-x.sh").write_text("deployment\n")
    (deployment / "framework" / "agents.yaml").write_text("deployment\n")

    _out, fw = _run(deployment)

    assert (fw / "env.d" / "10-x.sh").read_text() == "deployment\n"
    assert (fw / "agents.yaml").read_text() == "deployment\n"


def test_every_overlaid_entry_is_named_in_the_output(deployment):
    """Naming the path is the requirement. "Some files were not copied" leaves
    the reader exactly where they started."""
    (deployment / "framework" / "shell").mkdir()
    (deployment / "framework" / "shell" / "x.sh").write_text("d\n")

    out, _fw = _run(deployment)

    assert "OVERLAY" in out and "shell" in out


# --- the new silence this fix must not introduce --------------------------

def test_hidden_entries_are_reported_and_not_copied(deployment):
    """Hidden entries are ambiguous: recursing a stray .git would be
    catastrophic, but skipping in silence is the very defect being fixed. So
    they are named and left, and the operator decides."""
    (deployment / "framework" / ".secretdir").mkdir()
    (deployment / "framework" / ".secretdir" / "x").write_text("hidden\n")

    out, fw = _run(deployment)

    assert "SKIPPED (hidden)" in out
    assert ".secretdir" in out
    assert not (fw / ".secretdir").exists(), "hidden entry was copied blind"


def test_policies_layout_survives_a_parent_supplied_policies_dir(deployment):
    """Generalising the overlay could have introduced a NEW silent mishandling.

    The base -> sets/base normalisation ran once, right after the submodule
    copy. Once the overlay stopped being a fixed list, a deployment shipping
    framework/policies/base/ could land it after that step had already gone
    past -- leaving a layout the `current` symlink does not expect, silently.
    """
    (deployment / "framework" / "policies" / "base").mkdir(parents=True)
    (deployment / "framework" / "policies" / "base" / "own.md").write_text("deployment\n")

    _out, fw = _run(deployment)

    assert not (fw / "policies" / "base").exists(), "left in the pre-normalisation layout"
    assert (fw / "policies" / "sets" / "base" / "own.md").read_text() == "deployment\n"


def test_config_is_not_duplicated_into_the_framework_tree(deployment):
    """`framework/config/` belongs to a different pass and a different place.

    It is overlaid to `.maceff/config/`, which is where the container's env
    files are read from. The generic loop would also have copied it to
    `.maceff/framework/config/` -- a second, divergent copy that nothing reads,
    producing exactly the "which one is live?" ambiguity this fix exists to
    remove.

    Found against a real deployment rather than this fixture: its parent
    framework/ carries a config/ directory, and the synthetic tree did not.
    """
    (deployment / "framework" / "config" / "projects").mkdir(parents=True)
    (deployment / "framework" / "config" / "projects" / "x.env").write_text("K=V\n")

    _out, fw = _run(deployment)
    maceff = fw.parent

    assert (maceff / "config" / "projects" / "x.env").read_text() == "K=V\n", \
        "config/ did not reach its real destination"
    assert not (fw / "config").exists(), \
        "config/ was duplicated into the framework tree"
