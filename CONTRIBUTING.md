# Contributing to MacEff

## Before your first commit: install the checkers, then automate them

```bash
pip install -e "./macf[lint,test]"     # note the lint extra — ruff lives there
```

### Let the hook run them, not your memory

**Strongly recommended: run the gates from a pre-commit hook rather than by hand.** A checklist
you have to recall at the right moment is the tier of enforcement that fails — it is the exact
tier `ruff.toml` was written to move these rules *down* from. If your discipline is the
mechanism, the gate is advice.

```bash
tools/lint_staged.sh                   # what the hook should run — try it directly first
```

`tools/lint_staged.sh` is versioned on purpose and is designed to be called from a two-line
shim in `.git/hooks/pre-commit`, so the rule travels between clones and only the trigger is
local.

⚠️ **This repository already has a `pre-commit` hook — the OPSEC scanner.** Do not overwrite it;
it is a security control that keeps private research out of a public repo. Until the framework
ships a composable installer (#286), add the lint call to the existing hook rather than
replacing it, and check what is there first:

```bash
cat .git/hooks/pre-commit               # look before you write
```

Run the gates manually until your hook is in place:

```bash
ruff check . --select F821,E722        # the blocking rules — must stay at zero
tools/style_check.py                   # the MACEFF ratchet — counts must not go up
```

### Escape hatches, and when they are legitimate

Automation without an exit is how a gate gets uninstalled instead of satisfied. There are three,
in order of preference:

| situation | do this |
|---|---|
| a finding is genuinely justified | `# noqa: <CODE> - <reason>` **at the site** — the exception is then auditable and travels with the code |
| mid-rebase, WIP commit, or a hook that is itself broken | `git commit --no-verify`, and say why in the commit message |
| the gate blocks work it should not | **file it** — a gate you cannot satisfy legitimately is a bug in the gate |

That last row is the one that matters. An unsatisfiable gate teaches everyone to reach for the
override, and the habit does not stay confined to the false positives — it swallows the true
ones too. If `--no-verify` is becoming routine, that is a defect report waiting to be written,
not a workflow.

### Why two gates

They enforce different things by different mechanisms, and the split is deliberate.

**`ruff.toml` — a zero-count ratchet.** A rule blocks only once its violation count reaches
zero, at which point it can fire on nothing but a new introduction. `F821` (undefined name)
and `E722` (bare except) are there today. Everything else in the `select` list is reported
debt, visible via `ruff check .`, waiting to be burned down and promoted.

**`tools/style_check.py` — a baseline ratchet.** The MACEFF rules are custom AST checks for
principles ruff cannot express, and they have real backlogs, so a zero-count gate is
unavailable. `tools/style_baseline.json` records the count per rule and the commit is refused
if any count goes **up**. The debt is visible, cannot grow, and shrinks whenever someone
touches a site.

Both directions of travel are the same; the starting conditions differ.

### Import success is not the check

`python -c "import macf"` proves a module loads. It says nothing about whether names inside
function bodies resolve — those are runtime `NameError`s, and in a hook handler they fire on
every tool call.

This is not hypothetical. A refactor of the mode functions passed a smoke-import while four
hook handlers and one CLI call site had an undefined name, because the transform assumed five
"identical" handlers shared one import shape and they have four different ones. `F821` catches
that class; importing does not. **Run the linter, not just the interpreter.**

### If a gate blocks you

- **`F821` / `E722`** — these are at zero on purpose. A new one is a real defect; fix it rather
  than suppressing it.
- **A MACEFF count went up** — find it with `tools/style_check.py --report | grep <CODE>`. If
  the new site is genuinely justified, suppress it *at the site* with
  `# noqa: <CODE> - <reason>` so the exception is auditable.
- **A count went up and you did not write it** — check whether the finding is in a file git
  tracks. The ratchet currently walks directories rather than the tracked set, so untracked
  local work under `macf/src`, `macf/tests` or `docker` is charged as new debt (#284).

Never reach for `--no-verify`. A gate you cannot satisfy is a bug in the gate — file it.

## Testing

```bash
pytest macf/tests -q
```

Two things about the suite that are easy to get wrong:

**Isolate at the boundary, not by patching symbols.** Patching named write functions covers the
paths you predicted; a path you did not predict reaches the real store while the test passes.
Test isolation goes through environment variables (`MACF_TASKS_DIR`, `MACF_TASK_STORE_DIR`,
`MACF_EVENTS_LOG_PATH`, `MACEFF_AGENT_HOME_DIR`) — an environment variable has no escape path.
`conftest.py` applies these automatically; a test that needs a specific backend overrides them
explicitly rather than working around them.

**A test that has never failed is an assumption.** Before trusting a new guard, break the thing
it guards and watch it go red. A control that is green because the code beneath it never runs
is worse than no control, because it is also a claim.

## Where things live

| what | where |
|---|---|
| Package source | `macf/src/macf/` |
| Tests | `macf/tests/` |
| Framework policies (the spec) | `framework/policies/base/` |
| Maintainer docs | `macf/docs/maintainer/` |

Policies are read with `macf_tools policy navigate <name>` then `macf_tools policy read <name>`
— the CEP navigation guide is organised by question rather than keyword, so navigate before
searching.

**Policy is the spec.** For anything with a governing policy, write the specification first and
reconcile the implementation against it afterwards; the reconciliation catches real drift.

## Commits and pull requests

- One logical change per commit. The message explains **why**, since the diff already shows what.
- Reference the issue: `Fixes #N`.
- Green CI on all supported Python versions before merge.
- Squash-merge with `--delete-branch`.

Note that CI runs `ubuntu-latest` only, matrixed over Python versions. macOS-specific breakage
is green in CI by construction, so if you develop on a Mac your local run is not redundant with
CI — a disagreement between the two is itself the finding, whichever side is green.
