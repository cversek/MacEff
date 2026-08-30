# Changelog

All notable changes to MACF Tools (Multi-Agent Coordination Framework) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet. Changes land here as they merge, so the next release is described
as it is built rather than reconstructed from the log afterwards.

## [0.6.0] - 2026-08-29

### Summary

Consolidation release. The task system becomes a **work stack** — `task trace` reports which frame attention actually left rather than merely listing what is unfinished, completion hands attention back to the enclosing frame, and starting a phase cascades its pending ancestors — and gains a **project-scoped home task store**, so task history survives the session-UUID churn of fork, rewind, and continue instead of being copied and diverging. **GH_PR tasks** close the loop from issue to merged pull request, with a CI-green merge gate and a ground-truth MERGED / CLOSED_UNMERGED outcome that cascades to the issue tasks the PR closes. **USER_REMOTE** makes driving an agent from a chat channel viable by refusing the tools that would otherwise hang waiting for a terminal nobody is watching. The **knowledge web** becomes its own module with a corpus doctor that finds artifacts nothing can reach. A **pre-commit dispatcher** composes independent gates and adopts any hook already installed rather than overwriting it. Autonomous work splits into **SPRINT** (workload-defined) and **PLAY_TIME** (timer-bounded), which had been one overloaded concept. And the test suite was consolidated from four locations into one, split into a hermetic set and a live set by marker, and stripped of `xfail` tombstones that had outlived their reason by two minor versions. 280 commits since v0.5.0.

### Added

**Work stack and task lifecycle** (`macf_tools task`):
- `task trace` — the open-frame stack, classifying each frame as active, enclosing, parked, ready, or deferred, so a parent whose phase is running is not reported as a dropped frame
- Attention handed back to the enclosing frame when a task completes, and a message when the last child closes
- `task start` cascades pending ancestors on every start path, and reports what it started
- Stale-resume banner: work last touched in an earlier cycle names how stale it is and requires its history to be re-read before continuing
- Guard against completing a task over open children
- `task reparent` / `advance` / `set-custom` verbs
- `task doctor` — reconciles GitHub-backed tasks against live GitHub, and names structural faults such as a task parented to a non-root
- Last-touched recency marker in the tree, with a touch-discipline nag

**Home task store**:
- Optional project-scoped task store under the agent home, divorced from the session-keyed `~/.claude/tasks/`
- `task migrate-store` — one command from the legacy store to the home store
- Provisioning creates the store, rather than leaving an agent to opt in
- `task tree --loop` watches the resolved store, not the legacy session root

**GH_PR task type**:
- Inbound pull-request review and merge tracked as a first-class task type (🔀), with kind-aware URL parsing and metadata fetched from the host
- Completion records the ground-truth outcome (MERGED or CLOSED_UNMERGED) and cascades to the GH_ISSUE tasks the PR closes
- CI-green policy gate on merge, with the resolution path stated when the check is red
- GH_ISSUE close-out calling card is opt-in, and respects public-attribution settings

**Presence and modes**:
- `USER_REMOTE` presence mode — denies CLI-blocking tools so a remotely driven session cannot hang on a prompt nobody can see, with automatic permission restore and non-hanging housekeeping
- The transcript monitor mirrors the live exchange to the channel while USER_REMOTE is active
- SPRINT (workload-defined) and PLAY_TIME (timer-bounded) as separate autonomous-work types, with their own task types, models, CLI verbs, skills, and stop-hook dispatch
- Behavioral-reinforcement message on every mode transition
- AUTO_MODE requests the client's own auto mode and records the request where it can be audited

**Knowledge web** (`macf_tools knowledge`):
- Extracted into its own module; participation is emergent from wiki-links, with no registry to keep in sync
- `knowledge doctor` — a corpus doctor that finds orphans, drift, and undeclared artifact directories, answering the question `gaps` structurally cannot
- Node semantics and orphan prevention specified in policy, and all 39 substantive policies retrospectively annotated into the web
- Wiki-link flags on `idea create` and `idea update`; archived ideas excluded from gap suggestions

**Observability** (`macf_tools events`):
- Structured warnings framework with dual-channel emission, replacing scattered stderr writes
- `HookMessage` / `emit_message` for CLI-to-channel parity, and concise tool-invocation summaries
- `events analyze` — a generic structured-event JSONL analyzer
- Per-request byte accounting and a per-block census in the proxy
- SubagentStart hook as a parallel-safe bridge between tool-use id and agent id for delegation timing

**Commit gates** (`macf_tools githooks`, `macf_tools opsec`):
- A pre-commit dispatcher that runs a directory of independent checks and adopts any pre-existing hook instead of overwriting it
- A style ratchet whose finding counts may shrink and must not grow
- `opsec install-hook` — a gate against private-context leakage in a public tree

**Configuration and provisioning**:
- Unified config layer with a config-layer slot in identity resolution
- Declarative deployment environment via `agents.yaml` `defaults.container_env`
- Declarative account flavor, multi-key SSH, and vanilla-purity options for provisioned agents
- Declarative per-uid egress capability boundaries, with the policy that explains them
- Declared channel plugins installed and kept current at container start
- Idempotent tool install behind a fingerprint sentinel, so a warm restart skips reinstallation
- An `amail` mailbox created for every agent at init, with the protocol specified before the client was built

**Harness**:
- The persistent agent harness is generated from declarations rather than hand-edited
- One launch implementation, identity-derived session names, and failures that report what actually went wrong

**CLI and shell**:
- `macf_tools inject` — self-directed session control
- `macf_tools env set-term-title`, and `task tree --loop` auto-titling with the agent calling card
- `--title-width` for trimming long titles in the tree
- Seek-from-end line iterators for large transcripts, fixing a Stop-hook out-of-memory failure
- Configurable keys sent after every supervised child spawn; per-user auto-restart registries; singleton pre-flight that refuses to fork a live calling card

**Policies**:
- `public_voice` — writing standards for text leaving the agent's own tree
- `instruction_language` — foundational principles, grammar shape, and service model, with an interpreter skill
- `coding_standards` §7 — Derived State Discipline
- `mode_system` §13 Nag Design, and §14 stating which modes a subagent actually has a stance about
- `amail` — the agent mail protocol
- Maintainer principles, sorted by layer, with the framework layer seeded
- Cycle-scoped event queries with persistent state carried forward explicitly, rather than inferred

### Changed

- Scope is event-sourced only; the MTMD `scope_status` field was retired, and tree and list markers now read from the event log
- The test suite runs from one location, split by marker into a hermetic set (`make test`) and a live set requiring tmux, systemd, or a real client (`make test-live`)
- The README was rewritten from 916 lines to 265, with philosophy and container setup extracted into their own documents
- Proxy message rewriting is gated behind `MACF_PROXY_REWRITE` and defaults to off
- Mode detection reports what it actually knows, rather than presenting a default as a determination
- A nav guide surfaces once per cycle rather than once per task start
- `aiohttp`'s 1 MiB default body limit was raised in the proxy, which had been rejecting real conversations
- User activity is derived from the prompt-submit payload rather than a poller
- The full operator prompt is captured, not its first 200 characters

