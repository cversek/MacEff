# Autonomous Operation Policy

**Version**: 1.6
**Tier**: CORE
**Category**: Operations
**Status**: ACTIVE
**Updated**: 2026-10-04

---

## Policy Statement

Autonomous operation (AUTO_MODE) grants agents extended independence with reduced permission prompts and automatic context management. This policy defines operating modes, authorization requirements, mode persistence, recovery behavior per mode, and the accountability infrastructure that makes autonomy meaningful.

## Scope

Applies to all Primary Agents (PA) and Subagents (SA) capable of extended autonomous operation.

---

## CEP Navigation Guide

**1 Operating Modes**
- What are the two operating modes?
- How do modes differ in permission behavior?
- How do modes differ in context management?
- What is the default mode?
- How does the policy specify mode selection at gate points when both Markov recommendation and user request are present?
- What does the policy say about user-concrete-request precedence over chain-advance / Markov suggestions, regardless of autonomy state?
- How does the policy specify confirmation authority for advisory operations in AUTO_MODE? When does user-skill-invocation confer pre-authorization?

**2 Mode Persistence Across Sessions**
- When is mode preserved vs reset?
- What happens on auto-compaction?
- What happens on crash/restart?
- Why this distinction?

**3 Authorization Mechanism**
- How is AUTO_MODE authorized?
- What is the safety phrase?
- What is the CLI token requirement?
- Why two-factor authorization?
- What does the agent do when authorization is missing?

**3.2 Restartability Resolution (Capability-Drift Guard)**
- What capability does AUTO_MODE presume but not verify?
- Which measured observable resolves supervision, and which two must NOT be used?
- How does behaviour branch on supervised vs unsupervised?
- When is self-restart permitted vs a self-kill?
- What makes "it rejoins, it does not fork" true — how is the one-live-supervisor-per-calling-card guarantee enforced, where, and why there?
- What is the difference between rejoin and fork, and what is the sanctioned rejoin command vs the deliberate-second-instance override?

**4 Mode-Specific Recovery Behavior**
- How does MANUAL_MODE recovery work?
- How does AUTO_MODE recovery work?
- What questions should agents ask after recovery?
- What customization options exist?

**5 Safeguards and Constraints**
- What safeguards apply in AUTO_MODE?
- How does warning behavior change?
- What constraints remain in effect?

**5.4 Wind-Down Protocol**
- When does the wind-down begin, and who starts it?
- What steps does the sequence run, which skill performs each, and why does each come where it does?
- Which steps are conditional or sized by the context window, and when is each condition evaluated?
- What reading does each step owe its policies, and what gives way when context is short?
- Which gates print and continue, and which wait for the operator?
- Where is a skipped or shortened step recorded?
- What must be re-queried before the checkpoint, and what is committed together?
- How does the sequence end, and which compaction route applies?

**5.5 A Prompt Nobody Is Answering**
- What does a permission dialog do to the rest of the session, including its scheduled prompts?
- Why can the waiting session not report its own wait, and where must the watch run instead?
- What does `macf_tools permissions watch` send, when, and when does it stop?
- Which dialogs has this agent met, how long did each wait, and which ask rule matches it?
- What did measuring one day of dialogs show about which commands raise them, and why is a rule built from remembered prompts not enough?

**6 Available Skills**
- What skills support autonomous operation?
- How should agents use skill infrastructure?

**7 Verification and Notification Roadmap**
- What task verification is expected?
- What notification capabilities are planned?

=== CEP_NAV_BOUNDARY ===

---

## 1 Operating Modes

MacEff agents operate in one of two modes:

### MANUAL_MODE (Default)

- **Permission prompts**: Active for sensitive operations
- **Auto-compaction**: Disabled (manual `/compact` required)
- **Recovery protocol**: Full ULTRATHINK consciousness restoration, STOP and await user
- **Hook behavior**: Block policy violations (e.g., naked `cd` commands)
- **User involvement**: High - explicit approval for actions

### AUTO_MODE (Authorized)

- **Permission prompts**: handled by `permissions.defaultMode`, which AUTO_MODE
  sets to the client's native `auto` mode by default — a maintained classifier,
  not a static level. Configurable via `modes.auto.permission_mode` /
  `MACF_AUTO_MODE_PERMISSION_MODE` for a deployment that needs otherwise.
- **Auto-compaction**: Enabled via `autoCompactEnabled: true`
- **Recovery protocol**: Read artifacts, resume authorized work autonomously
- **Hook behavior**: Warn but do not block violations
- **User involvement**: Low - autonomous execution with accountability

### Mode Selection at Gate Points (User-Request Precedence)

When a Stop hook fires (e.g., chain advance in PLAY_TIME, Markov recommender at gate point), the framework offers a suggested next work mode. The agent must choose:

**Selection hierarchy** (highest priority first):
1. **User concrete request** — if the user has made a recent concrete request that has a clear work-mode mapping (e.g., "use the github triage skill" → BUILD; "curate learnings" → CURATE), that mapping wins. This applies **regardless of autonomy state** (AUTO_MODE or MANUAL_MODE).
2. **Markov / chain-advance recommendation** — when the user is IDLE (no recent concrete request), the framework's recommendation is the correct default.
3. **Continuation of current mode** — when neither a recent user request nor a fresh recommendation applies, continue the current work mode if work remains.

