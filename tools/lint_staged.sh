#!/bin/bash
# MacEff Python style gate, on STAGED content only.
#
# THIS FILE IS VERSIONED ON PURPOSE. A gate that lives only in .git/hooks does
# not travel to another clone, so every checkout would silently have no gate --
# a control whose absence is invisible, which is the failure this project keeps
# finding. The hook is a two-line shim that calls this; the rule lives here.
#
# WHY A BLOCKING SUBSET RATHER THAN THE WHOLE CONFIG. ruff.toml selects
# everything we intend to hold to; this blocks only the rules whose violation
# count is ZERO across the repo. A gate that fires on pre-existing debt gets
# --no-verify'd on its first day, and the habit then swallows the true
# positives too. Zero-count rules are pure ratchets: they can only ever fire on
# something newly introduced.
#
# TO PROMOTE A RULE: burn its count to zero (`ruff check --select RULE .`), then
# add it to BLOCKING below. That is the intended direction of travel, and the
# debt is recorded rather than left to be rediscovered.

set -uo pipefail

BLOCKING="E722,F821"
#   E722  bare except      -- policy calls it FORBIDDEN
#   F821  undefined name   -- a NameError waiting for its branch to execute.
#                            Five real ones were found the day this was written,
#                            including `sys` used in two error handlers of a
#                            module that never imported it: the stderr warning
#                            path raised instead of warning.

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$REPO_ROOT" || exit 0

# Staged, still-present Python files. ACMR excludes deletions -- linting a file
# that is being removed would block a commit over code that will not exist.
# A read loop rather than `mapfile`, which DOES NOT EXIST in bash 3.2 -- the
# version macOS ships and will keep shipping, and the one this file's shebang
# names. Under `set -u` the failure was not even a clean error: mapfile printed
# "command not found", FILES stayed unset, and the very next line aborted on an
# unbound variable. So on a Mac this gate exited non-zero for a reason having
# nothing to do with the code being committed, which is the fastest possible
# route to habitual --no-verify.
#
# `${#FILES[@]}` on an empty array is safe on 3.2; only a VALUE expansion
# `"${FILES[@]}"` aborts there, and the early exit below means the expansions
# further down are never reached empty.
FILES=()
while IFS= read -r f; do
  [ -n "$f" ] && FILES+=("$f")
done < <(git diff --cached --name-only --diff-filter=ACMR -- '*.py')
[ ${#FILES[@]} -eq 0 ] && exit 0

if ! command -v ruff >/dev/null 2>&1; then
  # REFUSE RATHER THAN SKIP. "ruff is not installed" and "the code is clean"
  # must not look the same from outside, or the gate silently stops running and
  # nobody learns that it did.
  echo "[lint] ruff is not installed -- refusing to commit unchecked."
  echo "[lint] install it:  python -m pip install 'ruff>=0.6'"
  exit 1
fi

echo "[lint] checking ${#FILES[@]} staged Python file(s) against ${BLOCKING}..."
if ! ruff check --force-exclude --select "$BLOCKING" -- "${FILES[@]}"; then
  echo
  echo "[lint] commit BLOCKED. These rules are at ZERO across the repo, so a"
  echo "[lint] finding here is something this change introduced."
  echo "[lint] override (only for a genuine false positive, and say why):"
  echo "[lint]   add '# noqa: <CODE> - <reason>' at the site, or git commit --no-verify"
  exit 1
fi

# The rest of the selected set is REPORTED, never blocking. Saying the number
# out loud keeps the debt visible; hiding it is how a linter comes to be
# believed to cover more than it does.
DEBT=$(ruff check --force-exclude --statistics -- "${FILES[@]}" 2>/dev/null \
       | awk '{s+=$1} END{print s+0}')
if [ "${DEBT:-0}" -gt 0 ]; then
  echo "[lint] ${DEBT} non-blocking finding(s) in these files (ruff check .) -- not gating."
fi

# ---- MacEff rules ruff cannot express ---------------------------------------
# These have real backlogs, so a zero-count gate is unavailable; the ratchet
# blocks only an INCREASE. Run repo-wide because the counts are repo-wide --
# and only when Python is staged, since nothing else can move them.
STYLE="$REPO_ROOT/tools/style_check.py"
if [ -x "$STYLE" ]; then
  "$STYLE" || exit 1
fi

exit 0
