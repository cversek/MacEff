"""A rendered declaration is read in preference to the home copy, and refused unless only root
can change it (MIS-0002-R33 (run_MUST-NOT_change_schedules)). A test isn't root, so the owner the
check wants is set to the test's own uid; the refusals are what a run as the agent could do."""
import json
import os
import pwd

import pytest

from macf.pd import core
from macf.pd import names

CARD = "Resident@1a2b3c"
UNIT = {"name": "broker", "command": ["true"], "account": pwd.getpwuid(os.getuid()).pw_name, "restart": "always",
        "liveness_interval_s": 30, "memory_limit_mb": 64}


@pytest.fixture
def layout(tmp_path, monkeypatch):
    monkeypatch.setattr(names, "RENDERED_DECLARATIONS", tmp_path / "etc")
    monkeypatch.setattr(names, "SEAL_UID", os.getuid())
    home = tmp_path / "home" / "resident"
    (home / ".maceff" / "pd").mkdir(parents=True)
    (home / ".maceff" / "pd" / "declaration.json").write_text(
        json.dumps({"version": 1, "agent": CARD, "units": []}))          # the agent's own copy
    rendered = tmp_path / "etc" / "resident" / "declaration.json"
    rendered.parent.mkdir(parents=True)
    rendered.write_text(json.dumps({"version": 1, "agent": CARD, "units": [UNIT]}))
    for p in (tmp_path / "etc", rendered.parent):
        p.chmod(0o755)
    rendered.chmod(0o644)
    return home, rendered


def test_the_rendered_declaration_is_read_and_the_home_copy_is_not(layout):
    home, rendered = layout
    assert names.declaration_path(home) == rendered
    assert [u.name for u in core.load_declaration(home, CARD).units] == ["broker"]


def test_without_a_rendering_the_home_copy_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(names, "RENDERED_DECLARATIONS", tmp_path / "etc")
    home = tmp_path / "home" / "resident"
    assert names.declaration_path(home) == home / ".maceff" / "pd" / "declaration.json"


@pytest.mark.parametrize("loosen", ["file group-writable", "directory world-writable", "file a symlink"])
def test_a_rendering_the_agent_could_change_is_refused(layout, loosen):
    home, rendered = layout
    if loosen == "file group-writable":
        rendered.chmod(0o664)
    elif loosen == "directory world-writable":
        rendered.parent.chmod(0o777)
    else:
        real = rendered.with_name("real.json")
        rendered.rename(real)
        rendered.symlink_to(real)
    with pytest.raises(core.DeclarationRefused, match="R33"):
        core.load_declaration(home, CARD)


def test_a_rendering_owned_by_someone_else_is_refused(layout, monkeypatch):
    home, _ = layout
    monkeypatch.setattr(names, "SEAL_UID", os.getuid() + 1)     # the files are not the sealer's
    with pytest.raises(core.DeclarationRefused, match="owned by uid"):
        core.load_declaration(home, CARD)
