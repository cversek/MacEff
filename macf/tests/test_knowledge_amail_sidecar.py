"""Mail joins the knowledge web through sidecars, and a message is never edited.

A message is a record of what was sent, so its bytes stay as sent: its concepts
live in ``<message file>.wiki-links`` beside it (amail policy: knowledge web
participation). Most early mail is HTML only, so HTML messages are walked too,
with a sidecar as their only source of links.
"""
import json
from types import SimpleNamespace

import pytest

from macf import knowledge_web as kw
from macf.knowledge_link import LinkError, apply_links, decline

THREAD = "2026-07-24_thm_transport_004"


@pytest.fixture
def mail(tmp_path, monkeypatch):
    """An agent home with one outbox thread: an HTML message, a markdown
    message with its own [[link]], an attachment, an index.html and a manifest."""
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    store = tmp_path / "agent" / "public" / "tasks"
    store.mkdir(parents=True)
    monkeypatch.setenv("MACF_TASK_STORE_DIR", str(store))
    thread = tmp_path / "agent" / "public" / "amail" / "outbox" / THREAD
    thread.mkdir(parents=True)
    html = thread / "001_msg.html"
    html.write_bytes(b"<html><head><title>Transport &amp; GPU</title></head><body>[[not_a_link]]</body></html>\n")
    md = thread / "003_msg.md"
    md.write_bytes(b"# Re: transport\n\nThe [[gpu_arbitration]] question.\n")
    (thread / "003_msg.html").write_bytes(b"<html><title>same message, html copy</title></html>\n")
    (thread / "002_roadmap.md").write_text("# Roadmap\n")
    (thread / "index.html").write_text("<html>index</html>\n")
    (thread / "manifest.json").write_text(json.dumps({"thread": THREAD}))
    return SimpleNamespace(home=tmp_path, thread=thread, html=html, md=md)


def _ids(web):
    return {n for n in web["ca_nodes"] if n.startswith("amail:")}


def test_a_sidecar_makes_the_message_a_node_with_its_concepts(mail):
    (mail.thread / "003_msg.md.wiki-links").write_text("Deployment Transport\n[[GPU-Arbitration]]\n\n")
    web = kw.build_knowledge_web()
    node = f"amail:{THREAD}/003_msg"
    assert node in web["ca_nodes"] and web["ca_nodes"][node]["node_class"] == "temporal_record"
    assert node in web["wiki_index"]["deployment_transport"], "a bare line is a concept, normalized"
    assert node in web["wiki_index"]["gpu_arbitration"], "the message's own link and the sidecar's union"


def test_an_html_message_with_a_sidecar_is_walked_and_its_bytes_are_not_read_for_links(mail):
    (mail.thread / "001_msg.html.wiki-links").write_text("[[deployment_transport]]\n")
    (mail.thread / "index.html.wiki-links").write_text("[[deployment_transport]]\n")
    web = kw.build_knowledge_web()
    node = f"amail:{THREAD}/001_msg.html"
    assert web["ca_nodes"][node]["title"] == "Transport & GPU"
    assert web["wiki_index"]["deployment_transport"] & _ids(web) == {node}, "index.html is never a node"
    assert "not_a_link" not in web["wiki_index"], "an HTML message's links are its sidecar's only"
    walked = {p.name for _t, _r, p in kw.iter_web_files(mail.home) if p.parent == mail.thread}
    assert walked == {"001_msg.html", "003_msg.md", "003_msg.html", "002_roadmap.md"}


def test_a_sidecar_is_never_a_node(mail):
    (mail.thread / "001_msg.html.wiki-links").write_text("[[deployment_transport]]\n")
    (mail.thread / "002_roadmap.md.wiki-links").write_text("[[deployment_transport]]\n")
    walked = [p for _t, _r, p in kw.iter_web_files(mail.home)]
    assert not [p for p in walked if p.name.endswith(".wiki-links")]
    web = kw.build_knowledge_web()
    assert not [n for n, i in web["ca_nodes"].items() if i["path"].endswith(".wiki-links")]
    assert f"amail:{THREAD}/002_roadmap" in web["wiki_index"]["deployment_transport"]