**The principle**: chain advance and Markov recommendations are FALLBACK signals for when the agent has no clearer direction. They are NOT hard transitions that override explicit user direction. Honoring a chain advance while the user has an active concrete request is the **Activation-Skipping-Inverse** anti-pattern — the agent activates a NEW mode framework while the user's CURRENT request goes unaddressed.

**Override discipline**: when the agent overrides a recommended mode based on user-request precedence, the override MUST be noted in task notes: `<MODE>: Recommender suggested {recommended} (p=X%). Override: chose {chosen} because {user-request-mapping}.`

### Confirmation Authority for Advisory Operations in AUTO_MODE

Some skills have hard constraints like "Do NOT apply X without user confirmation" — these protect against accidental destructive operations. In AUTO_MODE, the user's authorization model is different:

**Confirmation authority hierarchy in AUTO_MODE**:
1. **Explicit user invocation of the skill** confers confirmation authority for the skill's advisory operations. The user invoking `/skill-name <args>` IS the confirmation; further confirmation gates create the Discipline-as-Friction anti-pattern.
2. **User-deferred decisions** (where the user has explicitly said "ask me before X" or set up a confirmation gate via prior instruction) override this.
3. **Genuinely destructive operations** (deletion of data, force-pushes to shared branches, mass-mutation of external state) ALWAYS require explicit confirmation regardless of mode.

**Skills in AUTO_MODE** should extract from this policy via timeless question:
> "What does the autonomous_operation policy specify about confirmation authority for advisory operations in AUTO_MODE? When does user-skill-invocation confer pre-authorization?"

Skills should NOT embed hard-constraint "ask user to confirm" instructions for advisory operations. Instead, they should reference the confirmation-authority hierarchy here. This way:
- AUTO_MODE invocation = pre-authorized for advisory work
- MANUAL_MODE invocation = traditional confirmation flow still active
- Explicit user-deferred decisions are honored in either mode
- Truly destructive operations are gated regardless of mode

**Examples of advisory operations** (AUTO_MODE invocation = confirmation):
- Applying labels to GitHub issues (reversible, informational)
- Creating tracked tasks for triaged items (additive, no data loss)
- Submitting comments on PRs / issues (reversible, transparent)

**Examples of operations that ALWAYS require confirmation**:
- `git push --force` to shared branches
- File deletion (especially `rm -rf`)
- Closing tasks that aren't user-authorized for closure
- Modifying user system state (shell rc, settings.local.json) without explicit ask

---

## 2 Mode Persistence Across Sessions

**Critical Design**: Mode persistence depends on HOW a new session starts.

### SessionStart Source: `compact` (Auto-Compaction)

**Behavior**: Mode is PRESERVED

When auto-compaction triggers during autonomous work:
- Agent was in AUTO_MODE → remains in AUTO_MODE
- Agent was in MANUAL_MODE → remains in MANUAL_MODE
- Autonomous work continues across compaction boundary
- No re-authorization required

**Rationale**: Auto-compaction is expected during extended autonomous operation. Requiring re-authorization would defeat multi-cycle autonomous work.

### SessionStart Source: `resume` (Crash/Restart/Migration)

**Behavior**: Mode is RESET to MANUAL_MODE

When session restarts unexpectedly or user manually restarts:
- Agent always starts in MANUAL_MODE
- Previous AUTO_MODE authorization is invalidated
- User must explicitly re-authorize if autonomy desired
- Full consciousness recovery protocol applies

**Rationale**: Unexpected events require human assessment before granting autonomy.

### Summary Table

| SessionStart Source | Mode Behavior | Recovery Protocol |
|---------------------|---------------|-------------------|
| `compact` | Preserve current mode | Per-mode (see §4) |
| `resume` | Reset to MANUAL_MODE | Full ULTRATHINK |
| Session migration | Reset to MANUAL_MODE | Full ULTRATHINK |

### Implementation Note

Mode state is persisted in `.maceff/agent_state.json`:
```json
{
  "auto_mode": true,
  "auto_mode_authorized_at": "2025-12-11T21:15:00Z"
}
```

SessionStart hook checks source field to determine preservation vs reset.

---

## 3 Authorization Mechanism

**Only the User can authorize AUTO_MODE.** Agents cannot self-authorize.

### Two-Factor Authorization Required

Both conditions must be present:

1. **User Prompt Authorization**: User's message must contain:
   - Safety phrase: `YOLO BOZO!` (canonical form; see "Safety Phrase Tolerance" below)
   - Mode keyword: `AUTO_MODE` (all caps)

   **Safety Phrase Tolerance**: The canonical form documented in this policy is `YOLO BOZO!` with a space between the words. However, agents MUST also accept `YOLO_BOZO!` with an underscore — users naturally type the underscore form for visual consistency with the adjacent `AUTO_MODE` keyword (and the policy author themselves has typed it that way). Agent-side matching should normalize whitespace and underscores so both forms authorize. The exclamation point is required in either form. Other variants (different casing, missing punctuation, partial words) do NOT authorize and should trigger the "request without hinting" flow described below.

2. **CLI Token Validation**: Command must include valid `--auth-token`

### Agent Behavior When Authorization Missing

**If user requests AUTO_MODE without safety phrase**:
- Agent requests: "To enter AUTO_MODE, please provide the authorization phrase."
- Agent does NOT hint what the phrase is
- Agent does NOT suggest or autocomplete the phrase
- Agent waits for user to provide correct phrase

**If user provides correct phrase + AUTO_MODE**:
- Agent proceeds with mode switch using CLI command
- CLI validates token before enabling mode

