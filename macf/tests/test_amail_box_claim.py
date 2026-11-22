"""One store claims a pickup box (#872). A copied amail settings file names the same box in a second
agent's home; both stores' locks are their own, so they would split one agent's mail between them with
nothing said. The first store to ingest claims the box, and any other store is refused, naming both."""
import pytest

from macf.amail import client
from macf.amail.client import INGEST_CLAIM, BoxClaimed


@pytest.fixture
def box(tmp_path):
    b = tmp_path / "handoff" / "ira"
    b.mkdir(parents=True)
    return b


def test_the_first_ingest_claims_the_box_for_its_store(tmp_path, box):
    home = tmp_path / "ira_home"
    client.ingest(home, box, wait=False)
    assert (box / INGEST_CLAIM).read_text().strip() == str(home.resolve())


def test_another_store_is_refused_and_both_homes_are_named(tmp_path, box):
    first, second = tmp_path / "ira_home", tmp_path / "copied_home"
    client.ingest(first, box, wait=False)
    (box / "1.eml").write_text("Subject: x\n\nbody\n")
    with pytest.raises(BoxClaimed) as e:
        client.ingest(second, box, wait=False)
    said = str(e.value)
    assert str(first.resolve()) in said and str(second.resolve()) in said and INGEST_CLAIM in said
    assert (box / "1.eml").exists()                      # nothing taken into the wrong store


def test_the_claiming_store_ingests_again_without_a_refusal(tmp_path, box):
    home = tmp_path / "ira_home"
    client.ingest(home, box, wait=False)
    client.ingest(home, box, wait=False)
    assert client.box_claim_conflict(home, box) is None


def test_the_claim_is_not_mistaken_for_mail(tmp_path, box):
    home = tmp_path / "ira_home"
    client.ingest(home, box, wait=False)
    assert client.ingest(home, box, wait=False) == []     # the claim file is no entry


def test_the_receiver_refuses_a_box_another_store_claims_and_raises_the_notice(tmp_path, box):
    from macf.pd.receiver import Receiver
    client.ingest(tmp_path / "ira_home", box, wait=False)
    notices = []
    r = Receiver("Copy_abc123", tmp_path / "copied_home", box, "ira", tmp_path / "contacts",
                 lambda name, data: None, lambda src, key: notices.append(src))
    r.tick(0.0)
    assert r.refused and "claimed" in r.refused and str((tmp_path / "ira_home").resolve()) in r.refused
    assert notices == ["pd_grant_denied"]


def test_a_claim_made_after_the_receivers_first_check_refuses_it_without_raising(tmp_path, box):
    from macf.pd.receiver import Receiver
    notices = []
    r = Receiver("Copy_abc123", tmp_path / "copied_home", box, "ira", tmp_path / "contacts",
                 lambda name, data: None, lambda src, key: notices.append(src))
    r.tick(0.0)                                             # its first pass claims the box for this store
    assert r.refused is None
    (box / INGEST_CLAIM).write_text(str((tmp_path / "ira_home").resolve()) + "\n")   # then another store's claim
    r._next = float("-inf")
    r.tick(5.0)
    assert r.refused and "claimed" in r.refused and notices == ["pd_grant_denied"]


def test_a_claimed_box_is_not_read_as_fixed_when_the_receiver_looks_again(tmp_path, box):
    """The slow re-check asks _access; a box still claimed by another store stays refused, nothing cleared."""
    from macf.pd.receiver import EVENT_REFUSAL_CLEARED, RECHECK_S, Receiver
    client.ingest(tmp_path / "ira_home", box, wait=False)
    events = []
    r = Receiver("Copy_abc123", tmp_path / "copied_home", box, "ira", tmp_path / "contacts",
                 lambda name, data: events.append(name), lambda src, key: None)
    r.tick(0.0)
    r.tick(RECHECK_S + 5)
    assert r.refused and "claimed" in r.refused and EVENT_REFUSAL_CLEARED not in events


def test_one_home_reached_by_two_paths_is_one_store(tmp_path, box):
    real = tmp_path / "ira_home"
    real.mkdir()
    link = tmp_path / "ira_link"
    link.symlink_to(real)
    client.ingest(link, box, wait=False)
    client.ingest(real, box, wait=False)                     # the same store: no refusal
    assert (box / INGEST_CLAIM).read_text().strip() == str(real.resolve())


