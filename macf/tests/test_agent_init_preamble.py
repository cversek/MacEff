"""`agent init` must reconcile every CLAUDE.md the agent loads, and say what it did.

Three defects found upgrading a live agent from preamble v1.4 to v1.5.

The message said "appended" while the code replaced in place — asserting the
DANGEROUS outcome, so an operator reading it has been told the very thing they
should check for has happened.

The write was not idempotent: the upgrade boundary opens with its own `---`
separator, which sits above the marker and therefore survives the split back
into user content, so every run left two more lines in a file loaded into every
session.

And it reconciled one file while the agent loads several — leaving a v1.4 block
asserting a hardcoded compaction threshold loaded beside a v1.5 block telling the
agent to distrust exactly such numbers, with nothing naming the other file.
"""
import re
from pathlib import Path


class TestBoundarySeparatorDoesNotAccumulate:
    """The split keeps the boundary's own `---`; the next write adds another."""

    BOUNDARY_HEAD = "---\n\n<!-- ⚠️ DO NOT WRITE BELOW THIS LINE"

    def _user_region(self, content):
        """Mirror the command's extraction, including the separator strip."""
        head = content.split("<!-- ⚠️ DO NOT WRITE BELOW THIS LINE")[0].rstrip()
        return re.sub(r'\n*-{3,}\s*$', '', head).rstrip()

    def test_a_trailing_separator_is_stripped(self):
        content = "# My notes\n\nsome text\n\n" + self.BOUNDARY_HEAD + " ⚠️ -->\npreamble\n"
        assert self._user_region(content) == "# My notes\n\nsome text"

    def test_extraction_is_stable_under_repetition(self):
        """N runs must leave the user region byte-identical, or the file grows."""
        region = "# My notes\n\nsome text"
        for _ in range(5):
            rebuilt = region + "\n\n" + self.BOUNDARY_HEAD + " ⚠️ -->\npreamble\n"
            region = self._user_region(rebuilt)
        assert region == "# My notes\n\nsome text"

    def test_a_users_own_horizontal_rule_mid_document_survives(self):
        """Only a TRAILING separator is the boundary's; one in prose is content."""
        content = "# Notes\n\n---\n\nmore prose\n\n" + self.BOUNDARY_HEAD + " ⚠️ -->\np\n"
        assert "---" in self._user_region(content)


class TestLoadPathSurvey:
    """Reconciling one file while the agent loads several is the real bug."""

    def test_reports_another_file_carrying_a_preamble(self, tmp_path, monkeypatch):
        from macf.cli import other_claude_md_in_load_path
        home = tmp_path / "home"
        home.mkdir()
        (home / "CLAUDE.md").write_text(
            "notes\n<!-- MACEFF_PA_PREAMBLE_v1.4_START -->\nold\n"
            "<!-- MACEFF_PA_PREAMBLE_v1.4_END -->\n")
        monkeypatch.setattr("pathlib.Path.home", lambda: home)
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "CLAUDE.md").write_text("project\n")
        monkeypatch.chdir(proj)
        found = other_claude_md_in_load_path(proj / "CLAUDE.md")
        assert len(found) == 1
        assert found[0][1] == ["1.4"], "the stale version must be named, not just the file"

    def test_does_not_report_the_file_it_just_reconciled(self, tmp_path, monkeypatch):
        """Warning about the file you just fixed would train the warning away."""
        from macf.cli import other_claude_md_in_load_path
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr("pathlib.Path.home", lambda: home)
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "CLAUDE.md"
        target.write_text("<!-- MACEFF_PA_PREAMBLE_v1.5_START -->\nnew\n"
                          "<!-- MACEFF_PA_PREAMBLE_v1.5_END -->\n")
        assert other_claude_md_in_load_path(target) == []

    def test_orphaned_markers_are_reported_distinctly(self, tmp_path, monkeypatch):
        """Markers with no block are a real state — mine, after a manual removal."""
        from macf.cli import other_claude_md_in_load_path
        home = tmp_path / "home"
        home.mkdir()
        (home / "CLAUDE.md").write_text("notes\n<!-- ⚠️ DO NOT WRITE BELOW THIS LINE ⚠️ -->\n")
        monkeypatch.setattr("pathlib.Path.home", lambda: home)
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "CLAUDE.md").write_text("project\n")
        monkeypatch.chdir(proj)
        found = other_claude_md_in_load_path(proj / "CLAUDE.md")
        assert len(found) == 1
        assert found[0][1] == [] and found[0][2] is True

    def test_a_plain_claude_md_elsewhere_is_not_reported(self, tmp_path, monkeypatch):
        """No markers, no managed block — not ours, and not a finding."""
        from macf.cli import other_claude_md_in_load_path
        home = tmp_path / "home"
        home.mkdir()
        (home / "CLAUDE.md").write_text("just my personal notes\n")
        monkeypatch.setattr("pathlib.Path.home", lambda: home)
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "CLAUDE.md").write_text("project\n")
        monkeypatch.chdir(proj)
        assert other_claude_md_in_load_path(proj / "CLAUDE.md") == []


class TestShippedTemplatesDeclareOneVersion:
    """A version bump touches two markers, and the upgrade regex needs both.

    Bumping only the START leaves the block unterminated, so the replacement
    pattern -- which spans START to END -- stops matching. The upgrade then does
    nothing, quietly, on every agent, and the symptom is an old preamble that
    never changes rather than an error anyone sees.
    """

    ROOT = Path(__file__).resolve().parents[2] / "framework" / "templates"

    def _versions(self, name, kind):
        text = (self.ROOT / name).read_text()
        start = re.findall(rf'<!--\s*MACEFF_{kind}_PREAMBLE_v([\d.]+)_START\s*-->', text)
        end = re.findall(rf'<!--\s*MACEFF_{kind}_PREAMBLE_v([\d.]+)_END\s*-->', text)
        return start, end

    def test_pa_start_and_end_agree(self):
        start, end = self._versions("PA_PREAMBLE.md", "PA")
        assert len(start) == 1 and len(end) == 1, "exactly one marker pair expected"
        assert start == end, f"START says v{start[0]}, END says v{end[0]}"

    def test_sa_start_and_end_agree(self):
        start, end = self._versions("SA_PREAMBLE.md", "SA")
        assert len(start) == 1 and len(end) == 1, "exactly one marker pair expected"
        assert start == end, f"START says v{start[0]}, END says v{end[0]}"
