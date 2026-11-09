"""#780: per-session folders live under this user's private runtime directory, never a bare
/tmp/macf, which the first account to create it owns, leaving every other agent unable to write."""
import os

from macf.utils import paths


def test_the_session_root_is_this_users_own(monkeypatch, tmp_path):
    monkeypatch.delenv("MACF_SESSION_ROOT", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(paths, "_TMP_ROOT", str(tmp_path))
    root = paths.session_root()
    assert root.parent == paths.user_runtime_dir()
    assert str(os.getuid()) in str(root.parent) and root != paths.Path("/tmp/macf")
    assert oct(root.parent.stat().st_mode)[-3:] == "700"


def test_the_override_still_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("MACF_SESSION_ROOT", str(tmp_path / "elsewhere"))
    assert paths.session_root() == tmp_path / "elsewhere"