def test_a_first_ingest_that_loses_the_race_is_refused(tmp_path, box, monkeypatch):
    """Another store links its claim between this store's check and its own link."""
    import os as real_os
    rival = str((tmp_path / "rival_home").resolve())

    def link(src, dst):
        open(dst, "w").write(rival + "\n")
        raise FileExistsError(dst)
    monkeypatch.setattr(client.os, "link", link)
    with pytest.raises(BoxClaimed) as e:
        client.ingest(tmp_path / "ira_home", box, wait=False)
    assert rival in str(e.value)
    assert [p.name for p in box.iterdir()] == [INGEST_CLAIM]       # the temporary name is gone
    monkeypatch.setattr(client.os, "link", real_os.link)


def test_a_filesystem_with_no_hard_links_still_claims_the_box(tmp_path, box, monkeypatch):
    import errno

    def link(src, dst):
        raise OSError(errno.EPERM, "Operation not permitted")
    monkeypatch.setattr(client.os, "link", link)
    home = tmp_path / "ira_home"
    client.ingest(home, box, wait=False)
    assert (box / INGEST_CLAIM).read_text().strip() == str(home.resolve())
    with pytest.raises(BoxClaimed):
        client.ingest(tmp_path / "copied_home", box, wait=False)


def test_amail_list_on_a_box_another_store_claims_warns_and_still_lists(tmp_path, box, monkeypatch, capsys):
    import argparse
    from macf import cli
    client.ingest(tmp_path / "ira_home", box, wait=False)
    copied = tmp_path / "copied_home"
    monkeypatch.setattr(cli, "_amail_config", lambda: {
        "home": str(copied), "handoff": str(box.parent), "agent": "ira", "contacts": "", "domain": ""})
    code = cli.cmd_amail_list(argparse.Namespace(all=False, thread=None, json=False))
    out = capsys.readouterr()
    assert code == 0 and "no unread messages" in out.out
    assert "nothing ingested" in out.err and str(copied.resolve()) in out.err
    assert str((tmp_path / "ira_home").resolve()) in out.err


def test_the_receiver_says_a_mid_run_claim_on_stderr(tmp_path, box, capsys):
    from macf.pd.receiver import Receiver
    r = Receiver("Copy_abc123", tmp_path / "copied_home", box, "ira", tmp_path / "contacts",
                 lambda name, data: None, lambda src, key: None)
    r.tick(0.0)
    capsys.readouterr()
    (box / INGEST_CLAIM).write_text(str((tmp_path / "ira_home").resolve()) + "\n")
    r._next = float("-inf")
    r.tick(5.0)
    err = capsys.readouterr().err
    assert "can't ingest ira's mail" in err and "claimed" in err


def test_the_fallback_create_is_exclusive_and_leaves_a_rival_claim_untouched(tmp_path, box, monkeypatch):
    """No hard links, and another store creates its claim between this store's check and its create."""
    import errno
    rival = str((tmp_path / "rival_home").resolve()) + "\n"

    def link(src, dst):
        open(dst, "w").write(rival)
        raise OSError(errno.EPERM, "Operation not permitted")
    monkeypatch.setattr(client.os, "link", link)
    with pytest.raises(BoxClaimed):
        client.ingest(tmp_path / "ira_home", box, wait=False)
    assert (box / INGEST_CLAIM).read_text() == rival


def test_the_fallback_records_the_resolved_home(tmp_path, box, monkeypatch):
    import errno

    def link(src, dst):
        raise OSError(errno.EPERM, "Operation not permitted")
    monkeypatch.setattr(client.os, "link", link)
    real = tmp_path / "ira_home"
    real.mkdir()
    (tmp_path / "ira_link").symlink_to(real)
    client.ingest(tmp_path / "ira_link", box, wait=False)
    client.ingest(real, box, wait=False)                     # the same store through its real path
    assert (box / INGEST_CLAIM).read_text().strip() == str(real.resolve())


def test_an_empty_claim_being_written_holds_the_pass(tmp_path, box):
    (box / INGEST_CLAIM).write_text("")
    (box / "1.eml").write_text("Subject: x\n\nbody\n")
    with pytest.raises(client.IngestBusy):
        client.ingest(tmp_path / "copied_home", box, wait=False)
    assert (box / "1.eml").exists()


def test_an_empty_claim_left_standing_is_refused_by_name(tmp_path, box):
    import os
    claim = box / INGEST_CLAIM
    claim.write_text("")
    old = claim.stat().st_mtime - client.EMPTY_CLAIM_STALE_S - 5
    os.utime(claim, (old, old))
    with pytest.raises(BoxClaimed) as e:
        client.ingest(tmp_path / "copied_home", box, wait=False)
    assert str(claim) in str(e.value) and "never finished" in str(e.value)


