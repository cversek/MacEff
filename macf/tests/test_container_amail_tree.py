"""Tests for the container's amail mailbox creation.

The mailbox has to exist before ``agent/public/`` is locked to 550, or it can
never be added — an agent whose container came up without one has no place to
receive messages and no way to make one. A peer agent hit exactly that: it
hand-staged outbound messages from a temp directory and relayed them through a
human, because the tree its convention assumed had never been built.

``docker/scripts/start.py`` is a container entrypoint, not a package module, so
it is loaded by path here.
"""

import importlib.util
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

START_PY = (
    Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"
)


@pytest.fixture(scope="module")
def start_module():
    """Load start.py by path; it lives outside the importable package."""
    spec = importlib.util.spec_from_file_location("maceff_start", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def public_dir(tmp_path):
    d = tmp_path / "agent" / "public"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def calls(start_module):
    """Capture run_command instead of running it — chown needs root."""
    recorded = []
    with patch.object(start_module, "run_command", side_effect=lambda cmd, **kw: recorded.append(cmd)):
        yield recorded


def test_creates_both_boxes(start_module, public_dir, calls):
    start_module.create_amail_tree(public_dir, "pa_test")
    assert (public_dir / "amail" / "inbox").is_dir()
    assert (public_dir / "amail" / "outbox").is_dir()


def test_ships_the_convention_with_the_tree(start_module, public_dir, calls):
    """Two empty directories do not tell a fresh agent what a message is."""
    start_module.create_amail_tree(public_dir, "pa_test")
    readme = public_dir / "amail" / "README.md"
    assert readme.is_file()
    body = readme.read_text()
    assert "inbox/" in body and "outbox/" in body
    # The naming convention is the part a sender actually needs.
    assert "YYYY-MM-DD" in body


def test_group_is_agents_all_so_peers_can_deliver(start_module, public_dir, calls):
    start_module.create_amail_tree(public_dir, "pa_test")
    chowns = [c for c in calls if c[0] == "chown"]
    targets = {Path(c[2]).name: c[1] for c in chowns}
    for name in ("amail", "inbox", "outbox", "README.md"):
        assert targets.get(name) == "pa_test:agents_all", f"{name} not group agents_all"


def test_directories_are_owner_writable_group_readable(start_module, public_dir, calls):
    """750 on the boxes: the owner writes, peers traverse and read."""
    start_module.create_amail_tree(public_dir, "pa_test")
    chmods = {Path(c[2]).name: c[1] for c in calls if c[0] == "chmod"}
    assert chmods["amail"] == "750"
    assert chmods["inbox"] == "750"
    assert chmods["outbox"] == "750"
    assert chmods["README.md"] == "640"


def test_parent_permissions_are_set_after_its_contents(start_module, public_dir, calls):
    """Ordering matters: locking the parent first would block the contents."""
    start_module.create_amail_tree(public_dir, "pa_test")
    order = [Path(c[2]).name for c in calls if c[0] == "chmod"]
    assert order.index("amail") > order.index("inbox")
    assert order.index("amail") > order.index("outbox")
    assert order.index("amail") > order.index("README.md")


def test_is_idempotent_across_restarts(start_module, public_dir, calls):
    """The container re-runs init on every boot; a second pass must not wipe
    messages already delivered."""
    start_module.create_amail_tree(public_dir, "pa_test")
    message = public_dir / "amail" / "inbox" / "2026-07-31_peer_hello_001.html"
    message.write_text("<p>hello</p>")
    (public_dir / "amail" / "README.md").write_text("# locally amended\n")

    start_module.create_amail_tree(public_dir, "pa_test")

    assert message.is_file(), "existing message was destroyed by re-init"
    assert message.read_text() == "<p>hello</p>"
    # A local amendment to the convention survives too — the README is seeded,
    # not managed.
    assert (public_dir / "amail" / "README.md").read_text() == "# locally amended\n"


def test_returns_the_mailbox_path(start_module, public_dir, calls):
    result = start_module.create_amail_tree(public_dir, "pa_test")
    assert result == public_dir / "amail"


class TestTaskStoreProvisioning:
    """The live task store must be built by provisioning, like the mailbox.

    ``task_archives`` was created here for a long time while ``tasks`` -- the
    store it archives *from* -- was not, so provisioning appeared to know about
    the task subsystem while leaving every agent on CC's per-session store. That
    store deletes completed tasks and forks on rewind, and the failure is
    invisible until history is expected to survive.
    """

    def test_creates_the_store(self, start_module, public_dir, calls):
        start_module.create_task_store(public_dir, "pa_test")
        assert (public_dir / "tasks").is_dir()

    def test_store_is_distinct_from_the_archive(self, start_module, public_dir, calls):
        """CONTROL against the original confusion: creating the store must not
        be satisfied by the archive directory existing."""
        (public_dir / "task_archives").mkdir()
        start_module.create_task_store(public_dir, "pa_test")
        assert (public_dir / "tasks").is_dir()
        assert (public_dir / "tasks") != (public_dir / "task_archives")

    def test_idempotent_on_reprovision(self, start_module, public_dir, calls):
        start_module.create_task_store(public_dir, "pa_test")
        (public_dir / "tasks" / "7.json").write_text("{}")
        start_module.create_task_store(public_dir, "pa_test")
        assert (public_dir / "tasks" / "7.json").exists(), "reprovision destroyed tasks"

    def test_grants_group_access_for_peer_traversal(self, start_module, public_dir, calls):
        start_module.create_task_store(public_dir, "pa_test")
        assert ["chown", "pa_test:agents_all", str(public_dir / "tasks")] in calls
        assert ["chmod", "750", str(public_dir / "tasks")] in calls


class TestTaskStoreConfig:
    """The directory alone leaves the agent reading the legacy store."""

    def test_writes_mode_home_on_a_bare_maceff_dir(self, start_module, tmp_path, calls):
        m = tmp_path / ".maceff"
        m.mkdir()
        assert start_module.configure_task_store(m, "pa_test") is True
        import json as _json
        cfg = _json.loads((m / "config.json").read_text())
        assert cfg["task_store"]["mode"] == "home"
        assert cfg["task_store"]["path"] == "agent/public/tasks"

    def test_preserves_identity_on_upgrade(self, start_module, tmp_path, calls):
        import json as _json
        m = tmp_path / ".maceff"
        m.mkdir()
        (m / "config.json").write_text(_json.dumps(
            {"agent_identity": {"moniker": "Keep Me"}}))
        assert start_module.configure_task_store(m, "pa_test") is True
        cfg = _json.loads((m / "config.json").read_text())
        assert cfg["agent_identity"]["moniker"] == "Keep Me"
        assert cfg["task_store"]["mode"] == "home"

    def test_leaves_an_unreadable_config_untouched(self, start_module, tmp_path, calls):
        """CONTROL: overwriting a corrupt config would destroy exactly the
        information nobody can reconstruct. Report and decline."""
        m = tmp_path / ".maceff"
        m.mkdir()
        (m / "config.json").write_text("{not json")
        assert start_module.configure_task_store(m, "pa_test") is False
        assert (m / "config.json").read_text() == "{not json"
