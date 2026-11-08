"""Changes to the operator's registry as shown plans (MIS-0004 R42, R45): each change is a pure
transform of the file's text, idempotent, shown as a diff before root writes it, and written only
by root, through a staged copy whose digest the printed step names."""
import datetime
import hashlib
import os
import sys
from pathlib import Path

import pytest

from macf.amail.crypto import generate_keypair, load_private_key, public_key_line
from macf.amail import registry_edit as edit
from macf.amail.registry import Registry, RegistryError, parse_text

CARD, ACCOUNT = "Alice_0a1b2c", "alice"


def _key(tmp_path, name):
    generate_keypair(tmp_path / name)
    return public_key_line(load_private_key(tmp_path / name))


def _utc(*a):
    return datetime.datetime(*a, tzinfo=datetime.timezone.utc)


# ---- the transforms --------------------------------------------------------------------------

def test_every_change_run_twice_gives_the_same_registry(tmp_path):
    """agent init and the operator's commands may run any number of times; the second run of any
    change writes nothing."""
    old, new = _key(tmp_path, "old"), _key(tmp_path, "new")
    text = edit.declare("", CARD, ACCOUNT, old)
    changes = [
        lambda t: edit.declare(t, CARD, ACCOUNT, old),
        lambda t: edit.rotate(t, CARD, new, at=_utc(2026, 6, 1)),
        lambda t: edit.retire(t, CARD, new, at=_utc(2026, 9, 1)),
        lambda t: edit.cert_record(t, "alice", "3f9a01", datetime.date(2036, 11, 8)),
        lambda t: edit.cert_retire(t, "3f9a01", at=_utc(2026, 9, 1)),
    ]
    for change in changes:
        once = change(text)
        assert change(once) == once
        parse_text(once)              # every result is a registry a load accepts
        text = once


def test_rotate_keeps_one_signing_key_at_every_instant(tmp_path):
    """R45's order: the new key is declared from the moment of rotation and the old one retired at
    that same moment, so mail accepted before it still verifies against the old key, exactly one
    key verifies at any instant, and there is never a time with two keys that may sign."""
    old, new = _key(tmp_path, "old"), _key(tmp_path, "new")
    at = _utc(2026, 6, 1)
    text = edit.rotate(edit.declare("", CARD, ACCOUNT, old), CARD, new, at=at)
    entry = parse_text(text).agents[CARD]
    by_key = {k.key: k for k in entry.keys}
    assert by_key[old].valid_until == at and by_key[new].valid_from == at and not by_key[new].retired
    for when in (at - datetime.timedelta(seconds=1), at, at + datetime.timedelta(days=30)):
        signers = [k.key for k in entry.keys if k.valid_at(when) and not k.retired]
        verifiers = [k.key for k in entry.keys if k.valid_at(when)]
        assert len(verifiers) == 1
        assert len(signers) <= 1
    assert [k.key for k in entry.keys if k.valid_at(at - datetime.timedelta(seconds=1))] == [old]
    with pytest.raises(edit.RegistryEditError, match="not declared"):
        edit.rotate("", CARD, new, at=at)


def test_a_retired_key_or_certificate_keeps_its_first_end(tmp_path):
    """Retiring again is no second stamp: the first end date stands."""
    k = _key(tmp_path, "k")
    text = edit.retire(edit.declare("", CARD, ACCOUNT, k), CARD, k, at=_utc(2026, 9, 1))
    assert edit.retire(text, CARD, k, at=_utc(2027, 1, 1)) == text
    certs = edit.cert_retire(edit.cert_record("", "alice", "3f9a01", datetime.date(2036, 11, 8)),
                             "3f9a01", at=_utc(2026, 9, 1))
    assert edit.cert_retire(certs, "3f9a01", at=_utc(2027, 1, 1)) == certs
    assert parse_text(certs).certificates[0].retired_at == _utc(2026, 9, 1)


