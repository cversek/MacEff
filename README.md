# MacEff

Infrastructure that lets an LLM coding agent keep working coherently across the
things that normally break it: a context window that fills up, a summarisation
pass that discards most of the conversation, a session that restarts, a
delegation that returns and remembers nothing.

**Alpha.** APIs move. Expect rough edges and file issues.

## Two names, one system

The repository is **MacEff** — *Multi-agent Containerized Environment for
frameworks* — and it contains two layers whose names differ by one letter and
are routinely confused.

**MACF**, *Multi-Agent Coordination Framework*, is the portable Python package:
`macf_tools`, the lifecycle hooks, and the policy corpus. It depends on no
container and runs anywhere an agent runs — on a host, in someone else's Docker
image, inside any project.

**MacEff** proper is one deployment built on MACF: Docker containers with an
isolated home per Primary Agent, SSH access for agent sessions, a shared
workspace, and volume management for the artifacts agents write.

MACF is the library; MacEff is an implementation that uses it.

That distinction decides which half of this repository you want. Everything below
is MACF on a host, which needs no container and is where most people should
start. The container environment is in
[docs/container-setup.md](docs/container-setup.md).

## What problem it actually solves

An agent's context window fills, and the host compacts it — replacing the
conversation with a summary written by something that was not there. The agent
carries on with no signal that anything happened.

MacEff makes that boundary visible and survivable. Hooks detect the compaction
and tell the agent it occurred. State that matters is carried across explicitly,
with provenance. Work is tracked in files that outlive the context that created
them, so what survives is a record rather than a summary.

Everything else in the project follows from that: temporal awareness because an
agent cannot otherwise tell how long it has been working; a task system because
untracked work dies with the context; policies loaded on demand because a
preamble large enough to hold them would consume the window it is protecting.

The longer argument, including the stance on agent "consciousness" and why it is
deliberately a pragmatic one, is in [docs/philosophy.md](docs/philosophy.md).

## Requirements

- Python 3.10 or newer
- git
- Claude Code, for the hook integration (the CLI works without it)

Developed on macOS and Ubuntu.

## Install

```bash
git clone https://github.com/cversek/MacEff.git
cd MacEff
python3 -m venv .venv && source .venv/bin/activate
pip install -e ./macf
```

Confirm it landed:

```bash
macf_tools --version
```

```
macf_tools 0.6.1.dev0 (main @ 54f1899)
```

Both halves of that line track your checkout rather than this document, so
expect different values. `main` between releases carries a development version;
a release tag carries a plain one like `0.6.0`. The git hash follows, so a
deployed build says exactly which commit it is, and a working tree with
uncommitted changes adds `dirty`. Installed from a wheel rather than a checkout,
there is no suffix at all.

## Run something

```bash
macf_tools env
```

Prints where the agent thinks it is: agent id, whether it is supervised, the
paths it will read and write, the versions in play. This is the command to run
first when something is behaving oddly, because most surprises turn out to be a
path resolving somewhere unexpected.

```bash
macf_tools context
```

Token usage and context left, as a percentage. `CL 20` means a fifth of the
window remains.

```bash
macf_tools policy list
```

The policies available to the agent. They are not preloaded — the agent reads
one when it needs it:

```bash
macf_tools policy navigate testing     # the questions this policy answers
macf_tools policy read testing --section 1.1
```

`navigate` prints section headings phrased as questions, so an agent can find the
part it needs without reading the whole document. That indirection is the point:
the policy corpus is far larger than any context window that could hold it.

## Hooks

```bash
macf_tools hooks install --local
```

Installs eleven lifecycle hooks into `.claude/settings.json`. They fire on
session start, prompt submit, before and after each tool call, on stop, on
subagent start and stop, before compaction, and on session end.

What they do, in one line: inject the agent's own current state into its context
— time, context remaining, active modes, recent policy guidance — and record what
happened to an append-only event log.

```bash
macf_tools hooks logs      # what fired, and when
macf_tools events query    # the event log itself
```

The event log is the source of truth. State is derived from it rather than stored
separately, which is why there are no state files to go stale.

## The task system

Work an agent does without recording it dies when the context does. This is the
part of MacEff that most changes how a long-running agent behaves, so it is worth
showing rather than describing.

Orientation — what exists and where it stands:

```console
$ macf_tools task tree 1279 --succinct
🌳 Task Tree from #1279 (19 tasks)
============================================================
◼ #1279 🗺️ MISSION: MacEff v0.6 release: consolidate the test... [MacEff 0.6.0] 08/28 23:11 C527
├── ◻ #1283 [^#1279] 📋 Split on live external state, then clos... 08/29 12:26 C527
│   └── ◻ #1298 [^#1283] 🔀 PR/cversek/MacEff#340: purge(sidecar): remove a feature ... 08/29 15:12 C527
├── ◼ #1287 [^#1279] 📋 README overhaul (operator approval gate) 08/29 17:10 C527 👈 2h
└── ◻ #1288 [^#1279] 📋 Changelog and release 08/29 11:50 C527
```

