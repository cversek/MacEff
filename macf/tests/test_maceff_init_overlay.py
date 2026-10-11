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

import os
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


def _run(deployment, env=None):
    proc = subprocess.run([str(deployment / "MacEff" / "maceff_tools" / "maceff-init"),
                           "--force-overwrite"],
                          capture_output=True, text=True, env=env)
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


# --- a refresh is made in place (#408) ------------------------------------

def _path_without_rsync(tmp_path):
    """Every command on PATH except rsync, so the script takes its portable sync."""
    bin_dir = tmp_path / "bin-no-rsync"
    bin_dir.mkdir()
    for d in os.environ["PATH"].split(os.pathsep):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            target = os.path.join(d, name)
            if name != "rsync" and not (bin_dir / name).exists() and os.access(target, os.X_OK):
                (bin_dir / name).symlink_to(target)
    assert shutil.which("rsync", path=str(bin_dir)) is None
    return dict(os.environ, PATH=str(bin_dir))


@pytest.mark.parametrize("sync", ["rsync", "portable"])
def test_a_refresh_keeps_the_directory_a_container_mounts(deployment, tmp_path, sync):
    """A running container bind-mounts .maceff/framework and holds its inode, not its
    path. Moving the tree aside left it serving the old copy until it restarted; a
    refresh must update the directories in place, and the backup is a copy."""
    if sync == "rsync" and not shutil.which("rsync"):
        pytest.skip("rsync not installed here")
    env = None if sync == "rsync" else _path_without_rsync(tmp_path)
    upstream = deployment / "MacEff" / "framework" / "templates"
    _out, fw = _run(deployment, env)
    mounted = (fw.stat().st_ino, (fw / "templates").stat().st_ino)

    (upstream / "t.md").unlink()
    (upstream / "new.md").write_text("new\n")
    _out, fw = _run(deployment, env)

    assert (fw.stat().st_ino, (fw / "templates").stat().st_ino) == mounted
    assert (fw / "templates" / "new.md").read_text() == "new\n"
    assert not (fw / "templates" / "t.md").exists()
    backups = list((deployment / "MacEff").glob(".maceff.backup-*"))
    assert len(backups) == 1 and (backups[0] / "framework" / "templates" / "t.md").exists()
    assert not list((deployment / "MacEff").glob(".maceff.build-*"))


@pytest.mark.parametrize("sync", ["rsync", "portable"])
def test_a_refresh_keeps_what_the_deployment_set_on_existing_entries(deployment, tmp_path, sync):
    """A container's start-up gives the policies tree its own group and the setgid
    bit, so that group may edit policy and new files join it. A refresh copied the
    build tree's group and modes over the top, and that boundary was gone until the
    next container start, with nothing to say so. Content changes; what the
    deployment set on an entry that already exists does not."""
    if sync == "rsync" and not shutil.which("rsync"):
        pytest.skip("rsync not installed here")
    env = None if sync == "rsync" else _path_without_rsync(tmp_path)
    upstream = deployment / "MacEff" / "framework" / "policies" / "base"
    _out, fw = _run(deployment, env)
    policies = fw / "policies"
    policy = policies / "sets" / "base" / "p.md"
    # what the start-up does: a group on the whole tree, every directory 2775
    other = [g for g in os.getgroups() if g != policies.stat().st_gid]
    tree = [policies, *policies.rglob("*")]
    for p in tree:
        if p.is_symlink():
            continue
        if other:
            os.chown(p, -1, other[0])
        p.chmod(0o2775 if p.is_dir() else 0o664)
    kept = [(p.stat().st_gid, p.stat().st_mode) for p in (policies, policy)]

    (upstream / "p.md").write_text("revised\n")
    (upstream / "added.md").write_text("added\n")
    _out, fw = _run(deployment, env)

    assert policy.read_text() == "revised\n"
    assert [(p.stat().st_gid, p.stat().st_mode) for p in (policies, policy)] == kept
    added = policies / "sets" / "base" / "added.md"
    assert added.read_text() == "added\n"
    if other:
        # a new file in a setgid directory joins the directory's group
        assert added.stat().st_gid == other[0]


# --- no one else writes what every agent's shell sources -------------------

def _writable_by_others(fw):
    """Entries outside policies/ that group or world could write."""
    return sorted(str(p.relative_to(fw)) for p in fw.rglob("*")
                  if not p.is_symlink() and "policies" not in p.relative_to(fw).parts
                  and p.stat().st_mode & 0o022)


@pytest.mark.parametrize("sync", ["rsync", "portable"])
def test_the_framework_tree_has_no_group_write_outside_policies(deployment, tmp_path, sync):
    """Every agent's shell sources env.d/ and shell/ from this tree, so a group that can
    write them runs code as every agent; in a container a service account can share the
    host's group. Under a group-writable umask, neither a fresh tree nor a refresh may
    leave group or world write outside policies/, whose group is the editors' boundary."""
    if sync == "rsync" and not shutil.which("rsync"):
        pytest.skip("rsync not installed here")
    env = None if sync == "rsync" else _path_without_rsync(tmp_path)
    (deployment / "framework" / "env.d").mkdir()
    (deployment / "framework" / "env.d" / "10-toolchain.sh").write_text("export X=1\n")
    old = os.umask(0o002)
    try:
        _out, fw = _run(deployment, env)
        assert (fw / "env.d" / "10-toolchain.sh").exists()
        assert _writable_by_others(fw) == []
        # an entry left group-writable by hand, and one new to this refresh
        (fw / "env.d" / "10-toolchain.sh").chmod(0o664)
        (deployment / "framework" / "env.d" / "20-new.sh").write_text("export Y=1\n")
        _out, fw = _run(deployment, env)
    finally:
        os.umask(old)
    assert _writable_by_others(fw) == []
    assert (fw / "env.d" / "20-new.sh").exists()