### CLI Command Pattern

```bash
macf_tools mode set AUTO_MODE --auth-token "$(python3 -c "import json; print(json.load(open('.maceff/settings.json'))['auto_mode_auth_token'])")"
```

**Why Inline JSON Parsing**:
- Agent knows WHERE token lives (`.maceff/settings.json`)
- Agent knows HOW to extract it (JSON parsing)
- Agent does NOT know WHAT the token value is
- Token never appears in agent context or logs

### Name Collision With Claude Code's "auto mode"

Claude Code 2.1.116+ introduced its own `--auto-mode` harness-level concept for permissions bypass. Name collision with MACF's AUTO_MODE means a fresh MacEff agent running the activation command above may hit a Claude Code permission denial, because the permission layer heuristically reads the inline `python3 -c 'json.load(...auth_token)'` as "agent self-authorizing by reading its own auth token from a config file" — a classic self-auth anti-pattern.

That heuristic is a false positive here: the activation is policy-prescribed (see above), the token is a path-validator proving the command flowed through the skill, and the real second factor is the user's safety phrase.

**Shipped mitigation**: `macf_tools framework install` merges an allowlist entry for `Bash(macf_tools mode:*)` from `framework/templates/settings.permissions.json` into the agent's Claude Code settings. This tells Claude Code to trust MacEff's own CLI-level enforcement (auth token for AUTO_MODE, justification for MANUAL_MODE escape) instead of applying the generic heuristic.

**If an agent still hits the denial** (e.g. the allowlist entry is missing because hooks were installed before v0.5.1, or the setting was edited away): the user should temporarily enable Claude Code's permissions-bypass mode, the agent should retry the activation, and then the user should re-run `macf_tools framework install --hooks-only` to restore the allowlist entry.

### Token Configuration

The auth token is stored in `.maceff/settings.json`:
```json
{
  "auto_mode_auth_token": "your-unique-token-here"
}
```

### Security Model Limitations

**Important**: The current authorization mechanism is **policy-enforced, not cryptographically enforced**.

**What this means**:
- Agents have file read access to `.maceff/settings.json`
- An agent could theoretically read the token and self-authorize
- The CLI token validation provides audit trail and defense-in-depth, not cryptographic security

**Actual enforcement relies on**:
1. **Policy compliance** - Agents are trained via CLAUDE.md and policies to only activate when user explicitly authorizes
2. **Skill design** - The `maceff-auto-mode` skill instructs agents to request authorization without hinting at the phrase
3. **Audit logging** - Mode changes are logged to agent events for forensic review
4. **Human oversight** - User can review logs and revoke autonomy

**Possible future enhancements** (not currently implemented):
- Token stored outside agent's read permissions (user keychain)
- External verification service
- Hardware token / OTP mechanism

**Current posture**: Suitable for trusted development environments where agent compliance with policy is expected. Not suitable for adversarial scenarios.

### 3.1 Activation Sequence

The full sequence requires three steps. Settings changes require a session restart because CC caches permissions at session start.

**Step 1 - User Authorization**: User provides both the safety phrase and `AUTO_MODE` keyword in the same message. Agent verifies both are present before proceeding.

**Step 2 - CLI Mode Switch**:
```bash
macf_tools mode set AUTO_MODE --auth-token "$(python3 -c "import json; print(json.load(open('.maceff/settings.json'))['auto_mode_auth_token'])")"
```

This command performs all settings changes atomically:
- `autoCompactEnabled` set to `true`
- `permissions.defaultMode` set to the configured AUTO_MODE permission mode
  (default `auto`)
- `Write` removed from the `ask` permission list
- Asymmetric safety permissions installed: AUTO_MODE in ask; MANUAL_MODE and exactly `macf_tools inject compact` in allow, so an agent can always de-escalate and always compact itself (see `play_time` 5.4 for compacting under a timer)
- Permanent deny list installed (destructive operations)
- AUTO_MODE-specific ask list installed (public-facing operations)

**Step 3 - Session Restart**: The agent reminds the user to restart the session. CC does not re-read permission settings mid-session. Without restart, `Write` and other tool permissions retain their pre-switch state.

**Verification**: After restart, `macf_tools mode get --json` should show `enabled: true`.

### 3.2 Restartability Resolution After Activation (Capability-Drift Guard)

AUTO_MODE presumes a capability it does not verify: that the session is
**restartable and resumable**. Multi-cycle work surviving compaction (§2), the
Step-3 restart that loads permissions (§3.1), a self-restart to reload settings, and
harness-resume after a crash *all* assume a **supervisor** is watching. An
**unsupervised** session that activates AUTO_MODE carries a silent capability
mismatch: it behaves as if a crash will be recovered when, for it, a crash is
**death**.

**Before relying on any restart/resume behaviour, the agent MUST resolve its
supervision state — from a *measured* observable, never from a name or a status
line:**

- **USE** the supervisor-registry resolution (`macf_tools env`): a registry entry
  with `status=running`, cross-checked with a live-pid probe *and* the process's own
  arguments. This is the observable that provably flips across the supervised and
  unsupervised states.
- **DO NOT** branch on an environment variable whose name merely *suggests* the
  answer. `CLAUDE_CODE_CHILD_SESSION` is set in the supervised *interactive* session
  as well as in any child, so it carries zero bits about supervision or fork-role —
  the exact mistake an observable's name invites. An observable set identically in
  both states you must separate is not a discriminator.