### Removed

- The hook sidecar: a writer that shipped in 2025 with zero call sites, never gained one, and whose reader had been reporting its absence as a fact about hooks — along with the documentation that supplied a plausible wrong cause for the symptom
- The `archive` / `restore` / `archived` CLI trio, which failed closed rather than reporting false success
- The per-prompt policy-recommendation injection
- `utils/cycles.py`, dissolved into its callers
- The superseded `maceff-autonomous-sprint` skill, deleted rather than deprecated
- The deprecated `todo_hygiene` policy
- Every `xfail` marker citing the v0.4.0 removal of the TODO system, including two whose tests were passing

### Fixed

105 issues fixed since v0.5.0, plus one closed as a duplicate. Grouped by what they affected:

**Task system**:
- **#68**, **#70**: inconsistent task-id argument parsing across verbs; a misleading scope count with a spurious expansion line
- **#69**: `task create sprint --children` silently dropped the first child
- **#79**: completing a GH_ISSUE task closed the upstream issue before its PR merged
- **#148**, **#273**: `task reparent` left a stale parent marker in the subject, and orphaned on parent 0
- **#150**, **#289**, **#295**: the recency marker vanished in succinct mode; `--loop` hid tasks completed since it started; an archived descendant pinned its whole ancestor chain visible
- **#208**: `task create --parent 0` was accepted and orphaned the task outside the tree
- **#212**: starting a child of an unstarted parent now cascades upstream and says so
- **#255**: sprint completion synthesis counted children, reporting 0/3 for a scoped sprint
- **#261**: "abandoned" misnamed deliberate deferral, and hid which frames were still owed a return
- **#267**: the touch-discipline nag watched the legacy store and never reset under the home store
- **#268**: nothing was said when the last child closed and the parent still needed attention
- **#269**: a task with an unsatisfied `blocked_by` started anyway, so a declared dependency did not hold
- **#274**: `task hide-completed` was not idempotent and reported phantom counts
- **#306**: a running sprint was not in its own scope, so SPRINT mode was not in force for it
- **#125**, **#48**: a `NameError` crashed the protected-field guidance in `task edit`, and another crashed `task list` outright
- **#112**: no correct path existed for reparenting, advancing a lifecycle, or nesting — now `reparent` / `advance` / `set-custom`
- **#272**: the task-creation commands had no callers, leaving the phase policy-engagement requirement unreachable from every path

**Modes and presence**:
- **#53**: a client-side name collision blocked AUTO_MODE activation
- **#56**: the recommender hardcoded one agent's skill prefix
- **#67**: AUTO_MODE installed ask-list entries without auditing existing allow-list shadows
- **#72**: a gendered runner emoji replaced with a gender-neutral one
- **#50**: the PreToolUse mode dashboard lagged a tool call behind `mode set-work`
- **#181**, **#266**, **#301**: idle detection reported the user idle on the very prompt they had just sent, did not reset on permission-dialog activity, and disengaged once 200 agent events buried the user's last input
- **#275**: AUTO_MODE now hands the permission decision to the client's native auto mode
- **#279**: `utils/cycles.py` dissolved into the module that owned its functions
- **#294**, **#325**: the PA preamble taught modes as a two-value post-compaction checkbox; the SA preamble had no mode awareness at all, and the PA block could not simply be copied into it
- **#302**, **#309**: a bounded event scan's miss was being read as a fact at five sites; event queries are now cycle-scoped by default with cross-cycle state carried explicitly

**Hooks and session**:
- **#54**: the transcript-monitor daemon inherited the caller's pipe and hung `mode set` for ~90s
- **#65**: the Stop hook's scope-gate logic was indented inside a failsafe early-return, making it dead code
- **#66**: autocompact settings were written to a path the client had stopped reading
- **#82**: bare-`cd` detection missed every command fragment after the first
- **#89**: hook lookup used relative paths, so a bare `cd` in agent Bash could kill all hooks for the session
- **#92**, **#93**: hook warnings had no delivery framework; now structured and dual-channel
- **#94**: the Stop hook was OOM-killed at high context use by unbounded transcript and event-log reads
- **#110**, **#111**, **#118**: the context meter reported stale pre-compaction usage, scanned a tail that missed preserved-segment replays, and raced its own first post-compaction write
- **#116**: a `claude` substring match executed an unrelated binary during version detection on Linux, and forked in a loop
- **#154**: a PreToolUse deny also set `continue: false`, halting the agent instead of the tool call
- **#158**: session-id resolution let a concurrent session hijack the identity
- **#163**, **#165**, **#264**: notifications did not name the invoked skill; the SessionStart banner lacked an AUTO_MODE indicator and was silently dropped when the monitor cold-started
- **#271**: policy nav-guide injection fired per task start rather than once per cycle

**Configuration, identity, and provisioning**:
- **#96**: a unified config layer with environment-variable overrides
- **#115**: the AUTO_MODE auth token had no install path off Docker and its validation was bypassable
- **#120**, **#121**: a duplicate `config` subparser crashed the CLI on newer Pythons, and pydantic was a runtime dependency declared only under test extras
- **#131**, **#180**, **#283**: `agent init` never minted the agent id so identity resolved to a placeholder, later minted one that shadowed an existing global identity, and its preamble upgrade appended without removing the old version
- **#153**: preamble upgrades grew the file on every run
- **#252**: two agent-home resolvers disagreed, and the isolation fixture only patched one
- **#64**: subagent directories were created root-owned and 0700 in containers, blocking delegation
- **#258**: container deployments had no working path to start a supervised agent session
- **#280**: the init overlay was a fixed list, so anything a deployment declared outside it was dropped
- **#299**: provisioning models silently discarded unknown keys, so a declared capability could vanish without error

**Proxy, supervisor, and harness**:
- **#159**: the supervisor registry was not per-user, so a second agent on a host collided with the first
- **#161**, **#167**: the ad-hoc daemon and the systemd unit were not mutually exclusive; aiohttp's 1 MiB default body limit was silently rejecting real conversations
- **#162**: request-size telemetry with opt-in rolling capture
- **#164**: no post-restart hook, so a trust prompt on relaunch hung unattended
- **#209**, **#210**: harness status guessed the agent name, and an agent had no supported way to restart its own session
- **#27**: the auto-restart supervisor entered a crash loop under some terminals, from job-control signalling
- **#25**, **#46**: the channel plugin fork had drifted from its upstream, and its server log grew unbounded — 191 GB in three weeks, nearly filling a disk

**Knowledge web**:
- **#73**: the cross-CA graph indexed only ideas, ignoring learnings, checkpoints, and reflections
- **#87**: the graph builder ignored `wiki_links` in idea JSONs
- **#109**, **#124**: wiki-link flags on `idea create` and `idea update`