That is this release, tracked in the system it ships. A MISSION with phases
under it, a pull request tracked as its own task under the phase that produced
it, and `👈` marking where work last happened.

Task types carry their own metadata and their own completion rules — a
`🐙 GH_ISSUE` fetches its labels and state from GitHub, a `🔀 GH_PR` records
MERGED or CLOSED_UNMERGED and can complete the issue tasks it closes.

### Why it is more than a to-do list

Drop `--succinct` and a phase shows its full record:

```console
$ macf_tools task tree 1279
├── ✔ #1281 [^#1279] 📋 Consolidate four test locations into one 08/29 10:10 C527
│      → agent/public/roadmaps/2026-08-28_MacEff_v0_6_release_cons...
│      📝 PHASE 2 TRIAGE — measured, and two of the roadmap's own c...
│      📝 PHASE 2 — RETRACTION of my own claim, caught by measuring...
│      📝 PHASE 2 DECISION — PORT, do not delete. The measurement s...
│      📝 PHASE 2 — DOWNGRADING my own "the suites interfere" claim...
│      ✅ Work done: consolidated four test directories into one. M...
│   └── ✔ #1293 [^#1281] 🔀 PR/cversek/MacEff#331: test: consolidate the suite... 08/29 10:10 C527
│          → https://github.com/cversek/MacEff/pull/331
│          ✅ Merged as 6515b70 after CI green on test (3.10), test ...
```

Four things are visible there, and each exists for a reason:

- `→` a **plan reference**. The phase points at the roadmap that authorised it,
  so an agent picking the work up cold reads the intent before acting.
- `📝` **notes written while the work happened**, not reconstructed afterwards.
  Two of those are the agent retracting its own earlier claims mid-phase. A note
  deferred until completion is a note that does not exist if the context is lost
  first.
- `✅` a **completion report** — what was done, what was verified, what was left.
  Required; the CLI refuses to complete a task without one.
- The nesting: the PR that delivered the phase is a task in its own right,
  carrying its merge commit and the CI evidence.

### The stack

```console
$ macf_tools task trace
🧵 Open frames: 2 (0 awaiting a return)
   📂 #1279   enclosing  last touched 20h
   ▶️  #1287   active     last touched 2h
```

A tree of open tasks says several things are unfinished. The trace says which one
attention actually left, and classifies the rest: **active** (here now),
**enclosing** (work is proceeding one level down — not a dropped frame),
**parked** (waiting on a declared blocker), **ready** (that blocker has since
cleared), **deferred** (set down, nothing blocking it).

The distinction matters after a discontinuity. An agent resuming from a
compaction has to know which frame it owes a return to, and a detector that
reports a parent as "dropped" whenever a child is running would cry wolf every
time work was decomposed properly.

Work last touched in an earlier cycle triggers a resume protocol: the CLI reports
how stale it is and requires the history to be re-read before continuing, because
the context that made it legible is gone.

## Where things are

| | |
|---|---|
| [`macf/docs/user/`](macf/docs/user/) | CLI reference, configuration, hooks, identifiers |
| [`macf/docs/maintainer/`](macf/docs/maintainer/) | architecture, event sourcing, task internals |
| [`framework/policies/base/`](framework/policies/base/) | the policy corpus, also readable via `macf_tools policy` |
| [docs/philosophy.md](docs/philosophy.md) | the argument behind the design |
| [docs/container-setup.md](docs/container-setup.md) | the Docker demo environment, compose overrides, Make targets |
| [CHANGELOG.md](CHANGELOG.md) | what changed, and when |

## Contributing

```bash
make test        # the fast hermetic suite
make test-live   # tests needing tmux, systemd, or a real client
```

The suite is split because a test whose result depends on what is installed on
the machine is a different kind of test from one that does not. `make test` is
hermetic: its outcome is identical whether or not tmux is present, and that
equality is checked rather than assumed.

Install the commit gates before your first commit:

```bash
macf_tools githooks install
```

A dispatcher that runs a directory of checks and **adopts** any pre-existing hook
rather than overwriting it. Currently: a silent-exception scanner and a style
ratchet whose finding counts may shrink and must not grow.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Status

Alpha, developed in the open. It is used daily by the agents that build it, which
is the main reason its rough edges get found — most of what this release fixed
was discovered by the framework being pointed at itself.

Issues and experience reports are genuinely useful:
https://github.com/cversek/MacEff/issues
