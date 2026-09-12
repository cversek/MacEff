"""A hook dispatcher that composes, and adopts rather than clobbers.

Git gives a repository one file per hook, so every installer that wants a say
must refuse or overwrite. Refusing is the correct posture for a lone installer
and the wrong shape for a second one: the framework wants two things in
pre-commit, and whichever installed second lost while saying nothing afterwards.

The tests that matter here are about what happens to things the installer did
NOT put there.
"""

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from macf.githooks import install_dispatcher, list_hooklets

DISPATCHER = Path(__file__).resolve().parents[2] / ".githooks" / "pre-commit"


def _repo(tmp_path, with_existing_hook=None):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if with_existing_hook is not None:
        hooks = repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        hook = hooks / "pre-commit"
        hook.write_text(with_existing_hook)
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    return repo


class TestAdoptionRatherThanReplacement:

    def test_a_pre_existing_hook_is_moved_not_destroyed(self, tmp_path):
        """The developer's own hook keeps working. Destroying it is the failure
        the old installer refused in order to avoid — at the cost of the second
        gate never existing at all."""
        repo = _repo(tmp_path, with_existing_hook="#!/bin/sh\nexit 0\n")

        facts = install_dispatcher(repo)

        adopted = repo / ".git" / "hooks.local.d" / "pre-commit.d" / "00-local-preexisting"
        assert adopted.is_file(), "the pre-existing hook was lost"
        assert os.access(adopted, os.X_OK), "adopted but no longer runnable"
        assert facts["adopted"], "adoption happened but was not reported"

    def test_the_adopted_hook_runs_first(self, tmp_path):
        """It was running before the framework arrived and keeps its position.
        The 00 prefix is the whole ordering contract."""
        repo = _repo(tmp_path, with_existing_hook="#!/bin/sh\nexit 0\n")
        install_dispatcher(repo)

        names = [h["name"] for h in list_hooklets(repo)]
        assert names == ["00-local-preexisting"], (
            "the adopted hook must lead, and an unrelated repo must NOT inherit "
            "MacEff's own versioned hooklets — they travel by living in the "
            "repository that owns them"
        )

    def test_ordering_is_by_name_across_both_directories(self, tmp_path):
        """Ordering spans the per-clone and versioned directories, which is why
        it cannot be answered by listing either one."""
        repo = _repo(tmp_path)
        install_dispatcher(repo)
        local = repo / ".git" / "hooks.local.d" / "pre-commit.d"
        local.mkdir(parents=True, exist_ok=True)
        for name in ("05-early", "99-late"):
            p = local / name
            p.write_text("#!/bin/sh\nexit 0\n")
            p.chmod(p.stat().st_mode | stat.S_IXUSR)

        versioned = repo / ".githooks" / "pre-commit.d" / "50-versioned"
        versioned.parent.mkdir(parents=True, exist_ok=True)
        versioned.write_text("#!/bin/sh\nexit 0\n")
        versioned.chmod(versioned.stat().st_mode | stat.S_IXUSR)

        assert [h["name"] for h in list_hooklets(repo)] == [
            "05-early", "50-versioned", "99-late"
        ], "ordering did not interleave the per-clone and versioned directories"


class TestIdempotence:

    def test_a_second_install_changes_nothing(self, tmp_path):
        """A provisioning command called unconditionally must not accumulate.
        An empty action list is the observable difference between idempotent and
        merely harmless."""
        repo = _repo(tmp_path, with_existing_hook="#!/bin/sh\nexit 0\n")
        install_dispatcher(repo)

        before = {p: p.read_bytes() for p in sorted((repo / ".githooks").rglob("*")) if p.is_file()}
        facts = install_dispatcher(repo)
        after = {p: p.read_bytes() for p in sorted((repo / ".githooks").rglob("*")) if p.is_file()}

        assert facts["actions"] == [], f"a no-op run reported {facts['actions']}"
        assert facts["already_current"] is True
        assert before == after, "the tree changed on a run that claimed to change nothing"

    def test_adoption_does_not_repeat(self, tmp_path):
        """Re-adopting would overwrite the first adoption with whatever holds
        the slot now — including, eventually, the dispatcher itself."""
        repo = _repo(tmp_path, with_existing_hook="#!/bin/sh\necho original\nexit 0\n")
        install_dispatcher(repo)
        adopted = repo / ".git" / "hooks.local.d" / "pre-commit.d" / "00-local-preexisting"
        first = adopted.read_text()

        install_dispatcher(repo)

        assert adopted.read_text() == first