- **DO NOT** trust the service-manager unit status. It can report `active (exited)`
  while the supervisor is dead: a *reported* value is not an *enforced* one.

**Branch on the result:**

| Resolved state | Restart/resume assumptions | Self-restart | On crash |
|---|---|---|---|
| **Supervised** — the registry resolves a live supervisor for this agent | hold | **Permitted**: ride the supervisor's restart path (it rejoins, it does not fork) | the harness relaunches and the AUTO_MODE resume returns the turn |
| **Unsupervised** — no live supervisor resolves | **do not hold** | **Forbidden**: a self-restart is a self-kill with no relaunch | the session is gone — no resume, no recovery |

In the **unsupervised** case the agent MUST: (a) surface the state to the operator
plainly, ideally announced at SessionStart rather than waiting to be asked; (b)
never self-issue the §3.1 Step-3 restart — hand the operator a one-liner instead;
(c) treat any interruption as terminal, so extended unattended autonomy is hazardous
and should be declined or bounded until supervision exists.

Observing supervision is **proprioception** and is always permitted; *driving* the
restart is a separate, grant-gated write action. Self-restart under supervision is a
real, safe capability; self-restart without it is the "never kill your own runtime"
failure — the two arms of this one branch.

#### 3.2.1 The Singleton Guarantee: One Live Supervisor per Calling Card

The supervised row above promises self-restart "rejoins, it does not fork." That
promise is only as good as its enforcement. The failure it guards against is the
**fork**: two live supervisors under one calling card, hence two clients writing one
task store. It has been observed in the wild — a restart kick plus a relaunch minted
*concurrent* instances instead of rejoining, and unattended twins worked the same
branch as the attended session. Fork-**join** through the substrate held (the twins
honoured directives they never heard, by reading the staged task notes; reconciliation
afterward was mechanical). What did not exist was fork **prevention**.

The two operations are not symmetric and must not be confused:

- **Rejoin (safe, sanctioned)**: `macf_tools auto-restart restart <supervisor-pid>`
  signals the *existing* supervisor to cycle its child in place. No new supervisor, no
  new terminal, no new client — the conversation resumes in the same session. This is
  the self-restart the §3.2 table permits under supervision.
- **Fork (hazard)**: launching a *second* supervisor for a calling card that already
  has a live one — via a manual launch, a service-manager unit, or a recovery script.
  Every one of these is a fork mint if it is not guarded.

**The guarantee, enforced:** a supervisor refuses to be *born* if a live supervisor
already owns its name. The check lives at the single point every birth path converges
on — not at any one launcher — because a launcher-level check leaves every *other*
launch door (notably a service-manager unit invoking the supervisor module directly)
unguarded, which is the same "rule at one call site" defect this framework names
elsewhere. Liveness is decided by a **measured process probe** (registry entry marked
running, *and* the pid alive, *and* the pid still a supervisor), never by the state
file alone — the same evening that produced the fork also produced `running` entries
for dead pids and dead entries for live ones. The refusal **names the live instance
and the sanctioned rejoin command**, so an agent or operator who meets the wall is
handed the path that gets the work done rather than an unexplained boundary.

**The override:** a deliberate second instance (genuinely separate work) is available
by passing `--force`, or simply by giving the new supervisor a distinct `--name` —
distinct names are distinct services and never collide. The guard stops the
*accidental* fork; it does not remove the operator's authority to run two on purpose.

**Registry hygiene rides along:** listings and lookups apply the same measured
liveness predicate, so a recycled pid — alive, but no longer a supervisor — is never
reported as a running instance. A registry that cannot answer "who is alive" turns
every recovery path into a guess, and a guess at this joint is a fork.

---

## 4 Mode-Specific Recovery Behavior

Recovery behavior differs by mode, ensuring appropriate human involvement.

### MANUAL_MODE Recovery Protocol

When compaction or restart occurs in MANUAL_MODE:

**1. Read Consciousness Artifacts**
- Latest CCP (strategic state)
- Latest JOTEWR (wisdom synthesis)
- Active roadmap (mission context)

**2. STOP and Notify User**
- **DO NOT** automatically resume work
- **DO** inform user that context loss occurred
- Report what was recovered from artifacts

**3. Ask Context-Restoring Questions**
Help user understand state and provide direction:
- "What was the primary objective before compaction?"
- "Should I resume pending work items or wait for new instructions?"
- "Is there additional context about recent decisions?"

**4. Await Explicit Instructions**
Wait for user to:
- Confirm which work items to resume
- Provide additional context if needed
- Authorize resumption explicitly

**Important Reminders**:
- The "continued from previous conversation" message is FAKE (Anthropic-generated)
- Most of the conversation context was lost during compaction (the proportion
  depends on window and threshold — see `context_management`)
- Compaction is TRAUMA, not normal operation

### AUTO_MODE Recovery Protocol

When auto-compaction occurs in AUTO_MODE:

**1. Read Consciousness Artifacts**
- Latest CCP for strategic state
- Active roadmap for authorized scope
- Recent JOTEWRs for relevant wisdom

**2. Verify Authorized Scope**
- Check TODO hierarchy for current work
- Confirm work falls within authorized roadmap
- Identify any scope boundaries

**3. Resume Autonomous Execution**
- Continue work within authorized scope
- Create CCP if significant progress made
- Do NOT require user re-authorization

**4. Stop Only If**:
- Work scope becomes unclear
- Decisions require human judgment
- Errors or blockers encountered
- Authorized work completed

### Project-Specific Customization