**Tests and CI**:
- **#123**: a flaky session test that relied on `sleep()` for ordering
- **#241**: the tmux helper stripped PATH from its subprocess environment, breaking seven tests on macOS
- **#247**: the sprint suite wrote into the live task store
- **#254**: one flake's race removed, and the other made diagnosable
- **#282**, **#284**: the style gate was declared blocking and wired into nothing; the ratchet charged gitignored local work as new findings
- **#318**: four harness-render tests read live machine state, so they failed locally and passed in CI
- **#328**: the test suite spawned a real client that inherited live credentials and killed the developer's channel

**Documentation and policy**:
- **#52**: `framework install` reported hooks installed while writing an empty config
- **#55**: an ambiguity about how many scoped sprint tasks may exist
- **#63**: stale command-namespace references across framework commands and docs
- **#71**: three small UX nits in install output and skill text
- **#113**: `markdown present` failed silently when the HTML handler was hijacked
- **#242**: `macf_tools time` appended a checkpoint line to stdout, breaking its documented single-timestamp contract
- **#156**: the GH_ISSUE close-out comment leaked agent attribution to public issues
- **#211**: the per-prompt policy-recommendation injection removed in favour of on-demand search
- **#244**: per-agent breadcrumbs removed from shared policy headers
- **#259**: EXPERIMENT and ROADMAP disambiguated up front rather than at the comparison
- **#262**: artifact delivery assumed a local browser, which reaches nobody over SSH or a channel
- **#270**: the checkpoint policy had no recovery reading list and a template prescribing summaries
- **#276**: maintainer principles categorised by layer, with the framework layer seeded
- **#286**: git hooks provisioned composably, by a dispatcher that adopts pre-existing hooks
- **#287**: work a sprint generates needs a task at the moment of filing
- **#339**: `hooks status` reported an empty result because nothing called the writer, not because nothing had happened

## [0.5.0] - 2026-04-20

### Summary

Major release introducing the **Markov Mode System** with 5-mode recommender and autonomous sprint lifecycle, **Knowledge Web & Ideas** with cross-CA wiki-links and graph visualization, **Voice Services** with mlx-whisper transcription and domain correction, **Task Scope System** for AUTO_MODE boundary enforcement, **Markdown & Graph Visualization**, **Telegram channel integration**, **auto-restart process supervisor**, **GitHub issue tracking**, **CI/CD pipeline**, and **1M context window support**. 205 commits since v0.4.0.

### Added

**Markov Mode System** (`macf_tools mode`, `macf_tools recommender`):
- Core mode detection with 8-mode operational model (AUTO_MODE, USER_IDLE, QUIET_MODE, LOW_CONTEXT) + 5 work modes (DISCOVER, EXPERIMENT, BUILD, CURATE, CONSOLIDATE)
- Markov transition model with Monte Carlo sampling for work mode recommendations at gate points
- PreToolUse emoji dashboard showing active modes (`🤖😴🔕🪫 🔍🧪🔨📋✍️`)
- Transcript Monitor daemon for JSONL event detection (idle detection, content-replacement, rewind)
- 4 motivation skills for self-directed mode transitions
- Autonomous sprint policy with timer discipline and two-gate stop mechanism
- `mode show|set-work|unset-work|list` CLI commands
- `recommender show|sample` CLI commands
- AUTO_MODE indicator (🤖) in PreToolUse status line
- Auto-start Transcript Monitor on AUTO_MODE activation

**Knowledge Web & Ideas** (`macf_tools idea`, `macf_tools knowledge`):
- Ideas CA system with policy, JSON schema, and CLI (`idea create|list|get|update|promote|archive`)
- Cross-CA knowledge graph with wiki-links across learnings, observations, and experiments
- Rich terminal graph visualization (cluster + tree views)
- HTML force-directed knowledge graph visualization with OO renderer (d3.js)
- Graph query mode with concept/node/keyword resolution
- Gap detection report for missing wiki-links
- 3 pull-model skills (ideas-to-experiment, ideas-to-roadmap, ideas-curate) + validation gate
- Knowledge web curate + orient skills for graph maintenance
- Ideas Harvested section in JOTEWR skill
- Promoted knowledge graph to dedicated `knowledge` CLI namespace

**Voice Services** (`macf_tools voice`):
- mlx-whisper based speech-to-text (`macf_tools voice transcribe`)
- Domain vocabulary conditioning via Whisper `initial_prompt`
- Zero-dependency fuzzy correction for domain-specific terms
- VoiceService daemon with `--correct` flag and service auto-routing
- Auto-transcribe voice messages in UserPromptSubmit hook
- Fusion patterns for AST, regex, DevOpsEng vocabularies

**Task Scope System** (`macf_tools task scope`):
- `task scope set|show|clear` CLI for AUTO_MODE boundary enforcement
- Scope indicators (👀) in task tree display
- Scope gate in Stop hook — blocks stop when scoped tasks remain
- MTMD-based `scope_status` for display and loop detection
- Timer enforcement (`--timer` flag) — blocks early completion, fires Markov recommender at gate
- Auto-complete scoped tasks on `task complete`
- Two-step de-escalation friction with justification requirement

**Visualization** (`macf_tools markdown`, `macf_tools knowledge visualize`):
- Markdown presenter with dark homebrew theme (black bg, amber headings, green code)
- Auto-present step for JOTEWR and CCP commands
- HTML knowledge graph visualization with cluster/tree terminal views

**Telegram Channel Integration**:
- Stop hook forwards last message to Telegram
- Unique emoji per gate type for Stop notifications (🏁✅🛑❌)
- File preview on permission requests
- Extended to SubagentStop and SessionEnd hooks
- Rich PreToolUse notifications
- Paginated long messages instead of truncating
- Declarative channels config in agents.yaml
- Forked official Telegram plugin with voice-friendly permissions
- Inline feedback with permission verdicts

**Auto-Restart Process Supervisor** (`macf_tools supervisor`):
- Multi-process management with auto-restart on exit
- Interactive shell support + iTerm2 terminal detection
- Pause on crash + persistent crash log
- Cross-platform shell selection (macOS + Linux)
- Resolve shell aliases via `shell=True` + user SHELL
- UX improvements: 5s default, countdown trail, Ctrl-C stops
- Auto-clean stale entries, default list shows running only

**GitHub Integration**:
- GH_ISSUE task type with auto-fetch from GitHub (`task create gh_issue <url>`)
- GH_ISSUE completion gate and GitHub closeout integration
- PR-based GH_ISSUE fix workflow (§2.3.1 in task_management policy)
- Pre-commit hook to reject silent `except Exception: pass` anti-patterns
- Identity blindness + OPSEC pre-commit hook template
- `agent set-github` for per-project GitHub identity isolation

