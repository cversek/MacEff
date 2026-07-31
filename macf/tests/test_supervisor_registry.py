"""Per-user supervisor registry (cversek/MacEff#159).

A single global `/tmp/macf/auto-restart` is owned by whichever uid gets there
first, so a second agent user on the same host or container crashed with
PermissionError — and the symptom ("tmux session vanished instantly") pointed
nowhere near permissions. A shared directory is also a shared namespace.
"""
import importlib
import os
import stat


def _reload_supervisor():
    import macf.supervisor as s
    return importlib.reload(s)


def test_registry_uses_xdg_runtime_dir_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    s = _reload_supervisor()
    assert s._resolve_registry_dir() == tmp_path / "macf" / "auto-restart"


def test_registry_falls_back_to_uid_qualified_tmp(monkeypatch):
    """No XDG_RUNTIME_DIR (common on macOS/containers) → uid-qualified path."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    s = _reload_supervisor()
    resolved = s._resolve_registry_dir()
    assert str(resolved) == f"/tmp/macf-{os.getuid()}/auto-restart"
    # The uid must be in the path — that is what prevents the collision.
    assert str(os.getuid()) in str(resolved)


def test_registry_is_never_the_shared_global_path(monkeypatch):
    """Regression: the old shared path is what caused the cross-user crash."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    s = _reload_supervisor()
    assert s._resolve_registry_dir() != __import__("pathlib").Path("/tmp/macf/auto-restart")


def test_registry_dir_created_owner_only(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    s = _reload_supervisor()
    s._ensure_registry_dir()
    mode = stat.S_IMODE(os.stat(s.REGISTRY_DIR).st_mode)
    assert mode == 0o700, f"expected 0700, got {oct(mode)}"
