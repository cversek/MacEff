Create a MacEff-compliant experiment protocol by reading policies for structure guidelines, then drafting according to established patterns.

**Argument**: Brief description of the experiment hypothesis or topic

---

## EnterPlanMode (MANDATORY)

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
- This command creates the PROTOCOL only - execution via `/maceff:todos:start` separately

---

## Post-Drafting Checklist (MANDATORY)

After ExitPlanMode approval, complete these steps:

1. **Create task atomically**:
   ```bash
   macf_tools task create experiment "Your Title"
   ```
2. **Copy plan content** to the skeleton protocol.md created by CLI
3. **Create subdirectories** if needed: `artifacts/`, `archived_todos/`
4. **Report** task ID and protocol path
5. **🛑 STOP** - Await `/maceff:task:start #{TASK_ID}`

**Note**: The CLI creates the folder structure (with auto-numbered NNN), skeleton protocol.md, and task with MTMD automatically.

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths.

---

**Meta-Pattern**: Policy as API - this command extracts requirements from policies at runtime. Metavariables (`{POLICY_*}`) are filled during policy reading, ensuring the workflow adapts as policies evolve.