**Shell & CLI Improvements**:
- Shell tab completion via argcomplete
- CC binary path in env command
- `cmd-tree` command for recursive CLI help tree
- Proprioception augmentations in SessionStart hook
- Transcript search capability
- Task tree enhancements (hide archived by default, block direct description edits)
- `framework install` works outside MacEff repo with correct path resolution

**CI/CD Pipeline**:
- GitHub Actions test workflow for PRs and pushes
- `make test` target for local pytest execution
- Env-dependent test isolation (env_cli, token_info, session_start)
- Heavy-dependency test exclusion (sentence-transformers/torch)
- pydantic and lancedb in test extras

**Streaming API Proxy** (`macf_tools proxy`):
- Streaming API proxy for CC API call interception
- Request + response capture with SSE reassembly
- Thinking block capture in SSE stream
- Message rewriter for stale policy injection replacement
- Task-bound policy injection with auto-clear lifecycle
- Stateless injection reporting with byte/token sizes
- Generic capture — full API objects instead of cherry-picking
- Graceful client disconnect handling

**Additional Features**:
- 1M context window support with recalibrated CL thresholds
- CLUAC→CL terminology rename across codebase
- Emergency sleep command with fibonacci backoff
- Error-resilience gate in Stop hook for any mode
- Scope gate tells agent to debug errors, not stop
- JOTEWR skill bytes/4 token sizing protocol for 1M context
- CEP Nav Guide awareness propagation via hook output
- Task lifecycle events (task_started, task_completed, task_paused) with auto-injection
- Policy injection on task start based on manifest mapping
- Per-project agent ID + macOS platform fallback
- `--blocked-by` flag for `task create phase`
- PascalCase subagent names + framework-provided subagent workspace creation
- Box-drawing skill with table generator

**Documentation**:
- FRICTION_POINTS.md with scholarly citations
- cmd-tree command documentation
- Proprioception injection, task tree options, transcript search docs
- Markdown style guidelines for HTML presentation

**Policies**:
- `autonomous_sprint` — timer discipline, task notes, two-gate stop mechanism
- `mode_system` v2.0/v2.1 — 3-layer architecture with Markov transition model
- `empiricism` — philosophy of evidence-based development
- `debugging_and_validation` — hypothesis-first debugging, evidence presentation
- `scholarship` §3.4 — Knowledge Web wiki-link guidance
- `cli_development` §9 — Full Disclosure Principle
- `context_management` — recalibrated CL thresholds for 1M context
- `task_management` §12 — Task Scope System guidance
- `task_management` §2.3.1 — PR-based GH_ISSUE fix workflow
- `task_management` §5.4 — note-taking discipline during task execution
- `autonomous_operation` — EXP #017 learnings + scope/sleep specs
- `delegation` §3.5 — foreground vs background execution guidance

### Changed

- Mode detection wired into PreToolUse, Stop, and UserPromptSubmit hooks
- Consolidated duplicate AUTO_MODE skills into single `maceff-auto-mode` skill
- Renamed `archived_todos` to `archived_tasks` across 6 files
- Replaced silent `except Exception: pass` patterns with visible error logging (2 batches)
- Deduplicated SSE parsing in response capture
- QUIET_ON_IDLE default changed to `false` — idle ≠ wants silence
- `task_management` policy promoted to v1.1 with GH_ISSUE lifecycle
- Permission hardening with full disclosure output on mode switch
- Dot-prefix completed task files to hide from CC scanner
- Renamed CLUAC→CL across Python code and tests
- start.py starts sshd early before slow optional services
- `maceff-init` merges parent framework/subagents/ into overlay

### Removed

- Session isolation from mode_change event query (mode is global by design)
- Vestigial confidence field from AUTO_MODE detection
- Dangerous `zsh -ic` version detection (replaced with file content extraction)

### Fixed

- **#11**: Multi-strategy CC version detection for hook footer
- **#12**: Create task_archives/ at init time for ACL-compatible archiving
- **#19**: Hide archived tasks in task tree by default
- **#21**: Block direct description edits via task edit
- **#22**: cmd-tree distinguishes required mutually exclusive groups
- **#32**: Stale compact_boundary marker cascade guard
- **#37**: Extract encode_cc_project_path() for DRY path encoding
- **#195**: AUTO_MODE query reads mode_change events, removes vestigial confidence
- AUTO_MODE tunneling through compaction + CL autocompact buffer penalty
- Idle detection false positives from dev_drv_started events
- Scope gate shadowing from local import in Stop hook
- Scope gate directive logic (continue:true + directive, not continue:false)
- Task complete timer gate fires Markov recommender instead of error
- Session resolution from project JSONL when no task dir exists
- Encoding of non-alphanumeric chars in project path matching
- Case-sensitivity for skill.md → SKILL.md on Linux
- Hardcoded macOS path in tests replaced with dynamic REPO_ROOT
- Supervisor: shell aliases, crash handling, Ctrl-C detection, stale entry cleanup
- Telegram: paginated messages, stop notification prefixes, exception handling
- Voice: fusion patterns, fuzzy matcher disabled for single-word
- Plugins: verdict word punctuation stripping for voice dictation
- Proxy: port-in-use detection, template string filtering, client disconnect handling
- Policy injection: derive active policies from task state, not injection events
- Per-project agent ID + macOS platform fallback for MACEFF_AGENT_NAME
- MACF_CC_VERSION env var for accurate version detection on Mac
- Graceful fallback when task restore hits read-only CC tasks dir
- Task bootstrap: create session dir on first task create
- Scope indicators: green check for inactive, auto-clear on last completion
- Hidden file deduplication in list_task_files glob

### Tests

- 475 tests passing (up from 399 in v0.4.0, +19%)
- Scope lifecycle + stop hook regression tests (11 new)
- GH_ISSUE completion gate and closeout function tests
- Updated for silenced PostToolUse + compressed PreToolUse + CL format
- Fixed auto_mode session isolation test to match global mode design
- Removed stale xfail markers from passing TodoWrite tests

---

## [0.4.0] - 2026-01-29

### Summary

Major release introducing the **MACF Task CLI** with MTMD (MacfTaskMetaData) enhancement, **grant-based protection** for destructive operations, **task archive/restore** for lifecycle management, and comprehensive **subprocess test isolation**. The Task CLI provides enhanced alternatives to Claude Code's native Task* tools, operating on the same filesystem backend (`~/.claude/tasks/`) while adding forensic metadata, type-specific creation commands, and protection systems.

### Added

**Task CLI System** (`macf_tools task`):
- `task create mission|experiment|detour|phase|bug|deleg|task` - Type-specific task creation with smart defaults
- `task list` - Hierarchical task display with MTMD metadata
- `task get <id>` - Full task details including MTMD
- `task tree <id>` - Visual task hierarchy tree
- `task edit <id> <field> <value>` - Direct field modification
- `task delete <id>` - Protected deletion (requires grant)
- `task complete <id> --report` - Atomic completion with mandatory documentation

