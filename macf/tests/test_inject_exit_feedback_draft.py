"""An injected /exit refuses while the client holds an unsent feedback draft.

With a draft waiting, the client answers /exit with a dialog (review and send, or discard)
instead of exiting, so a session restart asked by `inject exit` sat in that dialog for six
minutes until the operator pressed a key (Oct 24). The draft is the operator's to send or
discard, so inject neither types into the dialog nor touches the file: it refuses and names it.
"""

from unittest.mock import patch

from macf import supervisor


def _drafts(tmp_path, monkeypatch, *names):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    drafts = tmp_path / "feedback" / "drafts"
    drafts.mkdir(parents=True)
    for name in names:
        (drafts / name).write_text("{}")
    return drafts


def test_exit_refuses_and_names_the_draft(tmp_path, monkeypatch, capsys):
    drafts = _drafts(tmp_path, monkeypatch, "e4605d9f.json")
    with patch.object(supervisor, "own_pane_target", return_value="seat"), \
         patch.object(supervisor, "_draft_in_box", return_value=""), \
         patch.object(supervisor, "send_keys", return_value=0) as send:
        assert supervisor.send_slash_to_self("exit") == 1
    send.assert_not_called()
    err = capsys.readouterr().err
    assert str(drafts / "e4605d9f.json") in err and "feedback" in err
    assert (drafts / "e4605d9f.json").exists()


def test_exit_is_typed_when_no_draft_waits(tmp_path, monkeypatch):
    _drafts(tmp_path, monkeypatch)
    with patch.object(supervisor, "own_pane_target", return_value="seat"), \
         patch.object(supervisor, "_draft_in_box", return_value=""), \
         patch.object(supervisor, "send_keys", return_value=0) as send, \
         patch("macf.stop_bypass.arm"):
        assert supervisor.send_slash_to_self("exit") == 0
    send.assert_called_once_with("seat", ["/exit"], enter=True, kind="inject")


def test_a_draft_does_not_stop_other_commands(tmp_path, monkeypatch):
    """Only exiting meets the dialog; a compaction runs past a waiting draft."""
    _drafts(tmp_path, monkeypatch, "e4605d9f.json")
    with patch.object(supervisor, "own_pane_target", return_value="seat"), \
         patch.object(supervisor, "_draft_in_box", return_value=""), \
         patch.object(supervisor, "send_keys", return_value=0) as send, \
         patch("macf.stop_bypass.arm"):
        assert supervisor.send_slash_to_self("compact", then=None) == 0
    send.assert_called_once()
