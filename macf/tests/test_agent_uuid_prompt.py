"""The UUID mint prompt previews a calling card the daemon layer would accept (cversek/MacEff#842).

It used to preview a bare '@abc123'. Every step keyed on the card needs the name half
too, which the calling-card step writes, so the preview names that half as still to come.
"""
import re


def test_the_mint_preview_shows_a_name_half_not_a_bare_suffix(tmp_path, monkeypatch, capsys):
    from macf.cli import _ensure_agent_uuid
    monkeypatch.setattr("macf.utils.identity._resolve_uuid_source", lambda: (None, None, None))
    monkeypatch.setattr("builtins.input", lambda prompt="": "a")
    _ensure_agent_uuid(tmp_path)
    out = capsys.readouterr().out
    minted = (tmp_path / ".maceff_primary_agent.id").read_text().strip()
    preview = next(line for line in out.splitlines() if "Calling card would be" in line)
    assert f"<name>@{minted[:6]}" in preview, preview
    assert not re.search(r"would be: @", preview), preview
    assert "--calling-card NAME" in preview
