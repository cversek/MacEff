"""The bundle gate: what leaves by hand, rather than what leaves by broker.

The broker scrubs what passes through it. A bundle a human zips and carries
never reaches the broker. These cover that path, and in particular the two
outcomes that must stay distinct: material found, and material unread.
"""
import json
import zipfile
from argparse import Namespace
from pathlib import Path

import pytest

from macf.amail.preflight import scan_bundle

GRANT = ('{\n  "_sentinel": "MACEFF-SECRET-SENTINEL:gmail_grant:must-not-leave-host",\n'
         '  "refresh_token": "1//0FAKEFAKEFAKEFAKEFAKEFAKEFAKE"\n}\n')


@pytest.fixture
def bundle(tmp_path):
    """A plausible courier bundle: a cover note, a manifest, an attachment."""
    d = tmp_path / "outbound"
    (d / "attachments").mkdir(parents=True)
    (d / "message.md").write_text("# Cover\n\nFindings attached. Nothing secret here.\n")
    (d / "manifest.json").write_text(json.dumps({"bundle": "01.zip", "files": []}))
    (d / "attachments" / "results.csv").write_text("session,snr\nNV001,3.2\n")
    return d


def _zip(d: Path) -> Path:
    z = d.parent / "bundle.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                zf.write(f, str(f.relative_to(d)))
    return z


class TestBundleGate:
    def test_a_clean_bundle_passes_as_directory_and_as_zip(self, bundle):
        for target in (bundle, _zip(bundle)):
            r = scan_bundle(target)
            assert r["clean"], f"{target.name}: {r['findings']} {r['unscannable']}"
            assert r["files_scanned"] == 3

    def test_a_planted_credential_is_refused_in_both_forms(self, bundle):
        (bundle / "attachments" / "config_backup.json").write_text(GRANT)
        for target in (bundle, _zip(bundle)):
            r = scan_bundle(target)
            labels = {f["label"] for f in r["credentials"]}
            assert not r["clean"]
            assert any("sentinel" in x for x in labels), labels
            assert all("config_backup.json" in f["file"] for f in r["credentials"])

    def test_private_vocabulary_is_reported_but_does_not_block(self, bundle, capsys):
        """Between agents of this framework the vocabulary IS the content.

        The first version called these credential-class and refused every bundle
        that had really been carried -- over twenty findings each, not one of
        them a credential.
        """
        from macf import cli
        (bundle / "message.md").write_text(
            "Ira here. MISSION #172 is closed; macf_tools reports 45 sessions.\n")
        r = scan_bundle(bundle)
        assert r["credentials"] == []
        assert r["context"], "expected the framework vocabulary to be noticed"
        rc = cli.cmd_amail_preflight(Namespace(target=str(bundle), json=False,
                                               allow_unscannable=False, strict=False))
        out = capsys.readouterr().out
        assert rc == 0 and "no credential material" in out

    def test_strict_blocks_the_same_bundle_when_the_destination_is_foreign(self, bundle, capsys):
        from macf import cli
        (bundle / "message.md").write_text("MISSION #172 via macf_tools\n")
        rc = cli.cmd_amail_preflight(Namespace(target=str(bundle), json=False,
                                               allow_unscannable=False, strict=True))
        assert rc == 3 and "strict" in capsys.readouterr().out.lower()

    def test_the_refusal_never_carries_the_material(self, bundle, capsys):
        """A gate that quotes what it caught has moved the disclosure, not stopped it."""
        from macf import cli
        (bundle / "leak.json").write_text(GRANT)
        rc = cli.cmd_amail_preflight(Namespace(target=str(bundle), json=False,
                                               allow_unscannable=False, strict=False))
        out = capsys.readouterr().out
        assert rc == 3
        assert "1//0FAKE" not in out
        assert "MACEFF-SECRET-SENTINEL" not in out
        assert "REDACTED" in out

    def test_an_unreadable_file_is_not_reported_as_clean(self, bundle):
        """Absence of evidence is its own outcome, distinct from a pass."""
        (bundle / "attachments" / "scan.pdf").write_bytes(b"%PDF-1.4\n\xff\xfe\x00\x01binary")
        r = scan_bundle(bundle)
        assert not r["clean"]
        assert r["credentials"] == []
        assert any(n.endswith("scan.pdf") for n in r["unscannable"])

    def test_unscannable_exits_distinctly_and_can_be_allowed_after_review(self, bundle, capsys):
        from macf import cli
        (bundle / "attachments" / "scan.pdf").write_bytes(b"%PDF-1.4\n\xff\xfe\x00\x01binary")
        assert cli.cmd_amail_preflight(Namespace(target=str(bundle), json=False,
                                                 allow_unscannable=False, strict=False)) == 4
        capsys.readouterr()
        assert cli.cmd_amail_preflight(Namespace(target=str(bundle), json=False,
                                                 allow_unscannable=True, strict=False)) == 0
        assert "no credential material" in capsys.readouterr().out

    def test_a_finding_outranks_an_unreadable_file(self, bundle, capsys):
        """A bundle with both must refuse, not merely ask for review."""
        from macf import cli
        (bundle / "leak.json").write_text(GRANT)
        (bundle / "attachments" / "scan.pdf").write_bytes(b"%PDF\xff\xfe\x00")
        assert cli.cmd_amail_preflight(Namespace(target=str(bundle), json=False,
                                                 allow_unscannable=True, strict=False)) == 3

    def test_a_path_that_is_neither_directory_nor_zip_is_refused_not_passed(self, tmp_path, capsys):
        from macf import cli
        loose = tmp_path / "note.txt"
        loose.write_text("hello")
        assert cli.cmd_amail_preflight(Namespace(target=str(loose), json=False,
                                                 allow_unscannable=False, strict=False)) == 1
        assert cli.cmd_amail_preflight(Namespace(target=str(tmp_path / "nope"), json=False,
                                                 allow_unscannable=False, strict=False)) == 1