def test_the_loser_of_the_fallback_race_waits_on_the_winners_empty_claim(tmp_path, box, monkeypatch):
    """No hard links; the rival's exclusive create lands first and hasn't written its line yet."""
    import errno
    real_open = client.os.open

    def link(src, dst):
        raise OSError(errno.EPERM, "Operation not permitted")

    def open_(path, flags, *a):
        if str(path).endswith(INGEST_CLAIM) and flags & client.os.O_EXCL:
            open(path, "w").close()                         # the winner's create, still empty
            raise FileExistsError(path)
        return real_open(path, flags, *a)
    monkeypatch.setattr(client.os, "link", link)
    monkeypatch.setattr(client.os, "open", open_)
    with pytest.raises(client.IngestBusy):
        client._claim_box(tmp_path / "ira_home", box)


def test_amail_list_on_a_claim_being_written_warns_and_still_lists(tmp_path, box, monkeypatch, capsys):
    import argparse
    from macf import cli
    (box / INGEST_CLAIM).write_text("")
    monkeypatch.setattr(cli, "_amail_config", lambda: {
        "home": str(tmp_path / "ira_home"), "handoff": str(box.parent), "agent": "ira", "contacts": "", "domain": ""})
    code = cli.cmd_amail_list(argparse.Namespace(all=False, thread=None, json=False))
    out = capsys.readouterr()
    assert code == 0 and "no unread messages" in out.out and "being written" in out.err


# ---- the fallback's file, and what the receiver does after a refusal ---------------------------------

def _no_hard_links(monkeypatch):
    import errno

    def link(src, dst):
        raise OSError(errno.EPERM, "Operation not permitted")
    monkeypatch.setattr(client.os, "link", link)


def test_the_fallback_never_writes_through_a_link_planted_at_the_claim(tmp_path, box, monkeypatch):
    _no_hard_links(monkeypatch)
    victim = tmp_path / "victim.txt"
    (box / INGEST_CLAIM).symlink_to(victim)
    try:
        client.ingest(tmp_path / "ira_home", box, wait=False)
    except (BoxClaimed, client.IngestBusy):  # whichever way it refuses, nothing is written through the link
        pass
    assert not victim.exists()


def test_the_fallback_creates_the_claim_readable_by_the_group_and_not_writable(tmp_path, box, monkeypatch):
    import os
    _no_hard_links(monkeypatch)
    old = os.umask(0)
    try:
        client.ingest(tmp_path / "ira_home", box, wait=False)
    finally:
        os.umask(old)
    assert (box / INGEST_CLAIM).stat().st_mode & 0o777 == 0o640


def _two_refusals(tmp_path, box, monkeypatch, times):
    """A receiver whose box another store claims mid-run, twice, the claim removed in between."""
    from macf.pd import receiver
    from macf.pd.receiver import RECHECK_S, Receiver
    clock = [0.0]
    monkeypatch.setattr(receiver.time, "time", lambda: clock[0])
    notices = []
    home, rival = tmp_path / "copied_home", str((tmp_path / "ira_home").resolve()) + "\n"
    (box / INGEST_CLAIM).write_text(rival)
    r = Receiver("Copy_abc123", home, box, "ira", tmp_path / "contacts",
                 lambda name, data: None, lambda src, key: notices.append(key))
    r.tick(0.0)                                           # refused at the first look: the re-check is set ahead
    (box / INGEST_CLAIM).unlink()
    r._next = float("-inf")
    r.tick(RECHECK_S + 5)                                 # looks again, finds it clear, ingests, claims it
    assert r.refused is None and (box / INGEST_CLAIM).read_text().strip() == str(home.resolve())
    for i, t in enumerate(times):
        clock[0] = t
        (box / INGEST_CLAIM).write_text(rival)           # another store takes the claim
        r._next = float("-inf")
        r.tick(RECHECK_S + 10 + i * 10)
        assert r.refused and "claimed" in r.refused
        (box / INGEST_CLAIM).unlink()                     # and gives it up
        r._next = float("-inf")
        r.tick(RECHECK_S + 15 + i * 10)                   # the next pass looks again, with no wait
        assert r.refused is None, "the receiver did not look again once the claim was removed"
    return notices


def test_the_receiver_ingests_again_the_pass_after_the_claim_is_removed(tmp_path, box, monkeypatch):
    _two_refusals(tmp_path, box, monkeypatch, [1000])


def test_each_refusal_raises_its_own_notice(tmp_path, box, monkeypatch):
    keys = _two_refusals(tmp_path, box, monkeypatch, [1000, 2000])
    mid_run = [k for k in keys if k.endswith((":1000", ":2000"))]
    assert mid_run == ["pd_grant_denied:amail-receiver:1000", "pd_grant_denied:amail-receiver:2000"]