def test_what_a_change_refuses(tmp_path):
    k, other = _key(tmp_path, "k"), _key(tmp_path, "other")
    text = edit.declare("", CARD, ACCOUNT, k)
    with pytest.raises(edit.RegistryEditError, match="account"):
        edit.declare(text, CARD, "someone_else", other)          # a card doesn't move accounts here
    with pytest.raises(edit.RegistryEditError, match="timezone"):
        edit.retire(text, CARD, k, at=datetime.datetime(2026, 9, 1))
    with pytest.raises(edit.RegistryEditError, match="timezone"):
        edit.cert_retire(edit.cert_record("", "a", "01", datetime.date(2036, 1, 1)), "01",
                         at=datetime.datetime(2026, 9, 1))
    with pytest.raises(edit.RegistryEditError, match="not declared"):
        edit.retire(text, CARD, other, at=_utc(2026, 9, 1))
    with pytest.raises(edit.RegistryEditError, match="serial"):
        edit.cert_record(edit.cert_record("", "a", "01", datetime.date(2036, 1, 1)), "b", "01",
                         datetime.date(2036, 1, 1))
    # A retirement before the key's own start would leave a window that ends before it begins.
    late = edit.rotate(text, CARD, other, at=_utc(2026, 6, 1))
    with pytest.raises(edit.RegistryEditError):
        edit.retire(late, CARD, other, at=_utc(2026, 5, 1))
    # The card is matched without regard to case (R164), and kept in its declared case.
    assert edit.declare(text, CARD.lower(), ACCOUNT, k) == text


# ---- shown, staged and written --------------------------------------------------------------

def test_a_dry_run_writes_nothing_not_even_the_staged_copy(tmp_path, monkeypatch, capsys):
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setenv("TMPDIR", str(staging))
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", None)
    target = tmp_path / "etc" / "registry.yaml"
    plan = edit.plan(target, lambda t: edit.declare(t, CARD, ACCOUNT, _key(tmp_path, "k")))
    assert plan.changed and "+  Alice_0a1b2c:" in plan.diff
    rc = edit.carry_out(plan, dry_run=True, is_root=False)
    assert rc == 0 and not target.exists() and list(staging.iterdir()) == []


def test_the_printed_root_step_names_the_staged_bytes(tmp_path, capsys):
    target = tmp_path / "etc" / "registry.yaml"
    plan = edit.plan(target, lambda t: edit.declare(t, CARD, ACCOUNT, _key(tmp_path, "k")))
    rc = edit.carry_out(plan, dry_run=False, is_root=False, staging_dir=tmp_path)
    out = capsys.readouterr().out
    assert rc == 0 and not target.exists()
    staged = Path(out.split("staged at ")[1].split()[0])
    digest = hashlib.sha256(staged.read_bytes()).hexdigest()
    assert f"sha256 {digest}" in out
    group = "wheel" if sys.platform == "darwin" else "root"
    step = edit.root_step(staged, target, platform=sys.platform)
    assert step in out and f"-o root -g {group} -m 0644 {staged}" in step
    assert step.index("install -d") < step.index(".registry.yaml.new") < step.index("mv -f")
    assert step.rstrip().endswith(f"macf_tools amail registry check --path {target}")


def test_a_registry_already_current_is_left_alone(tmp_path, capsys):
    target = tmp_path / "etc" / "registry.yaml"
    target.parent.mkdir()
    k = _key(tmp_path, "k")
    target.write_text(edit.declare("", CARD, ACCOUNT, k))
    plan = edit.plan(target, lambda t: edit.declare(t, CARD, ACCOUNT, k))
    assert not plan.changed
    assert edit.carry_out(plan, dry_run=False, is_root=False, staging_dir=tmp_path) == 0
    assert "already current" in capsys.readouterr().out and not list(tmp_path.glob("*.staged.yaml"))