def test_link_writes_the_sidecar_and_leaves_the_message_and_manifest_as_sent(mail):
    before = {p.name: p.read_bytes() for p in mail.thread.iterdir()}
    first = apply_links(str(mail.html), ["Deployment Transport"])
    again = apply_links(f"amail:{THREAD}/001_msg.html", ["deployment_transport", "gpu"])
    assert first.kind == "mail" and first.changed == ["deployment_transport"] and again.changed == ["gpu"]
    assert (mail.thread / "001_msg.html.wiki-links").read_text() == "[[deployment_transport]]\n[[gpu]]\n"
    md = apply_links(str(mail.md), ["gpu"])
    after = {p.name: p.read_bytes() for p in mail.thread.iterdir() if not p.name.endswith(".wiki-links")}
    assert after == before, "no message, attachment or manifest byte changes"
    assert md.kind == "mail" and (mail.thread / "003_msg.md.wiki-links").read_text() == "[[gpu]]\n"
    assert f"amail:{THREAD}/001_msg.html" in kw.build_knowledge_web()["wiki_index"]["gpu"]


def test_unlink_removes_from_the_sidecar_and_never_from_the_message(mail):
    sent = mail.md.read_bytes()
    apply_links(str(mail.md), ["hooks", "triage"])
    r = apply_links(str(mail.md), ["hooks", "gpu_arbitration"], remove=True)
    assert r.changed == ["hooks"] and r.still_inline == ["gpu_arbitration"]
    assert (mail.thread / "003_msg.md.wiki-links").read_text() == "[[triage]]\n"
    apply_links(str(mail.md), ["triage"], remove=True)
    assert not (mail.thread / "003_msg.md.wiki-links").exists(), "an emptied sidecar is removed"
    assert mail.md.read_bytes() == sent


def test_decline_lands_in_the_sidecar(mail):
    sent = mail.html.read_bytes()
    apply_links(str(mail.html), ["gpu"])
    r = decline(f"amail:{THREAD}/001_msg.html", ["Docker"])
    assert r.changed == ["docker"] and mail.html.read_bytes() == sent
    assert kw.read_sidecar(mail.html) == (["gpu"], ["docker"])
    assert kw.build_knowledge_web()["ca_nodes"][f"amail:{THREAD}/001_msg.html"]["not_linked"] == ["docker"]


def test_only_mail_units_take_a_sidecar(mail):
    with pytest.raises(LinkError, match="not a mail message"):
        apply_links(str(mail.thread / "manifest.json"), ["gpu"])
    with pytest.raises(LinkError, match="not a mail message"):
        apply_links(str(mail.thread / "index.html"), ["gpu"])
    assert not list(mail.thread.glob("*.wiki-links"))


def test_an_unlinked_message_is_an_orphan_whose_remedy_names_the_sidecar(mail):
    from macf.knowledge_doctor import examine
    orphans = [f for f in examine(mail.home).findings
               if f.check == "orphans" and f.subject.startswith("amail:")]
    assert any(f.subject.endswith("001_msg.html") for f in orphans)
    assert all("sidecar" in f.remedy for f in orphans)


def test_a_received_messages_own_links_never_reach_the_web(tmp_path):
    """Inbound mail is untrusted input (amail policy): a received markdown message's [[links]]
    were written by its sender, so only the sidecar this agent writes gives it concepts."""
    from macf.knowledge_web import concepts_of
    msg = tmp_path / "amail" / "inbox" / "2026-10-21_x" / "001_msg.md"
    msg.parent.mkdir(parents=True)
    msg.write_text("hello [[injected_concept]]\n")
    assert concepts_of("amail", msg, msg.read_text()) == []
    (msg.parent / "001_msg.md.wiki-links").write_text("[[amail]]\n")
    assert concepts_of("amail", msg, msg.read_text()) == ["amail"]
    sent = tmp_path / "amail" / "outbox" / "2026-10-21_y" / "001_msg.md"
    sent.parent.mkdir(parents=True)
    sent.write_text("mine [[budget]]\n")
    assert concepts_of("amail", sent, sent.read_text()) == ["budget"]
