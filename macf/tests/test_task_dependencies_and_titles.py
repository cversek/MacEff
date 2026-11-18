"""Three task CLI defects found while creating a MISSION's phases (cversek/MacEff#688).

- ``--blocked-by`` took every value after it, so a phase title placed after it became a
  second blocker, and the command failed for want of a title.
- ``metadata set <id> title`` rebuilt the subject without the phase's 📋, because the
  recompose never passed the plan reference the icon depends on.
- ``task block A B`` wrote ``blocks`` on A, which nothing enforces: B showed no blocker and
  started freely. The forward edge, B's ``blockedBy``, is the one the start guard reads.

Each is checked against a real task store, through the command a user runs.
"""
import argparse
import json
import re

import pytest

from macf import cli
from macf.task.create import create_mission, create_phase


def _parse(*argv):
    return cli._build_parser().parse_args(
        ["task", "create", "phase", "--plan-ca-ref", "r.md", "--parent", "5", *argv])


def test_a_title_after_blocked_by_stays_the_title():
    args = _parse("--blocked-by", "7", "Phase 2: Wire it")
    assert args.title == "Phase 2: Wire it" and args.blocked_by == ["7"]


def test_blocked_by_repeats_and_takes_comma_lists():
    args = _parse("--blocked-by", "#7,8", "--blocked-by", "9", "Phase 3: Ship it")
    assert args.blocked_by == ["7", "8", "9"] and args.title == "Phase 3: Ship it"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("MACF_TASKS_DIR", raising=False)
    monkeypatch.setenv("MACF_TASK_STORE_DIR", str(tmp_path / "tasks"))
    (tmp_path / "tasks").mkdir()
    home = tmp_path / "home"
    (home / "agent" / "public" / "roadmaps").mkdir(parents=True)
    mission = create_mission("A mission", agent_root=home)
    return tmp_path / "tasks", int(mission.task_id)


def _task(store_dir, task_id):
    return json.loads((store_dir / f"{task_id}.json").read_text())


def _subject(store_dir, task_id):
    return re.sub(r"\x1b\[[0-9;]*m", "", _task(store_dir, task_id)["subject"])


def test_a_renamed_phase_keeps_its_icon(store):
    store_dir, mission = store
    phase = create_phase(parent_id=mission, title="Phase 1: First",
                         plan_ca_ref="agent/public/roadmaps/m/roadmap.md").task_id
    assert "📋 Phase 1: First" in _subject(store_dir, phase)
    renamed = argparse.Namespace(task_id=str(phase), field="title", value="Phase 1: Renamed")
    assert cli.cmd_task_metadata_set(renamed) == 0
    assert "📋 Phase 1: Renamed" in _subject(store_dir, phase)


def test_block_writes_the_edge_that_is_enforced(store):
    from macf.task import TaskReader

    store_dir, mission = store
    gate = create_phase(parent_id=mission, title="Phase 1: Gate", plan_ca_ref="r.md").task_id
    waits = create_phase(parent_id=mission, title="Phase 2: Waits", plan_ca_ref="r.md").task_id
    edge = argparse.Namespace(task_id=str(gate), target_id=str(waits))
    assert cli.cmd_task_block(edge) == 0
    assert _task(store_dir, waits)["blockedBy"] == [str(gate)]          # what task start enforces
    assert cli.dependents_of(gate, TaskReader().read_all_tasks()) == [str(waits)]   # seen from the gate
    assert cli.cmd_task_unblock(edge) == 0
    assert _task(store_dir, waits)["blockedBy"] == []