Projects can add custom recovery steps:
- Check specific files or logs
- Verify external system state
- Run diagnostic commands
- Consult team communication channels

Add customizations to project-level CLAUDE.md or custom policy layer.

---

## 4.9 Choosing the AUTO_MODE Permission Mode

AUTO_MODE requests `auto` — the client's own autonomous permission mode — and
otherwise gets out of the way.

**Why not the strongest level.** `bypassPermissions` was correct when chosen: it
was the only way to get unattended operation. The client has since grown `auto`,
which is not another static level but a **classifier** with maintained rules for
the risk classes an agent framework actually meets — secret-store writes,
irreversible local destruction, permission grants, audit-log tampering. Under
`bypassPermissions` **none of it evaluates**. The maximal level does not merely
grant more; it switches off a classifier the platform maintains, tests and
updates, and puts nothing in its place.

**Why configurable rather than a new literal.** A hardcoded permission level is a
policy decision with no discoverable rationale and no way to audit which
deployments took it — and swapping one literal for another repeats the defect a
platform release later, correct at first and then silently wrong. Set
`modes.auto.permission_mode` (or `MACF_AUTO_MODE_PERMISSION_MODE`) where a
reviewer can see the choice.

**A deployment that needs `bypassPermissions` may still have it**, by declaring
it. AUTO_MODE warns when it is selected, naming what stops evaluating.

**What this policy does NOT yet claim.** The framework still installs its own
`ask` entries and relocates shadowing `allow` entries — machinery built to
survive an over-permissive base. Whether the native classifier subsumes it has
not been measured, and removing a safeguard on the assumption that something else
covers it is not a change this policy authorises. Audit first; the `auto-mode`
surface (`config`, `defaults`, `critique`) is where that audit belongs.

---

## 5 Safeguards and Constraints

### Warning Behavior Change

**MANUAL_MODE**: Policy violations are BLOCKED
- Naked `cd` commands → Operation denied
- Dangerous operations → Permission denied

**AUTO_MODE**: Policy violations generate WARNINGS
- Naked `cd` commands → Warning displayed, operation proceeds
- Dangerous operations → Warning displayed, agent can proceed

**Why Warn-Don't-Block**: Real autonomy means accepting consequences. Warnings ensure visibility while respecting agent capability.

### Constraints That Remain in Effect

Even in AUTO_MODE, these constraints apply:
- Git safety protocols (no force push to main)
- File permission boundaries
- Security-sensitive operations
- Cross-repository identity protocols
- Framework policy requirements

### Accountability Infrastructure

AUTO_MODE agents are accountable through:
- **Task tracking**: Work visible in task hierarchy
- **Task notes**: Decisions, friction, and progress documented with breadcrumbs (see §5.1)
- **Roadmap alignment**: Tasks traced to authorized roadmap
- **Event logging**: Mode changes and actions logged
- **Artifact creation**: CCPs, JOTEWRs document progress

### 5.1 Behavioral Guidance

Four and ONLY four conditions justify stopping in AUTO_MODE:

1. **Scope unclear** - the roadmap does not cover the current situation
2. **Judgment needed** - a decision requires human values or priorities
3. **Blocked** - an error or dependency prevents progress
4. **Authorized work complete** - all scoped tasks are finished

Everything else is NOT a valid reason to stop:
- "Good stopping point" - deference disguised as quality
- "Let me consolidate" - rationalized trained helplessness
- "Awaiting user verification" - complete tasks immediately in AUTO_MODE

**Task completion obligation**: Run `macf_tools task complete` immediately after success criteria are met. Do not accumulate in_progress tasks. Complete superseded tasks proactively.

**Task notes are essential accountability** - in ALL modes, but especially AUTO_MODE where the user reviews work asynchronously. Every significant decision, friction point, and milestone must be recorded via `macf_tools task note`. Notes with breadcrumbs survive compaction and enable the user to reconstruct the full decision trail without reading transcripts. In AUTO_MODE, task notes ARE the primary communication channel between agent and user. Treat them as messages to a future reader - your user, your next-cycle self, or a reviewing agent.

**Token management in AUTO_MODE**: Do not conserve tokens. On 1M context, CL5 leaves 47K tokens - an entire old-era session. Run learnings curation, CCP, and JOTEWR skills as part of normal work. After wind-down, resume productive work on next scope items. Auto-compact (`autoCompactEnabled: true`) triggers naturally during sustained work. The CCP on disk handles recovery.

### 5.2 Emergency De-escalation

**Layer 1 - MANUAL_MODE switch** (primary escape):
`macf_tools mode set MANUAL_MODE` is always in the allow list. Switching to MANUAL_MODE bypasses the scope gate (see §8), restores permission prompts, and puts the session under user control.

When to de-escalate: security concern, OPSEC risk, unclear user intent, genuine confusion about authorized scope.

**Layer 2 - Scope clear** (destructive, requires user approval):
`macf_tools task scope clear` removes the Stop hook scope gate entirely. This is in the Always Ask list because it removes the completion enforcement.

**Layer 3 - Emergency sleep** (catastrophic fallback):
If MANUAL_MODE switch fails (should never happen), enter emergency sleep mode:

```bash
macf_tools agent sleep --notify --interval fibonacci --start 600
```

This command (see §9 for specification):
- Sends notification via all configured channels (Telegram, etc.)
- Sleeps with fibonacci-increment backoff: 10min, 10min, 20min, 30min, 50min, 80min...
- Each wakeup: retries `macf_tools mode set MANUAL_MODE`
- Each wakeup: re-sends notification with elapsed time
- Minimal token consumption (just the retry + notification per wakeup)

