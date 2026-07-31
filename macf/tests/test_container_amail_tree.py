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
