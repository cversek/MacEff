"""Task metadata is parsed with libyaml's loader when PyYAML has it.

Every command that reads the whole task store parses one MTMD block per task.
With PyYAML's pure-Python loader that was about 2 s of `task get` on a store of
1,324 tasks; libyaml's loader gives the same results about fifteen times faster.
"""
import pytest
import yaml

from macf.task import models
from macf.task.models import MacfTaskMetaData

BLOCKS = {
    "ordinary": """<macf_task_metadata version="1.0">
creation_breadcrumb: s_abcd1234/c_7/g_abc1234/p_none/t_100
created_cycle: 7
task_type: BUG
title: "a title: with a colon, quoted"
wiki_links: [hooks, event_first]
updates:
- breadcrumb: s_abcd1234/c_8/g_abc1234/p_none/t_200
  description: "noted \\u00e9 \\u6f22 and a list: [a, b]"
  agent: PA
  type: note
</macf_task_metadata>""",
    "unparseable": """<macf_task_metadata version="1.0">
created_cycle: 7
title: CLI: an unquoted colon, as some old records have
</macf_task_metadata>""",
}


@pytest.fixture
def loaders_used(monkeypatch):
    used = []
    real = yaml.load

    def spy(stream, Loader):
        used.append(Loader)
        return real(stream, Loader=Loader)

    monkeypatch.setattr(yaml, "load", spy)
    return used


@pytest.mark.skipif(not getattr(yaml, "__with_libyaml__", False), reason="PyYAML built without libyaml")
def test_the_c_loader_is_used_when_pyyaml_has_it(loaders_used):
    MacfTaskMetaData.parse(BLOCKS["ordinary"])
    assert loaders_used == [yaml.CSafeLoader]


def test_the_pure_loader_is_used_without_libyaml(loaders_used, monkeypatch):
    monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
    assert MacfTaskMetaData.parse(BLOCKS["ordinary"]) is not None
    assert loaders_used == [yaml.SafeLoader]


@pytest.mark.parametrize("name", sorted(BLOCKS))
def test_both_loaders_give_the_same_metadata(name, monkeypatch):
    fast = MacfTaskMetaData.parse(BLOCKS[name])
    monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
    pure = MacfTaskMetaData.parse(BLOCKS[name])
    assert fast == pure
    assert (fast is None) == (name == "unparseable")