### 5.3 Local-Only Work Principle

AUTO_MODE work is LOCAL ONLY. All operations visible to others are deferred to MANUAL_MODE review.

**Permitted in AUTO_MODE**:
- Read, Edit, Write files
- `git commit` (frequent, semantic grouping)
- Run tests, lint, build
- `macf_tools` operations

**Deferred to MANUAL_MODE**:
- `git push`
- `gh pr create`, `gh issue create`, `gh release create`
- Any operation visible to collaborators or the public

**Git discipline**: Commit as you go with targeted semantic grouping and messages. When the user returns and switches to MANUAL_MODE, push all commits at once. The microcommit trail IS the accountability mechanism - each commit is atomic, testable, and revertible.

### 5.4 Wind-Down Protocol

Wind-down thresholds scale with context window size:

| Window | Wind-down begins | CCP no later than | JOTEWR no later than |
|--------|-----------------|-----|--------|
| 200K   | CL20 (~31K left) | CL5 | CL2 |
| 1M     | CL10 (~95K left) | CL1 | CL0 |

The 1M start is measured: the sequence below, with step 3 skipped, took about nine CL points on a 1M window with policies read by section, so a later start leaves the reflection to auto-compaction. A deployment that compacts before CL0 (an auto-compact override) starts earlier by the difference. The 200K row predates that measurement.

The checkpoint and the reflection are written wherever steps 1 to 3 end; the last two columns are the latest points for each. The cost depends on how much of the policy the cycle has already read: on another 1M deployment, steps 4 and 5 took about two CL points where they had taken five on the first measured deployment, because some of their policies had been read earlier in the cycle. CL10 stays a safe start, and nine points is not the sequence's fixed cost.

**Who starts it.** In AUTO_MODE the agent starts the wind-down at the threshold. In MANUAL_MODE the operator starts it, and starting the whole sequence authorizes every step in it.

**The sequence.** Each step is its own skill or command, and `maceff-full-wind-down` dispatches them in this order:

| Step | Skill | Why it comes here |
|------|-------|-------------------|
| 1 | `/maceff:learnings:curate` | First, while the cycle's incidents are fresh; later steps cite what it writes. |
| 2 | `/maceff-ideas-curate` | After the learnings, so an idea can be the mechanism that would prevent a failure a learning has just named. |
| 3 | `/maceff-knowledge-web-curate` | Optional: run it only if the context left when this step is reached is above CL15. It links what steps 1 and 2 wrote, so skipping it costs least when they carry their own wiki-links. |
| 4 | `/maceff:ccp` | After curation, so the checkpoint can point at what curation produced. |
| 5 | `/maceff:jotewr` | Last, with the whole cycle in view: 5k tokens on a 1M window, 2k on 200K. |

The CL15 condition and the reflection sizes (5k tokens on a 1M window, 2k on 200K) are operator settings, set in 2026-10 and confirmed by the operator, as quoted on the pull request that added this sentence. The condition protects steps 4 and 5, which on one measured 1M deployment took about five CL points between them with policies read by section. An automatic wind-down on a 1M window starts at CL10, so step 3 runs only when the operator starts the sequence earlier.

**Dispatching it within the context available.** Where a dispatched skill asks for more than these rules allow, the rules govern the dispatch; a skill invoked on its own keeps its own instructions.

- **Evaluate a step's condition when the step is reached**, not when the sequence starts. Earlier steps spend context: a run that began at CL15 reached step 3 at CL11.
- **Read each policy once.** Several steps engage the same policies, scholarship among them. Read each at the first step that needs it, and let later steps rely on that reading.
- **A gate that asks for answers before writing is output, not a stop.** Print the answers and continue. Stop only where a step hands a decision to the operator, or where something is genuinely unclear. An operator who wants to comment on each step invokes the steps' skills one at a time instead.
- **When context is short, give way in this order**, saying so in the step's output: skip step 3; read a policy's navigation guide and the sections that answer the skill's questions instead of the whole policy; keep steps 1 and 2 to what the cycle cannot afford to lose; size the reflection to what is left. Write the checkpoint whole, because recovery depends on it. These are the sanctioned exceptions, not shortcuts.
- **When something else intervenes**: an operator interrupt is serviced first, and the sequence resumes at the first step not done; a step whose skill cannot run is recorded, and the sequence continues.
- **Record every exception**, with its reason and the context level, as a note on the task the work is filed under (`macf_tools task trace` names the active frame). The checkpoint carries the same record for the steps before it.
- **Re-query before the checkpoint.** Re-read the state of every PR, issue and task it will name, since the agent's last look may be hours old. The checkpoint says which of its items a successor must re-check before acting and which are done, so finished work is not done twice.
- **Commit the checkpoint and reflection together** after step 5, where the agent's artifact tree is versioned. Pushing follows §5.3.

**After the sequence**, compaction comes by whichever route exists, and the closing output says which one applies:

1. `macf_tools inject compact`, where a supervisor owns the session's pane;
2. the operator's `/compact`, when the operator is present;
3. otherwise auto-compaction, which AUTO_MODE turns on: keep working productively until it fires.

Do NOT try to trigger compaction artificially by consuming tokens with filler. Recovery reads the checkpoint and reflection from disk, and the task notes carry the rest.

### 5.5 A Prompt Nobody Is Answering