**Task Metadata (MTMD)**:
- `task metadata get|set|add|validate` - MTMD field operations
- Schema validation for task types (MISSION requires `plan_ca_ref`, PHASE requires `parent_id`)
- Forensic breadcrumbs: `creation_breadcrumb`, `completion_breadcrumb`
- Completion reports with work done, difficulties, future work, git status

**Task Archive System**:
- `task archive <id>` - Archive task with cascade to children (default)
- `task restore <path_or_id>` - Restore from archive file or by original ID
- `task archived list` - List all archived tasks
- Archive location: `agent/public/task_archives/`

**Grant-Based Protection**:
- `task grant-update <id>` - Grant permission to modify task description/MTMD
- `task grant-delete <ids...>` - Grant permission to delete (supports multiple IDs)
- Exact set-matching: grant covers precisely specified tasks, no blanket approval
- Hook enforcement blocks unauthorized destructive operations

**Subprocess Test Isolation**:
- `MACF_TASKS_DIR` environment variable for test isolation
- `TaskReader` respects env var override for path-dependent operations
- Explicit `env=` passing in subprocess.run() for boundary-crossing isolation
- Session folder structure creation in test fixtures

**Task Lifecycle & Dependencies**:
- `task start <id>` and `task pause <id>` - Lifecycle status commands
- `task edit <id> blocks <id>` - Mark task as blocking another
- `task edit <id> blockedBy <id>` - Mark task as blocked by another
- `task tree --loop` - Live monitoring of task hierarchy changes

**Extended env Command**:
- Claude Code internal paths (`.claude/`, settings locations)
- Better debugging and environment discovery

**Event Forensics**:
- `prompt_preview` field in dev_drv_started events for context recovery