def test_root_writes_in_place_and_the_result_is_held_to_the_owner_check(tmp_path, capsys):
    """As root (a container's start, or the operator), the write goes through a rename beside the
    file, and the registry is then loaded as every reader loads it, ancestors and all."""
    target = tmp_path / "etc" / "registry.yaml"
    k = _key(tmp_path, "k")
    plan = edit.plan(target, lambda t: edit.declare(t, CARD, ACCOUNT, k))
    rc = edit.carry_out(plan, dry_run=False, is_root=True, root_uid=os.getuid())
    assert rc == 0 and Registry(target, root_uid=os.getuid()).keys_for(CARD) == [k]
    assert oct(target.stat().st_mode)[-3:] == "644" and not (target.parent / ".registry.yaml.new").exists()
    # The same write where the owner check fails is reported, not passed over.
    os.chmod(target.parent, 0o777)
    plan2 = edit.plan(target, lambda t: edit.cert_record(t, "alice", "3f9a01", datetime.date(2036, 1, 1)))
    assert edit.carry_out(plan2, dry_run=False, is_root=True, root_uid=os.getuid()) == 1
    os.chmod(target.parent, 0o755)


# ---- agent init's registry step -------------------------------------------------------------

def _ctx(tmp_path, monkeypatch, dry_run=False):
    import argparse
    from macf import agent_stack
    home = tmp_path / "home"
    (home / ".maceff" / "keys").mkdir(parents=True, exist_ok=True)
    os.chmod(home / ".maceff" / "keys", 0o700)
    monkeypatch.setattr(agent_stack, "resolve_card", lambda ctx: setattr(ctx, "card", CARD) or CARD)
    monkeypatch.setenv("MACF_AMAIL_REGISTRY", str(tmp_path / "etc" / "registry.yaml"))
    monkeypatch.delenv("MACF_AMAIL_SIGNING_KEY", raising=False)
    staging = tmp_path / "staging"
    staging.mkdir(exist_ok=True)
    monkeypatch.setenv("TMPDIR", str(staging))
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", None)
    from types import SimpleNamespace
    ctx = agent_stack.Context(home=home, login_home=home, in_container=False,
                              args=argparse.Namespace(), dry_run=dry_run)
    return SimpleNamespace(stack=agent_stack, ctx=ctx, home=home, staging=staging)


def test_agent_init_declares_the_agents_key_shown_first_and_once(tmp_path, monkeypatch):
    """The operator's ruling on #927: agent init writes the agent's own entry, transparently
    (the change and the exact root step are shown) and idempotently (current means nothing)."""
    env = _ctx(tmp_path, monkeypatch)
    stack, ctx, home, staging = env.stack, env.ctx, env.home, env.staging
    target = tmp_path / "etc" / "registry.yaml"
    r = stack.step_registry(ctx)
    assert r.status == stack.SKIPPED and "amail keygen" in r.detail and not list(staging.iterdir())
    generate_keypair(home / ".maceff" / "keys" / "amail_signing_key.pem")
    public = public_key_line(load_private_key(home / ".maceff" / "keys" / "amail_signing_key.pem"))
    # --plan: what it would declare, and nothing staged.
    plan_ctx = _ctx(tmp_path, monkeypatch, dry_run=True).ctx
    plan_ctx.home = home
    r = stack.step_registry(plan_ctx)
    assert r.status == stack.WOULD and CARD in r.detail and not list(staging.iterdir())
    # A host, not root: staged, with the root step that installs exactly those bytes.
    r = stack.step_registry(ctx)
    assert r.status == stack.PLANNED and "sudo install" in r.detail and not target.exists()
    staged = next(staging.iterdir())
    assert f"sha256 {hashlib.sha256(staged.read_bytes()).hexdigest()}" in r.detail
    assert parse_text(staged.read_text()).agents[CARD].keys[0].key == public
    # Once the operator has run it, agent init finds the entry current.
    target.parent.mkdir()
    target.write_text(staged.read_text())
    assert stack.step_registry(ctx).status == stack.ALREADY