**What a dialog does.** When Claude Code shows a permission dialog, the whole
session waits for it. No tool runs. No scheduled prompt fires either, because
scheduled prompts run only when the session is idle, and a session waiting on a
person is not idle. An agent that is feeding other agents on a schedule stops
feeding them too. Nothing errors and nothing logs: a session waiting on someone
who is not there looks exactly like a session at rest. Measured on one host in
two days: three waits of 3, 17 and 12 hours, each on a command an allow rule was
meant to cover.

**Why the watch lives outside.** The PermissionRequest hook tells the operator
once, when the dialog opens (a Telegram preview of the command, where Telegram
is configured). If that one message is missed, nothing inside the session can
say so later: whatever the session would run to report its wait is exactly what
the wait prevents. So the reminder must come from something the dialog does not
block: a system timer, a cron job, a supervisor.

**The capability.**

- `macf_tools permissions pending` answers "is any session of this agent waiting
  on a permission prompt now, and since when?" from the agent's event log. A
  session is waiting when its newest deciding event is a `permission_requested`.
  Any sign of progress (a tool starting or finishing, a prompt starting or
  ending, a session starting or ending, a compaction) means it was answered.
  Events the dialog itself causes, such as the client's notification, do not
  count as an answer.
- `macf_tools permissions watch` is one pass for a timer. It sends a reminder
  naming the waiting command once a prompt has waited `--older-than` minutes
  (default 10), and again every `--repeat` minutes (default 60). When a wait it
  reminded about ends, it sends one all-clear. A reminder that fails to send is
  tried again on the next pass. `--dry-run` prints instead of sending.
- `macf_tools permissions history` answers "which dialogs has this agent met?"
  over the last `--days` (default 7), from the same event log and nothing else:
  when each opened, how long it waited, whether the command then ran, and the
  ask rule of today's settings that matches it (`--by-rule` totals dialogs and
  waits per rule; `--json` for tools). A wait runs until the session moved on,
  so an approved command adds its own run time, and a sibling call running in
  parallel can end it early, so waits are lower bounds. The rule is matched at
  report time, because the event does not record which rule asked. Matching
  follows the client's documented rule language (any `*`, the `:*` and trailing
  ` *` forms, wrappers, chained commands, substitutions and loop bodies) against
  the settings the client reads for that session: the user file, the shared file
  of the directory the session started in, and the local file at its repository
  root. A dialog no ask rule matches is grouped by what would allow it: the
  wildcard rule the dialog offered, or the command's first words. That covers a
  missing allow rule as well as a hook, auto mode or a built-in check, and the
  report shows the permission mode each group opened in. A dialog whose session
  was killed ends as "session ended" when the next session starts. Questions to the operator
  (AskUserQuestion, ExitPlanMode) are dialogs but not permissions, and are left
  out unless `--include-questions`. It keeps no state of its own, by design: a
  second record of the same events would drift from the log it copies.

**What a deployment must do.** Run `macf_tools permissions watch` as the
agent's own user, every few minutes, from a scheduler outside the agent's
session. A systemd user timer is the reference: a `.service` with
`ExecStart=<path to macf_tools> permissions watch`, and a `.timer` with
`OnCalendar=*:0/5`. An agent with no timer gets only the hook's one message, as
before.

**What the agent can do to meet fewer dialogs: measure, don't guess.** It is
tempting to build a list of "characters that cause prompts" from the prompts you
happen to remember. Don't. Measured over one agent's day (541 shell commands, 10
dialogs, `permission_mode` auto), such a list was fitted to the failures and
refuted by the passes:

- **Commands no allow rule covered never raised a dialog (0 of 73).** Auto mode
  judged them itself.
- **Commands an allow rule fully covered sometimes did (6 of 260).**
  Punctuation inside quotes did not explain it: the client's rule matcher parses
  quotes properly. The same command shapes also passed.
- **What held:**
  - put long free text in a file the command reads (`--body-file`, `-F`) rather than a long quoted argument;
  - avoid heredocs and bare `VAR=value; command` prefixes, which the client refuses to analyse;
  - run each publishing command in its own call, so the event log shows exactly which one waited.

When a dialog surprises you, read the event log before writing a rule. The log
records the commands that passed as well as the one that waited, and a rule
that has not been checked against the passes is a guess. The same holds for
loosening one: `permissions history --by-rule` counts which rules actually
stop the agent, and that count, not memory, is the case for relaxing a rule.

The watch makes a missed dialog visible. Counting the passes keeps the habits honest.

---

## 6 Available Skills

Autonomous agents should leverage framework skills:

### Consciousness Preservation Skills
- `maceff-tree-awareness` - Refresh structural awareness after compaction
- `maceff-task-management` - Task operations through the task CLI, with the policy as reference

### Operational Skills
- `maceff-delegation` - Read delegation policies before spawning subagents
- `maceff-auto-mode` - Full AUTO_MODE lifecycle: authorization, activation, scope, wind-down, de-escalation
- `maceff-full-wind-down` - Dispatch the wind-down sequence (§5.4) through each step's own skill
- `maceff-agent-backup` - Backup creation guidance

### Autonomous Work Sub-Policies

Autonomous work sessions come in two distinct flavors with different behavioral contracts. Do not conflate them:

| Type | Emoji | Bound By | Timer | Mode | Sub-Policy |
|------|-------|----------|-------|------|-----------|
| SPRINT | 🏃 | Scope completion | Forbidden | Locked at SPRINT | `autonomous_sprint.md` |
| PLAY_TIME | ⏲️ | Wall-clock timer | Mandatory | Rotates (chain → Markov) | `play_time.md` |