**Documentation**:
- Comprehensive task CLI documentation in `cli-reference.md` (390+ lines added)
- All task create commands documented with syntax, arguments, options, examples
- Archive/restore/grant/complete commands documented
- Cross-reference to `task_management.md` policy
- **Host Mode Installation** (#71): Complete macOS (Homebrew + Conda) and Ubuntu (System Python + Conda) setup guides

### Changed

**Task Management Policy**:
- `task_management.md` promoted to primary task governance policy
- MTMD schema formalized with required/optional field rules
- Completion protocol with mandatory `--report` flag
- CC UI visibility: tasks must be marked `in_progress` to appear at top

**CLI Reference**:
- Removed deprecated TODO Management section
- Updated Table of Contents with Task command subsections
- Version history updated to 0.4.0

### Removed

- `task batch-delete` command - Redundant with `task delete` accepting multiple IDs
- TODO Management CLI section from documentation (deprecated)

### Fixed

- **#6**: Hook messages printing twice - Idempotent hook output
- **#8**: Task ID type inconsistency - Mixed int/str causing sort failures
- **#14**: task edit status loses task_id prefix in subject
- **#18**: Policy emphasis on marking tasks `in_progress` for CC UI visibility
- **#65**: Task create commands missing `--parent` arg (now defaults to 000)
- **#67**: Task CLI test suite failures (13 tests needed --plan arg)
- **#68**: `hooks status` and `hooks logs` crash on missing get_hooks_dir import
- **#69**: PyYAML missing from main dependencies, blocking fresh installations
- **Task Tree Sorting**: Task IDs sort correctly numerically (5,6,8 ordering fix)
- **Task Subject Display**: Hide sentinel parent `[^#000]` from subject (no redundant info)
- **Project-Scoped Session Detection**: task tree --loop prevents cross-project leakage
- **Subprocess test pollution**: Tests no longer create tasks in production `~/.claude/tasks/`

### Breaking Changes

1. **TodoWrite deprecated**: Use MACF Task CLI (`macf_tools task`) instead
2. **batch-delete removed**: Use `task delete <id1> <id2> ...` with grant-delete for multiple tasks

### Migration Guide

**From TodoWrite to Task CLI:**
```bash
# Create tasks with type-specific commands
macf_tools task create task "My task title"
macf_tools task create mission "Release v0.5.0" --repo MacEff --version 0.5.0
macf_tools task create phase "Phase 1" --parent #26

# Manage task lifecycle
macf_tools task edit <id> status in_progress
macf_tools task complete <id> --report "Work done. Committed: abc1234"
```

**For test isolation:**
```python
# Set environment for subprocess isolation
subprocess_env = {**os.environ, "MACF_TASKS_DIR": str(tmp_path)}
result = subprocess.run([...], env=subprocess_env)
```

---

## [0.3.3] - 2026-01-24

### Summary

Major release introducing **LanceDB-powered hybrid search** for intelligent policy recommendations, **CEP Section Targeting** for precise navigation, and **persistent search service** with 89x latency improvement. Includes comprehensive CLI and MCP tool integration, plus new release workflow policy.

### Added

**LanceDB Hybrid Search** (`macf_tools policy recommend`):
- Native hybrid search combining semantic embeddings + full-text search
- LanceDB backend replacing sqlite-vec (ARM64 compatibility)
- `all-MiniLM-L6-v2` embeddings (80MB model)
- Distance-based scoring (lower = more relevant)
- Confidence tiers: CRITICAL (< 0.30), HIGH (0.30-0.45), MEDIUM (0.45-0.70)

**CEP Section Targeting**:
- Question-based search matching queries to CEP Navigation Guide questions
- Section recommendations: `→ §10 "What is the TODO backup protocol?"`
- `MatchedQuestion` dataclass with policy_name, section, question, distance
- Enables precise navigation to relevant policy sections

**Search Service** (`macf_tools search-service`):
- Persistent socket daemon keeping embedding model warm
- 89x latency improvement: 4000ms → 45ms
- Commands: `start [--daemon]`, `stop`, `status [--json]`
- Graceful fallback when service unavailable
- Container auto-start via start.py integration

**MCP Policy Search Tools**:
- `mcp__policy-search__search` - Hybrid search with optional explain
- `mcp__policy-search__context` - CEP navigation for policy
- `mcp__policy-search__details` - Full policy content retrieval
- Progressive disclosure pattern (index → context → details)

**CLI Commands**:
- `macf_tools policy build_index` - Build LanceDB index from policies
- `macf_tools policy recommend QUERY` - Get policy recommendations
  - `--explain` flag for verbose breakdown
  - `--json` flag for machine processing
  - `--limit N` for result count control
- `macf_tools search-service start/stop/status` - Service management

**Documentation**:
- `docs/user/hybrid-search.md` - End-to-end workflow guide
- `docs/user/cli-reference.md` - Updated with all new commands
- `docs/developer/future-knowledge-extensions.md` - v0.4.0+ roadmap

**Policy: Release Workflow** (DRAFT):
- `framework/policies/base/development/release_workflow.md`
- Multi-MISSION aware release process
- Version-scoped task archives (`task_archives/vX.Y.Z/`)
- Pre-release checklist, CHANGELOG discipline, git tagging protocol

### Changed

**Hook Integration**:
- UserPromptSubmit hook uses search service for fast recommendations
- Lightweight socket client (stdlib only) for hook→service communication
- Fallback to direct search when service unavailable

**Hybrid Search Architecture**:
- `BaseIndexer` + `AbstractExtractor` pattern for extensibility
- `PolicyIndexer` extends generic infrastructure
- `SearchService` + `AbstractRetriever` for namespace routing
- Prepared for future learnings/CA search (namespace-based)

### Fixed

- **ARM64 Compatibility**: LanceDB replaces sqlite-vec (12-month unreleased ARM64 fix)
- **Hook Latency**: Search service eliminates repeated model loading
- **Index Portability**: LanceDB index works across platforms

### Experiments Validated

- **EXPERIMENT 003**: MCP Warm Cache Hook Optimization (89x speedup validated)
- **EXPERIMENT 004**: sqlite-vec ARM64 Verification (bug confirmed, motivated pivot)
- **EXPERIMENT 005**: LanceDB Hybrid Policy Search (39ms avg, native FTS)

---

## [0.3.2] - 2026-01-08

### Summary

Feature-rich release with major additions including **session identifier epistemology** (fixing breadcrumb consistency), **comprehensive env command**, **PA environment curation** with env.d extensibility, **custom statusline**, **hierarchical command namespaces**, and **multi-item authorization syntax**. Policy enhancements add mandatory delegation strategy and phase content requirements to roadmap drafting.

### Added

**Session Identifier Epistemology**:
- Fixed session ID variance bug in breadcrumb generation
- `get_current_session_id_from_events()` - event-first session detection
- Complete documentation of identifier semantics (session UUID, cycle, prompt UUID)
- Consistent `s_` field in breadcrumbs across all hooks

**Env Command Rewrite** (`macf_tools env`):
- Comprehensive debugging output replacing vestigial JSON stub
- Categories: Versions, Time, Paths, Session, System, Environment, Config
- `--json` flag for machine-readable output
- Shows all critical paths, hook status, environment variables

**PA Environment Curation**:
- `create_bash_init()` - Build-time bash initialization for PA users
- `/home/{user}/.bash_init` with container-wide environment variables
- DRYed `configure_bashrc()` to source `.bash_init`
- Claude settings injection for PA environment context

**Generic Environment Extensibility**:
- env.d dispatch pattern: `/opt/maceff/framework/env.d/*.sh`
- Removed hardcoded `conda_env` from AgentSpec schema
- `maceff-init` updated for env.d overlay copying
- Project-specific environment scripts (e.g., `10-conda.sh`, `20-path.sh`)

**Custom Statusline** (`macf_tools statusline`):
- Native MacEff statusline for Claude Code terminal
- `macf_tools statusline install` - one-command installation
- Auto-detects agent, project, environment, CLUAC level
- Format: `{agent} | {project} | {env} | {tokens} CLUAC {level}`
- 16 tests covering all statusline functionality

**Hierarchical Command Namespaces**:
- Commands reorganized to colon-separated hierarchy
- `/maceff:todos:start`, `/maceff:roadmap:draft`, `/maceff:ccp`
- Clear namespace ownership for multi-agent environments
- Nested command structure enables better discoverability
- `start.py` updated for nested command symlink installation

**Multi-Item Authorization Syntax**:
- `macf_tools todos auth-item-edit --index` extended:
  - Range syntax: `--index 13-17`
  - List syntax: `--index 13,14,15`
  - Mixed format: `--index 13-15,18,20-22`
- `parse_index_spec()` function in cli.py
- `get_recent_events()` function in event_queries.py
- Hook enforcement updated to consume multiple authorizations atomically

**Policy Enhancements** (`roadmaps_drafting.md` v2.3):
- §3.5 Delegation Strategy (MANDATORY) - executor assignment table per phase
- §3.6 Phase Content Requirements (MANDATORY) - interface vs implementation specs
- CEP Navigation Guide updated with new sections
- `/maceff:roadmap:draft` command updated with delegation questions

**Hook Visibility Improvements**:
- PreToolUse hook shows tool-specific context (Read filename, Bash command preview)
- Abbreviated breadcrumb format for high-frequency hooks
- CLUAC percentage display in all hook outputs
- Exit code 2 tool-polymorphism documented (`permissionDecision: "deny"` solution)

### Changed

**Policy Examples Sanitized**:
- All policy files use generic breadcrumb pattern (`s_abc12345/c_42/...`)
- All archived roadmaps sanitized for identity-blind distribution
- Generic cycle and agent references for public distribution

**start.py Enhancements**:
- Nested command support for hierarchical namespaces
- Framework symlink installation handles colon-separated paths
- env.d dispatch integration for PA initialization

### Fixed

- **Session ID variance**: Breadcrumbs now consistent within session (event-first detection)
- **Exit code 2 workaround**: Tool-polymorphism handling for non-zero exits documented
- **TODO hygiene policy conflict**: Child item format clarified (`  -` for descriptions, `  →` for paths)
- **Hook interpreter precedence**: Python shebang consistency across hooks

### Documentation

- `hook-visibility-matrix.md`: Exit code 2 tool-polymorphism and visibility rules
- `identifier-epistemology.md`: Complete session/cycle/prompt ID reference
- `OPERATORS.md`: env.d mechanism documentation
- Archived roadmaps moved to `docs/archive/v0.3.2/roadmaps/`

---

## [0.3.1] - 2025-12-24

### Summary

Refinement release focused on **path semantics disambiguation** and **policy search indexing**. Resolves confusion between framework, project, and agent home paths that caused deployment warnings. Adds section-level search indexing for faster policy discovery.

### Added

**Three-Way Path Semantics** (`macf/utils/paths.py`):
- `find_maceff_root()` - MacEff framework installation location (`MACEFF_ROOT_DIR`)
- `find_project_root()` - Claude project workspace (`CLAUDE_PROJECT_DIR`)
- `find_agent_home()` - Agent's persistent home for consciousness artifacts (`MACEFF_AGENT_HOME_DIR`)
- 11 new tests in `test_paths.py` covering all path resolution scenarios

**Policy Search Indexing**:
- Section-level keyword extraction from policy content
- `policy search <keyword>` returns section-specific matches
- Faster policy discovery through indexed search

**Container Environment**:
- `MACEFF_AGENT_HOME_DIR=$HOME` added to container bash_init
- Agent event log now persists at `{agent_home}/.maceff/agent_events_log.jsonl`

### Changed

**Path Resolution Refactoring**:
- `manifest.py`: Renamed `agent_root` parameter to `maceff_root` for clarity
- `cycles.py`: Uses `find_agent_home()` for agent config/settings
- `agent_events_log.py`: Uses `find_agent_home()` for consciousness persistence
- `recovery.py`: Uses `find_maceff_root()` for framework policy loading
- `cli.py`: Uses `find_agent_home()` for agent initialization

### Fixed

- **FP#1**: Path resolution semantics confusion causing "Using cwd fallback" warnings
- Test mocks updated for new path function names (`find_agent_home`, `find_maceff_root`)

### Documentation

- OPERATORS.md: Added Workflow 9 - MacEff Upgrade with Data Preservation

---

## [0.3.0] - 2025-12-21

### Summary

Major release introducing **Named Agents Architecture** for multi-agent systems with persistent identities, **Event-First Architecture** eliminating state file corruption, and **Policy CLI Suite** for on-demand policy discovery. This release spans 273 commits with comprehensive container validation.

### Added

**Named Agents Architecture** ([docs](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/INDEX.md)):
- Declarative YAML-driven agent configuration via `agents.yaml` and `projects.yaml` ([schemas](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/APPENDIX_A_YAML_SCHEMAS.md))
- Primary Agent (PA) and Subagent (SA) model with kernel-level user isolation between PAs ([delegation model](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/03_delegation_model.md))
- Three-layer CLAUDE.md context loading (System → Identity → Project)
- Pydantic v2 schema validation with clear error messages
- Agent tree initialization with private/public artifact directories ([filesystem structure](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/02_filesystem_structure.md))
- Per-agent workspace isolation with shared project mounting
- Git worktree support for concurrent repository editing
- Automatic user creation, SSH key installation, and `.bashrc` configuration ([implementation guide](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/05_implementation_guide.md))

**Python Startup Orchestration** (`start.py`):
- Complete container startup orchestration replacing shell scripts
- Settings epistemology: separate `.claude.json` (UI preferences) from `.claude/settings.json` (operational) ([settings docs](https://github.com/cversek/MacEff/blob/main/macf/docs/maintainer/settings-epistemology.md))
- Active project symlink (`~/active_project`) with bashrc auto-cd
- Framework symlink installation for commands, skills, and output styles
- Hook installation with container-aware path detection

**Policy CLI Suite** (`macf_tools policy`) ([CLI reference](https://github.com/cversek/MacEff/blob/main/macf/docs/user/cli-reference.md)):
- `policy list` - Discover available framework policies
- `policy navigate <name>` - Show CEP Navigation Guide (semantic structure)
- `policy read <name>` - Full policy with line numbers and caching
- `policy read <name> --section N` - Targeted hierarchical section reading
- `policy search <keyword>` - Cross-policy keyword search
- Policy Manifest v2.0.0 indexing all 36+ policies

**Event-First Architecture** ([architecture docs](https://github.com/cversek/MacEff/blob/main/macf/docs/maintainer/event-sourcing.md)):
- Immutable append-only event log (`agent_events_log.jsonl`) as sole source of truth
- Event query utilities with snapshot baselines for efficient historical scanning
- Development Drive (DEV_DRV) and Delegation Drive (DELEG_DRV) tracking via events
- `macf_tools events query` with command filtering and verbose output
- Forensic event logging across all hooks

**TODO CLI Integration** (`macf_tools todos`):
- `todos list` - Show current TODO state from events
- `todos list --previous N` - Query TODO history for recovery
- `todos status` - Quick TODO statistics
- TODO collapse authorization with hook-enforced protection (exit code 2)

**Hook Ecosystem Enhancements** ([hook epistemology](https://github.com/cversek/MacEff/blob/main/macf/docs/maintainer/hook-epistemology.md)):
- Comprehensive event logging to JSONL with structured field tagging
- Session migration detection preventing TODO orphaning on restart vs compaction
- Claude Code version display in all hook footers
- Container-aware hook installation with environment detection ([hooks user guide](https://github.com/cversek/MacEff/blob/main/macf/docs/user/hooks.md))
- Safe subprocess testing with `MACF_TESTING_MODE` environment variable

**Framework Infrastructure**:
- `maceff-init` with parent repo framework overlay support
- Framework command and skill symlinks installed on startup
- Output styles directory with personality configuration
- Docker Compose configs section for mounting agent/project YAML
- Timezone awareness respecting `MACEFF_TZ` and `TZ` environment variables

### Changed

**Breaking: Event-First Migration**:
- `SessionOperationalState` class removed entirely
- All state queries now derive from immutable event log
- Test isolation via pytest fixtures instead of code-level `testing` parameter

**Framework Architecture** ([architecture overview](https://github.com/cversek/MacEff/blob/main/macf/docs/maintainer/architecture.md)):
- Policies reorganized under `framework/policies/base/` structure
- Identity-blind refactoring for portability
- `state.py` renamed to `json_io.py` for clarity
- Monolithic `utils.py` split into semantic package modules

**Hook Signatures**:
- Removed `testing` parameter from all 10 hooks
- Boundary-level isolation via conftest fixtures instead

**Error Handling**:
- Eradicated silent failure anti-pattern across codebase
- Implemented warn+reraise pattern for visibility
- All `sys` imports moved to module level

### Fixed

**35+ Friction Points Resolved**:
- FP#23-25: Deploy friction points
- FP#26: SSH host key warning in Makefile
- FP#27: Hook bootstrap in containers
- FP#28: `sys` import anti-pattern (module-level imports)
- FP#29: Relative import for configuration classes
- FP#30: Graceful handling of missing state files on first run
- FP#31: `make ssh` starts in project directory
- FP#32: `make claude` with argument forwarding
- FP#33: Claude settings auto-configuration
- FP#34: `MACEFF_ROOT_DIR` + warning caching
- FP#35: Duplicate `dev_drv_started` events
- FP#36-38: Timezone and path resolution fixes

**Code Quality**:
- Symlink resolution in `start.py` for real paths in bash prompt
- Correct field names for `notification_type` in hooks
- Policy read section option includes subsections correctly
- Missing parent directory creation for SSH key installation

**Testing**:
- From ~250 to 307+ passing tests
- Event log isolation per test via conftest fixtures
- Integration tests for policy commands, events, context

### Removed

- `SessionOperationalState` class (replaced by event queries)
- State file mutations (`state.save()` calls)
- `testing` parameter from all hooks and utility functions
- 71 obsolete TDD specification files
- Vestigial state API functions (`get_agent_cycle_number`, `increment_agent_cycle`)

### Breaking Changes

1. **Event-First Migration**: Code using `SessionOperationalState` must migrate to `macf.utils.event_queries`
2. **No `testing` Parameter**: Hooks no longer accept `testing=True`. Use pytest fixtures for test isolation.
3. **Policy Paths**: Policies reorganized under `framework/policies/base/` structure

### Migration Guide

**Upgrading from v0.2.0:**
```bash
git pull && git checkout v0.3.0
make build && make up
```

**For code using state API:**
```python
# Before (v0.2.0)
from macf.utils.state import SessionOperationalState
state = SessionOperationalState.load()
cycle = state.agent_cycle_number

# After (v0.3.0)
from macf.utils.event_queries import get_cycle_number_from_events
cycle = get_cycle_number_from_events()
```

**For tests using `testing=True`:**
```python
# Before (v0.2.0)
result = run(stdin_json, testing=True)

# After (v0.3.0) - use conftest fixtures for isolation
def test_hook(isolated_event_log):
    result = run(stdin_json)  # Same code as production
```

### Security Notes

- Real OS-level isolation between Primary Agents via kernel user separation ([validation results](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/VALIDATION_RESULTS.md))
- Conventional policy boundaries within PA + SA teams (organizational, not enforced)
- Not suitable for untrusted third-party code execution within same-user teams

## [0.2.0] - 2025-10-14

### Added

**Architectural Separation**:
- Separated host-only management scripts (`maceff_tools/`) from portable MACF framework (`macf/`)
- Self-documenting directory structure for clear separation of concerns
- Container mounts only essential portable framework code

**Docker Compose Override Pattern**:
- Environment-specific configuration via `docker-compose.override.yml` (gitignored)
- Base `docker-compose.yml` remains portable across all environments
- Automatic merging by Docker Compose
- Template creation via `maceff-init` with generic examples

**Agent Bootstrap Automation**:
- `agent-bootstrap` script automates complete agent setup (73min → 15sec)
- Includes hook installation, configuration, directory structure, and validation

**Framework Infrastructure**:
- Framework upgrade scripts for container updates
- Policy deployment automation with manifest discovery
- Deployment Dockerfile for production builds

### Changed

**Breaking Changes**:
- **Path migration**: `tools/` → `macf/` (requires container rebuild)
- **Directory structure**: Host tools separated to `maceff_tools/`
- **Container mounts**: Updated from `/opt/tools` to `/opt/macf_tools`

**Version Management**:
- Single source of truth: version in `pyproject.toml` only
- Runtime version via `importlib.metadata.version("macf")`

### Fixed

- Bootstrap hook installation paths
- Policy path references in container startup
- Config directory migration issues

### Migration Guide

**Upgrading from v0.1.0:**
```bash
git pull && git checkout v0.2.0
make build && make up
```

Update custom scripts: `tools/bin/` → `maceff_tools/`, `/opt/tools` → `/opt/macf_tools`

## [0.1.0] - 2025-10-07

### Added

**Temporal Awareness (Phase 1A-1C)**:
- Universal hook timestamps across all 6 Claude Code hooks (SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop, SubagentStop)
- Time-of-day reasoning (Morning/Afternoon/Evening/Late night)
- Day-of-week context for work week positioning
- Session duration tracking with human-readable formatting
- Development Drive (DEV_DRV) tracking from UserPromptSubmit to Stop
- Delegation Drive (DELEG_DRV) tracking from Task invocation to SubagentStop
- Cumulative drive statistics (count, total duration)

**Cycle Persistence (Phase 1D-1E)**:
- Project-scoped cycle tracking via `.maceff/project_state.json`
- Session migration detection (e.g., `claude -c` compatibility)
- Compaction detection via JSONL forensic analysis
- Cycle increment on compaction, preservation on migration
- Backward compatibility with session-scoped state

**Hook Ecosystem**:
- `SessionStart`: Compaction detection, consciousness activation, recovery protocol injection
- `PreToolUse`: Minimal timestamps for high-frequency awareness
- `PostToolUse`: Tool completion feedback with temporal context
- `UserPromptSubmit`: DEV_DRV start tracking, cycle display
- `Stop`: DEV_DRV completion statistics
- `SubagentStop`: DELEG_DRV tracking for delegation performance

**Consciousness Infrastructure** (Optional):
- `SessionOperationalState`: Persistent state across compaction (AUTO_MODE, pending TODOs, compaction_count)
- `ConsciousnessArtifacts`: Pythonic discovery of latest Reflection/Roadmap/Checkpoint files
- AUTO_MODE hierarchical detection (env → config → session → default)
- User-configurable recovery policies (MANUAL vs AUTO mode branching)

**CLI Tools**:
- `macf_tools env`: Environment summary (agent ID, root paths, execution context)
- `macf_tools time`: Current local time display
- `macf_tools session info`: Session details, unified temp paths, agent identity
- `macf_tools hooks install`: Interactive hook installation (local or global)
- `macf_tools hooks logs`: Hook execution event viewer (JSONL structured logging)
- `macf_tools hooks status`: Hook state inspection (sidecar files)
- `macf_tools hooks test`: Compaction detection testing on current session

**Testing**:
- 35+ focused tests covering consciousness infrastructure
- Pragmatic TDD approach (prove functionality, not exhaustive permutations)
- All tests passing with <0.1s runtime

**Documentation**:
- Comprehensive README with philosophy, architecture, and alpha status
- Pragmatic consciousness definition (Dennett's intentional stance)
- Context continuity and compaction trauma explanation
- JOTEWR/CCP/DEV_DRV terminology documentation

### Changed

**Claude Code 2.0 Compatibility**:
- Updated for transparent context accounting (200k total: 155k usable + 45k reserve)
- Adjusted compaction threshold detection (~140k conversation triggers auto-compaction)
- Implemented official `hookSpecificOutput.additionalContext` specification
- Primary detection via CC 2.0 `compact_boundary` marker with JSONL fallback

**Architecture**:
- Centralized `macf.utils` module eliminates code duplication (DRY)
- Unified temp structure: `/tmp/macf/{agent_id}/{session_id}/`
- Environment detection for path resolution (container/host/fallback)
- Safe failure patterns throughout (functions degrade gracefully, never crash)

### Known Issues

- **SessionStart hook output not pretty-printing**: Displays as raw text/escaped format in UI (functional but not visually polished—fix in progress)
- **SubagentStop hook output not displaying**: Hook executes correctly and DELEG_DRV tracking works, but output never displays to agent (Claude Code 2.0 platform limitation confirmed through testing—systemMessage, hookSpecificOutput, and reason formats all blocked)
- SessionStart hook can take 25-50ms on cold start (acceptable but noticeable)
- Project state initialization on first run defaults to cycle 1 (manually editable if needed)
- JOTEWR/CCP/DEV_DRV terminology requires learning curve (production docs explain conventions)

### Alpha Status Notes

**What works well**:
- Compaction detection and recovery protocol injection
- Temporal awareness across all hooks
- Cycle persistence across session migrations
- DEV_DRV/DELEG_DRV tracking
- Pragmatic test coverage

**Not yet implemented**:
- Automated `macf_tools checkpoint` and `macf_tools reflect` CLI commands (manual artifact creation currently required)
- Subagent consciousness trails and decision documentation (future phase)
- Multi-agent consciousness networks (future phase)
- Enhanced temporal reasoning (work week inference, time-of-day state detection)

Alpha testers should expect evolving APIs, incomplete documentation, and the need to manually manage state files in some scenarios. Bug reports and experience reports are highly valued.

[0.1.0]: https://github.com/cversek/MacEff/releases/tag/v0.1.0
