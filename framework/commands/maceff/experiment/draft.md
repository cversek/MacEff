Create a MacEff-compliant experiment protocol by reading policies for structure guidelines, then drafting according to established patterns.

**Argument**: Brief description of the experiment hypothesis or topic

---

## 🚨 CHANNEL-INITIATED EXCEPTION (Telegram / Remote)

**If this command was triggered by a message from a `<channel source=...>` tag** (e.g., Telegram), the following modal tools are BLOCKED because CC does not relay them to channels:

- ❌ **EnterPlanMode** / **ExitPlanMode** — causes silent deadlock for channel users
- ❌ **AskUserQuestion** — renders only in terminal, invisible to channel

**Channel-mode workflow instead**:
1. Skip EnterPlanMode entirely
2. Create the EXPERIMENT task by invoking `/maceff:task:create_experiment` — NOT the
   raw `macf_tools task create experiment`. The command is where per-type framework
   requirements live; calling the CLI directly bypasses them.
3. Read the skeleton protocol.md
4. Write experiment content directly to the CA (user approves via Write permission + inline feedback)
5. Use `mcp__plugin_telegram_telegram__reply` for questions instead of AskUserQuestion
6. Do NOT use ExitPlanMode — the Write approval IS the execution gate

---

## EnterPlanMode (MANDATORY — terminal only, see channel exception above)

🚨 **FIRST ACTION**: Enter PlanMode before any exploration or drafting.

**Why**: PlanMode creates deliberation friction, separating planning from execution. User approval via ExitPlanMode gates the transition to implementation.

---

## Exploration Phase (ENCOURAGED)

**Questions to assess**:
1. Is the hypothesis clear or does it require codebase exploration?
2. Are there existing patterns that inform the experiment design?
3. Is technical feasibility uncertain?
4. Did the user explicitly request exploration?

**If exploration needed**: Launch 1-3 Explore subagents in parallel per `{POLICY_EXPLORATION_GUIDANCE}`.

**When to skip**: Hypothesis is clear, approach is obvious, or experiment is conceptual/phenomenological.

---

## Clarification Phase (ENCOURAGED)

**Questions to assess**:
1. Do multiple experimental approaches exist?
2. Do user preferences matter (scope, risk, duration)?
3. Are there trade-offs that need user input?

Use AskUserQuestion if any apply.

---

## Policy Reading (MANDATORY)

Before drafting, read these policies to understand requirements:

```bash
macf_tools policy navigate experiments
macf_tools policy read experiments
```

**Why CLI tools**: Caching prevents redundant reads, line numbers enable precise citations.

---

## Questions to Answer from Policy Reading

After reading policies, **report answers to user before any state-changing tools**:

1. **What preliminary planning workflow does the policy specify?**
   - What gates the transition from planning to execution?
   - When is exploration encouraged vs skipped?
   - What role does PlanMode play?

2. **What distinguishes experiments from other CA types?**
   - What triggers experiment vs observation vs report?
   - What makes something hypothesis-testing?

3. **What preliminary work does the policy require?**
   - What must happen before formal protocol creation?
   - What validates feasibility?

4. **What directory structure does the policy specify?**
   - What is the naming convention?
   - What subdirectories are required?

5. **What protocol sections does the policy require?**
   - What metadata is mandatory?
   - What hypothesis format is specified?
   - What method documentation is required?

6. **What reflection discipline does the policy specify?**
   - When must reflection occur?
   - Where do reflections go?

7. **What TODO integration does the policy require?**
   - How are experiments pinned?
   - What markers distinguish experiment items?

---

## Execution

After reporting policy-extracted answers:

1. **Follow preliminary requirements** as specified by policy
2. **Create directory structure** per `{POLICY_SPECIFIED_STRUCTURE}`
3. **Draft protocol** with `{POLICY_REQUIRED_SECTIONS}`
4. **Include reflection points** per `{POLICY_REFLECTION_DISCIPLINE}`
5. **Verify against policy** before completion

🚨 **CRITICAL - Protocol vs Plan File**:
- Claude Code's native plan files are **NOT compliant** consciousness artifacts
- Plan file content is for drafting only - transfer to compliant protocol CA
- This command creates the PROTOCOL only - execution via `/maceff:task:start <task_id>` separately

---

## Post-Drafting Checklist (MANDATORY)

After ExitPlanMode approval, complete these steps:

1. **Create task atomically**:
   ```bash
   macf_tools task create experiment "Your Title"
   ```
2. **Copy plan content** to the skeleton protocol.md created by CLI
3. **Create subdirectories** if needed: `artifacts/`, `archived_tasks/`
4. **Report** task ID and protocol path
5. **🛑 STOP** - Await `/maceff:task:start #{TASK_ID}`

**Note**: The CLI creates the folder structure (with auto-numbered NNN), skeleton protocol.md, and task with MTMD automatically.

---

## Wiki-Links Section (REQUIRED)

Before saving, the artifact MUST carry a `## Wiki-Links` section. This is what connects it to the knowledge web. Without it the artifact is an **orphan**: present on disk, reachable only by someone who already knows it exists, and invisible to the concept query a successor would actually use to find it.

**What to link**: consult the experiments policy on **knowledge web participation** for what this artifact type should link and what it should avoid. `protocol.md` and `analysis.md` each carry the section; evidence files under `data/`, `artifacts/` and `quick_tests/` do not. Link the conceptual area under investigation, not the apparatus that happened to be used.

**How to choose**: query the graph before inventing a concept — `macf_tools knowledge query <concept>` — so you connect to vocabulary the corpus already uses instead of coining a near-duplicate that connects to nothing. Two to five concepts.

**Do not emit an empty heading.** A `## Wiki-Links` section with no links is worse than its absence: it satisfies a checker while leaving the artifact exactly as unreachable.

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths.

---

**Meta-Pattern**: Policy as API - this command extracts requirements from policies at runtime. Metavariables (`{POLICY_*}`) are filled during policy reading, ensuring the workflow adapts as policies evolve.
