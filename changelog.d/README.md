# changelog.d: one CHANGELOG fragment per pull request

A pull request does not edit `CHANGELOG.md`. It adds its entry here, as a new file, and the
fragments are gathered into `CHANGELOG.md` at release (`python tools/changelog_gather.py --write`).
No two pull requests touch the same file, so merging one never puts the others into conflict.
The rule and its reason are in policy `release_workflow` §3.5.

**Name** the file after the branch, with `/` as `-`, e.g. `fix-session-unit-reap.md`.

**Write** a category heading, then the entry, in the CHANGELOG's own style:

```markdown
### Fixed

- **What changed, in plain words** (`module.py`, policy `name` §N): why, and what it means for a reader.
```

Categories: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. A fragment may
hold more than one. `python tools/changelog_gather.py` (without `--write`) checks every
fragment and changes nothing.
