Create a MacEff-compliant experiment protocol by reading policies for structure guidelines, then drafting according to established patterns.

**Argument**: Brief description of the experiment hypothesis or topic

---

## Policy Reading (MANDATORY)

Before drafting, read these policies to understand requirements:

1. **Experiments Policy** - Protocol structure, phases, success criteria:
   ```bash
   macf_tools policy navigate experiments
   macf_tools policy read experiments
   ```

2. **Path Portability** (for framework experiments) - Portable path conventions:
   ```bash
   macf_tools policy read path_portability
   ```

**Why CLI tools**: Caching prevents redundant reads, line numbers enable precise citations.

---

## Questions to Answer from Policy Reading

After reading policies, **report answers to user before any state-changing tools**:

1. **What distinguishes experiments from other CA types?**
   - What triggers experiment vs observation vs report?
   - What makes something hypothesis-testing?

2. **What preliminary work does the policy require?**
   - What must happen before formal protocol creation?
   - What validates feasibility?

3. **What directory structure does the policy specify?**
   - What is the naming convention?
   - What subdirectories are required?

4. **What protocol sections does the policy require?**
   - What metadata is mandatory?
   - What hypothesis format is specified?
   - What method documentation is required?

5. **What reflection discipline does the policy specify?**
   - When must reflection occur?
   - Where do reflections go?

6. **What TODO integration does the policy require?**
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

After ExitPlanMode approval, complete these steps using policy-extracted values:

1. **Create experiment folder** - `{POLICY_NAMING_CONVENTION}`
2. **Create subdirectories** - `{POLICY_REQUIRED_SUBDIRS}`
3. **Transfer plan to protocol** - `{POLICY_PROTOCOL_LOCATION}`
4. **Pin TODO** - `{POLICY_TODO_FORMAT}` with `{POLICY_EXPERIMENT_MARKER}`
5. **🛑 STOP** - Report completion and AWAIT `/maceff:todos:start`

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths.

---

**Meta-Pattern**: Policy as API - this command extracts requirements from policies at runtime. Metavariables (`{POLICY_*}`) are filled during policy reading, ensuring the workflow adapts as policies evolve.
