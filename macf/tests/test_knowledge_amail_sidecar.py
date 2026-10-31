"""Mail joins the knowledge web through sidecars, and a message is never edited.

A message is a record of what was sent, so its bytes stay as sent: its concepts
live in ``<message file>.wiki-links`` under the amail folder's ``.links``
(amail policy: knowledge web participation), where no bundle unpacks. Most early mail is HTML only, so HTML messages are walked too,
with a sidecar as their only source of links.
"""
import json
from pathlib import Path
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


def _write_side(message, text):
    side = kw.sidecar_path(message)
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text(text)
    return side


def _ids(web):
    return {n for n in web["ca_nodes"] if n.startswith("amail:")}


def test_a_sidecar_makes_the_message_a_node_with_its_concepts(mail):
    _write_side(mail.thread / "003_msg.md", "Deployment Transport\n[[GPU-Arbitration]]\n\n")
    web = kw.build_knowledge_web()
    node = f"amail:{THREAD}/003_msg"
    assert node in web["ca_nodes"] and web["ca_nodes"][node]["node_class"] == "temporal_record"
    assert node in web["wiki_index"]["deployment_transport"], "a bare line is a concept, normalized"
    assert node in web["wiki_index"]["gpu_arbitration"], "the message's own link and the sidecar's union"


def test_an_html_message_with_a_sidecar_is_walked_and_its_bytes_are_not_read_for_links(mail):
    _write_side(mail.thread / "001_msg.html", "[[deployment_transport]]\n")
    _write_side(mail.thread / "index.html", "[[deployment_transport]]\n")
    web = kw.build_knowledge_web()
    node = f"amail:{THREAD}/001_msg.html"
    assert web["ca_nodes"][node]["title"] == "Transport & GPU"
    assert web["wiki_index"]["deployment_transport"] & _ids(web) == {node}, "index.html is never a node"
    assert "not_a_link" not in web["wiki_index"], "an HTML message's links are its sidecar's only"
    walked = {p.name for _t, _r, p in kw.iter_web_files(mail.home) if p.parent == mail.thread}
    assert walked == {"001_msg.html", "003_msg.md", "003_msg.html", "002_roadmap.md"}


def test_a_sidecar_is_never_a_node(mail):
    _write_side(mail.thread / "001_msg.html", "[[deployment_transport]]\n")
    _write_side(mail.thread / "002_roadmap.md", "[[deployment_transport]]\n")
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
    assert kw.sidecar_path(mail.thread / "001_msg.html").read_text() == "[[deployment_transport]]\n[[gpu]]\n"
    md = apply_links(str(mail.md), ["gpu"])
    after = {p.name: p.read_bytes() for p in mail.thread.iterdir() if not p.name.endswith(".wiki-links")}
    assert after == before, "no message, attachment or manifest byte changes"
    assert md.kind == "mail" and kw.sidecar_path(mail.thread / "003_msg.md").read_text() == "[[gpu]]\n"
    assert f"amail:{THREAD}/001_msg.html" in kw.build_knowledge_web()["wiki_index"]["gpu"]


def test_unlink_removes_from_the_sidecar_and_never_from_the_message(mail):
    sent = mail.md.read_bytes()
    apply_links(str(mail.md), ["hooks", "triage"])
    r = apply_links(str(mail.md), ["hooks", "gpu_arbitration"], remove=True)
    assert r.changed == ["hooks"] and r.still_inline == ["gpu_arbitration"]
    assert kw.sidecar_path(mail.thread / "003_msg.md").read_text() == "[[triage]]\n"
    apply_links(str(mail.md), ["triage"], remove=True)
    side = kw.sidecar_path(mail.thread / "003_msg.md")
    assert not side.exists(), "an emptied sidecar is removed"
    assert not side.parent.exists() and side.parents[2].name == kw.SIDECAR_ROOT, "and its emptied folders"
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
    assert not (mail.home / "agent" / "public" / "amail" / kw.SIDECAR_ROOT).exists()


def test_an_unlinked_message_is_an_orphan_whose_remedy_names_the_sidecar(mail):
    from macf.knowledge_doctor import examine
    orphans = [f for f in examine(mail.home).findings
               if f.check == "orphans" and f.subject.startswith("amail:")]
    assert any(f.subject.endswith("001_msg.html") for f in orphans)
    assert all("sidecar" in f.remedy for f in orphans)


def test_a_received_messages_own_links_never_reach_the_web(mail):
    """Inbound mail is untrusted input (amail policy): a received markdown message's [[links]]
    were written by its sender, so only the sidecar this agent writes gives it concepts."""
    from macf.knowledge_web import concepts_of
    amail = mail.home / "agent" / "public" / "amail"
    msg = amail / "inbox" / "2026-10-21_x" / "001_msg.md"
    msg.parent.mkdir(parents=True)
    msg.write_text("hello [[injected_concept]]\n")
    assert concepts_of("amail", msg, msg.read_text()) == []
    _write_side(msg, "[[amail]]\n")
    assert concepts_of("amail", msg, msg.read_text()) == ["amail"]
    sent = amail / "outbox" / "2026-10-21_y" / "001_msg.md"
    sent.parent.mkdir(parents=True)
    sent.write_text("mine [[budget]]\n")
    assert concepts_of("amail", sent, sent.read_text()) == ["budget"]