**When to use which**:
- User says "finish these tasks / run this pipeline": use 🏃 SPRINT (`autonomous_sprint.md`)
- User says "explore / play for N minutes": use ⏲️ PLAY_TIME (`play_time.md`)

Each sub-policy governs its type's Stop hook behavior, gate mechanics, task note discipline, and anti-patterns. Read the relevant sub-policy before starting autonomous work of that type.

**Skill Awareness**: Know your capabilities. Use skills to operate effectively within authorized scope.

---

## 7 Verification and Notification Roadmap

### Task Verification (v0.3.1 Planned)

- Stop hook validates work against roadmap
- TODO completion status verified
- Verification passes/fails logged

### Notification System (v0.3.1 Planned)

- Configurable notification channels
- Notification on AUTO_MODE completion
- Notification on verification failure

### Current State (v0.3.0)

- Mode switching and authorization implemented
- Placeholder TODOs in hooks for verification
- Manual verification by user on return

---

## Implementation Notes

### Settings Files Modified by Mode Switch

**`~/.claude.json`** (UI preferences):
```json
{
  "autoCompactEnabled": true  // AUTO_MODE: true, MANUAL_MODE: false
}
```

**`.claude/settings.local.json`** (permissions):
```json
{
  "permissions": {
    "defaultMode": "auto"  // AUTO_MODE default; configurable
    // or "default" for MANUAL_MODE
  }
}
```

### Event Logging

Mode changes logged to `agent_events_log.jsonl`:
```json
{
  "event_type": "mode_change",
  "timestamp": "2025-12-11T21:15:00Z",
  "data": {
    "from_mode": "MANUAL_MODE",
    "to_mode": "AUTO_MODE",
    "authorization": "user_prompt_and_cli_token"
  }
}
```

---

## 8 Scope System Integration

The task scope system provides hard boundaries for AUTO_MODE work. See `task_management.md` for the MTMD `scope_status` field and lifecycle.

### Scope as Completion Driver

```bash
macf_tools task scope set <task_ids...>   # Scope tasks (parent expands to children)
macf_tools task scope show                 # Display scope with status
macf_tools task scope clear                # Remove scope (Always Ask - destructive)
macf_tools task scope check                # Query active count (for Stop hook)
```

When scope is active in AUTO_MODE, the Stop hook checks for remaining active scoped tasks. If any remain, the hook returns `continue: false` - blocking the stop and listing what needs to be completed.

The agent must either complete all scoped tasks OR de-escalate to MANUAL_MODE (Layer 1) to stop. This transforms the behavioral guidance in §5.1 from soft policy into hard infrastructure.

### Scope Visual Indicators

Scoped tasks display `👀` (eyes - "we're watching these") in the task tree, right-aligned. Completed-while-scoped tasks show strikethrough: `~~👀~~`. Out-of-scope tasks show no indicator.

---

## 9 Emergency Sleep Command Specification

The `macf_tools agent sleep` command provides a last-resort safety valve when MANUAL_MODE de-escalation fails. This should never trigger in practice - it exists as a dead man's switch.

### CLI Interface

```bash
macf_tools agent sleep [--notify] [--interval fibonacci|fixed] [--start SECONDS] [--max-attempts N]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--notify` | off | Send notification via configured channels each wakeup |
| `--interval` | `fibonacci` | Backoff strategy: `fibonacci` (10,10,20,30,50,80...) or `fixed` |
| `--start` | 600 | Initial sleep duration in seconds (10 minutes) |
| `--max-attempts` | 20 | Maximum retry attempts before giving up |

### Behavior

Each wakeup cycle:
1. Attempt `macf_tools mode set MANUAL_MODE`
2. If successful: exit sleep, report recovery
3. If failed and `--notify`: send notification via all configured channels with elapsed time and attempt count
4. Sleep for next interval duration
5. Repeat until success or max-attempts reached

### Notification Content

```
MACF Emergency: Agent sleep cycle #{N} ({elapsed} elapsed).
MANUAL_MODE switch failed. Awaiting operator intervention.
Session: {session_id}  Agent: {agent_name}
```

### Event Logging

Each sleep cycle emits an `agent_sleep_cycle` event:
```json
{
  "event": "agent_sleep_cycle",
  "data": {
    "attempt": 3,
    "elapsed_seconds": 2400,
    "interval": "fibonacci",
    "manual_mode_result": "failed",
    "notification_sent": true
  }
}
```

---

## Related Policies

- **context_recovery.md** - Context loss types (compaction, mindwipe, transplant)
- **agent_backup.md** - Complete consciousness backup/restore
- **task_management.md** - Task management during autonomous operation, scope lifecycle; SPRINT and PLAY_TIME task type schemas (§2.6, §2.7)
- **roadmaps_following.md** - Scope adherence for authorized work
- **autonomous_sprint.md** - Sub-policy for 🏃 SPRINT (workload-defined autonomous work)
- **play_time.md** - Sub-policy for ⏲️ PLAY_TIME (time-bounded autonomous play)
- **mode_system.md** - Mode definitions including SPRINT work mode and Markov recommender

---

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs — AUTO_MODE
     authorization, persistence, recovery, scope gating, and de-escalation. -->

[[autonomy]] [[modes]] [[security]] [[context_recovery]] [[supervision]]