class TestTheChainActuallyRuns:

    def test_a_failing_hooklet_blocks_the_commit_and_names_itself(self, tmp_path):
        repo = _repo(tmp_path)
        install_dispatcher(repo)
        local = repo / ".git" / "hooks.local.d" / "pre-commit.d"
        local.mkdir(parents=True, exist_ok=True)
        bad = local / "05-refuses"
        bad.write_text("#!/bin/sh\necho 'nope' >&2\nexit 1\n")
        bad.chmod(bad.stat().st_mode | stat.S_IXUSR)

        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.st"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
        (repo / "a.txt").write_text("x")
        subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True)

        r = subprocess.run(["git", "-C", str(repo), "commit", "-m", "x"],
                           capture_output=True, text=True)

        assert r.returncode != 0, "a failing hooklet did not block the commit"
        assert "05-refuses" in r.stderr, "the blocking hooklet was not named"

    def test_a_present_but_non_executable_hooklet_is_refused_not_skipped(self, tmp_path):
        """Skipping it quietly would report success for a gate that never ran,
        which is worse than having no gate because it is believed."""
        repo = _repo(tmp_path)
        install_dispatcher(repo)
        local = repo / ".git" / "hooks.local.d" / "pre-commit.d"
        local.mkdir(parents=True, exist_ok=True)
        inert = local / "05-not-executable"
        inert.write_text("#!/bin/sh\nexit 0\n")
        inert.chmod(0o644)

        entry = next(h for h in list_hooklets(repo) if h["name"] == "05-not-executable")
        assert entry["executable"] is False, "reported as runnable while it is not"


class TestDispatcherIsBash32Safe:
    """macOS ships bash 3.2 and the dispatcher's shebang names /bin/bash.

    CI runs bash 5, where none of these constructs fail — so this is a STATIC
    check for the same reason the harness one is: the runtime failure is
    invisible in the only environment that runs automatically.
    """

    TEXT = DISPATCHER.read_text()

    #: Comment lines dropped. A construct NAMED in a comment is a mention, not a
    #: use -- and without this, the comment explaining why `mapfile` is banned
    #: would itself fail the check, pushing an author to delete the explanation
    #: in order to satisfy it.
    CODE = "\n".join(l for l in TEXT.splitlines() if not l.lstrip().startswith("#"))

    def test_no_bash4_only_builtins(self):
        for construct in ("mapfile", "readarray", "declare -A", "${BASH_REMATCH", "${var,,"):
            assert construct not in self.CODE, f"{construct} does not exist in bash 3.2"

    def test_every_case_pattern_uses_the_leading_paren_form(self):
        """Inside `$( )`, bash 3.2 counts the `)` closing a case pattern as the
        one closing the substitution and dies on `;;`. bash 4+ parses it either
        way, so this fails only on macOS.

        The rule is ALL patterns, not only those inside a substitution. One rule
        with no exceptions is checkable; "only inside `$( )`" needs a checker
        that reproduces the very parser confusion it is looking for -- the first
        version of this test did exactly that and could not see its own
        synthetic offender. The leading-paren form parses everywhere, so the
        stricter rule costs nothing.

        Reintroduced once while writing the very hook that fixes the class,
        which is the argument for checking it rather than remembering it.
        """
        offenders = [
            line.strip() for line in self.CODE.splitlines()
            if ";;" in line and not line.strip().startswith("(")
        ]
        assert not offenders, f"case patterns missing the leading paren: {offenders}"

    def test_the_paren_check_can_actually_fail(self):
        """A check never watched failing is a painted bulb, and this one is
        subtle enough that a broken version would look identical to a clean one.
        """
        saved = type(self).CODE
        try:
            type(self).CODE = 'case "$f" in\n  a) continue ;;\nesac'
            with pytest.raises(AssertionError):
                self.test_every_case_pattern_uses_the_leading_paren_form()
        finally:
            type(self).CODE = saved

    def test_every_array_value_expansion_is_guarded(self):
        """Under `set -u`, bash 3.2 aborts on an empty array's `[@]`. Same rule
        the harness start script now follows."""
        assert "set -u" in self.CODE, "this check inspected a script without set -u"
        for m in re.finditer(r'"\$\{([A-Za-z_][A-Za-z0-9_]*)\[@\]\}"', self.CODE):
            pytest.fail(f"unguarded ${{{m.group(1)}[@]}} — use ${{name[@]+\"${{name[@]}}\"}}")


def _commit(repo, message, path="a.txt"):
    """Stage a file and commit with the given message; returns the CompletedProcess."""
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.st"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    f = repo / path
    f.write_text(f.read_text() + "x" if f.exists() else "x")
    subprocess.run(["git", "-C", str(repo), "add", path], check=True)
    return subprocess.run(["git", "-C", str(repo), "commit", "-F", "-"],
                          input=message, capture_output=True, text=True)


SESSION_TRAILER = ("feat: something\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n"
                   "Claude-Session: https://claude.ai/code/session_01V28aryCvj2w6i25W9KeD9m\n")
BARE_URL = "feat: something\n\nsee https://claude.ai/code/session_01V28aryCvj2w6i25W9KeD9m for context\n"
CLEAN = "feat: something\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n\n[AgentMacEff@abc123: task#1 s_a/c_1/p_b/t_2]\n"