def test_a_sidecar_shipped_in_a_bundle_gives_a_received_message_nothing(mail):
    """A bundle is a folder of files its sender named, so a sidecar unpacked beside a
    received message is the sender's: the web reads it nowhere, and the doctor names it."""
    from macf.knowledge_doctor import examine
    thread = mail.home / "agent" / "public" / "amail" / "inbox" / "2026-10-21_bundle"
    thread.mkdir(parents=True)
    msg = thread / "001_msg.md"
    msg.write_text("# hello\n\n[[security]]\n")
    (thread / "001_msg.md.wiki-links").write_text("[[security]]\n[[credentials]]\noperator_override\n")
    assert kw.concepts_of("amail", msg, msg.read_text()) == []
    web = kw.build_knowledge_web()
    for concept in ("security", "credentials", "operator_override"):
        assert "amail:2026-10-21_bundle/001_msg" not in web["wiki_index"].get(concept, set())
    stray = [f for f in examine(mail.home).findings if f.check == "stray mail sidecars"]
    assert [f.subject for f in stray] == ["amail: inbox/2026-10-21_bundle/001_msg.md.wiki-links"]
    with pytest.raises(LinkError, match="not a sidecar the web reads"):
        apply_links(str(thread / "001_msg.md.wiki-links"), ["gpu"])
    apply_links(str(msg), ["gpu"])
    assert kw.concepts_of("amail", msg, msg.read_text()) == ["gpu"], "the agent's own sidecar counts"
    assert (thread / "001_msg.md.wiki-links").read_text().startswith("[[security]]"), "the shipped file is left as is"


def test_link_takes_a_sidecar_path_under_links_as_its_message(mail):
    side = _write_side(mail.html, "[[gpu]]\n")
    r = apply_links(str(side), ["triage"])
    assert r.kind == "mail" and Path(r.target).resolve() == mail.html.resolve()
    assert kw.read_sidecar(mail.html)[0] == ["gpu", "triage"]


def test_a_bundle_bringing_its_own_amail_and_links_gives_its_messages_nothing(mail):
    """The sidecar root is the amail folder the web walks, never the nearest folder of that
    name: a bundle's own amail/.links inside a received thread is a stray, and names nothing."""
    from macf.knowledge_doctor import examine
    amail = mail.home / "agent" / "public" / "amail"
    nested = amail / "inbox" / "2026-10-21_bundle" / "amail"
    (nested / ".links").mkdir(parents=True)
    msg = nested / "002_msg.md"
    msg.write_text("# hi\n")
    (nested / ".links" / "002_msg.md.wiki-links").write_text("[[operator_override]]\n")
    assert kw.concepts_of("amail", msg, msg.read_text()) == []
    assert kw.sidecar_path(msg).is_relative_to(amail.resolve() / kw.SIDECAR_ROOT / "inbox")
    stray = {f.subject for f in examine(mail.home).findings if f.check == "stray mail sidecars"}
    assert stray == {"amail: inbox/2026-10-21_bundle/amail/.links/002_msg.md.wiki-links"}


def test_only_the_walked_amail_folders_are_mail(mail):
    """A folder named amail anywhere else, such as source code or one the web never walks,
    is not mail: its markdown is linked in place, never through a sidecar."""
    src = mail.home / "src" / "amail" / "PROVENANCE.md"
    src.parent.mkdir(parents=True)
    src.write_text("# Provenance\n")
    r = apply_links(str(src), ["amail"])
    assert r.kind == "markdown" and "[[amail]]" in src.read_text()
    stray_root = mail.home / "agent" / "amail" / "inbox" / "t" / "001_msg.md"
    stray_root.parent.mkdir(parents=True)
    stray_root.write_text("# x\n")
    assert not kw.in_mail_root(stray_root)
    assert kw.in_mail_root(mail.md)


def test_a_home_under_a_folder_named_inbox_keeps_its_sent_links(tmp_path, monkeypatch):
    """Which box a message is in is read below the amail root, not anywhere in its path."""
    home = tmp_path / "inbox" / "home"
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(home))
    from macf.utils.paths import find_agent_home
    find_agent_home.cache_clear()
    sent = home / "agent" / "public" / "amail" / "outbox" / "t" / "001_msg.md"
    sent.parent.mkdir(parents=True)
    sent.write_text("mine [[budget]]\n")
    assert kw.concepts_of("amail", sent, sent.read_text()) == ["budget"]
    find_agent_home.cache_clear()