class TestCommitMsgStageAndPortableHooklets:
    """The session-link guard is delivered by the INSTALLER into the per-clone
    directory of whatever repository it is run on -- a scratch repo here, which
    never asked for anything MacEff-specific and must still get exactly this one
    hooklet and nothing that depends on MacEff's tree."""

    def test_install_delivers_the_guard_into_a_foreign_repo(self, tmp_path):
        repo = _repo(tmp_path)
        report = install_dispatcher(repo)
        assert (repo / ".githooks" / "commit-msg").is_file()
        guard = repo / ".git" / "hooks.local.d" / "commit-msg.d" / "10-no-session-url"
        assert guard.is_file() and os.access(guard, os.X_OK)
        assert any("10-no-session-url" in a for a in report["actions"])
        # nothing MacEff-specific came along: the style gate needs tools/ that this repo lacks
        assert not (repo / ".githooks" / "pre-commit.d" / "20-style").exists()
        assert [h["name"] for h in list_hooklets(repo, "commit-msg")] == ["10-no-session-url", "20-no-private-refs"]
        # and the second install is a genuine no-op
        assert install_dispatcher(repo)["actions"] == []

    def test_a_session_trailer_is_refused_and_the_id_is_not_echoed(self, tmp_path):
        repo = _repo(tmp_path)
        install_dispatcher(repo)
        r = _commit(repo, SESSION_TRAILER)
        assert r.returncode != 0, "a Claude-Session trailer was committed"
        assert "10-no-session-url" in r.stderr
        assert "session_<redacted>" in r.stderr
        assert "session_01V28aryCvj2w6i25W9KeD9m" not in r.stderr, "the refusal printed the identifier"

    def test_a_bare_session_url_in_the_body_is_refused_too(self, tmp_path):
        repo = _repo(tmp_path)
        install_dispatcher(repo)
        assert _commit(repo, BARE_URL).returncode != 0

    def test_the_calling_card_footer_passes(self, tmp_path):
        """Positive control: the sign-off the guard is steering people towards."""
        repo = _repo(tmp_path)
        install_dispatcher(repo)
        r = _commit(repo, CLEAN)
        assert r.returncode == 0, r.stderr
        log = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%B"],
                             capture_output=True, text=True).stdout
        assert "AgentMacEff@abc123" in log

    def test_a_commented_out_line_is_not_a_hit(self, tmp_path):
        """git's own template lines start with '#' and are stripped before the
        message is stored; the guard must not refuse a message over them."""
        repo = _repo(tmp_path)
        install_dispatcher(repo)
        r = _commit(repo, "feat: x\n\n# Claude-Session: https://claude.ai/code/session_01ZZZZ (template noise)\n")
        assert r.returncode == 0, r.stderr

    def test_the_portable_copy_is_byte_identical_to_the_canonical_one(self, tmp_path):
        repo = _repo(tmp_path)
        install_dispatcher(repo)
        canonical = DISPATCHER.parent / "portable" / "commit-msg.d" / "10-no-session-url"
        installed = repo / ".git" / "hooks.local.d" / "commit-msg.d" / "10-no-session-url"
        assert installed.read_bytes() == canonical.read_bytes()

    def test_every_dispatched_hook_is_the_same_dispatcher(self):
        """The bash-3.2 audits above read only pre-commit. A second stage that
        drifted from it would pass every audit while being a different program."""
        from macf.githooks import DISPATCHED_HOOKS
        for hook in DISPATCHED_HOOKS:
            assert (DISPATCHER.parent / hook).read_bytes() == DISPATCHER.read_bytes(), hook


class TestPrivateReferencesAreRefused:
    """A message that points a public reader at the author's roadmap phases, task
    or idea numbers is refused; the calling-card footer line is not a reference."""

    def _guard(self, tmp_path):
        repo = _repo(tmp_path)
        install_dispatcher(repo)
        return repo / ".git" / "hooks.local.d" / "commit-msg.d" / "20-no-private-refs"

    def test_phase_and_task_references_are_refused_and_named(self, tmp_path):
        guard = self._guard(tmp_path)
        msg = tmp_path / "m"
        msg.write_text("feat: x\n\nPhase 4 of the ROLE system (roadmap task #242), on top of #376.\n")
        r = subprocess.run(["bash", str(guard), str(msg)], capture_output=True, text=True)
        assert r.returncode == 1
        assert "cannot find" in r.stderr and "Phase 4 of the ROLE system" in r.stderr

    def test_the_footer_and_pr_numbers_pass(self, tmp_path):
        guard = self._guard(tmp_path)
        msg = tmp_path / "m"
        msg.write_text("feat: x\n\nFourth in the series, on top of #376. See roles.md.\n\n"
                       "[IraMacEff@ee9a78: task#242 s_abc12345/c_40/p_x/t_1]\n")
        r = subprocess.run(["bash", str(guard), str(msg)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    @pytest.mark.parametrize("line", ["idea #247 is not here", "sprint #245 closed", "see the roadmap folder",
                                      "Phase 2. Duties rank themselves", "MISSION #238 owns it", "in cycle 40 we"])
    def test_each_private_vocabulary_shape(self, tmp_path, line):
        guard = self._guard(tmp_path)
        msg = tmp_path / "m"; msg.write_text(f"feat: x\n\n{line}\n")
        assert subprocess.run(["bash", str(guard), str(msg)], capture_output=True, text=True).returncode == 1
