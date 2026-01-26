Create a MacEff-compliant roadmap by reading policies for structure guidelines, then drafting according to established patterns.

**Argument**: Brief description of the roadmap topic

---

## Policy Reading (MANDATORY)

Before drafting, read these policies to understand requirements:

1. **Roadmap Drafting Guidelines** - Structure, phases, success criteria:
   ```bash
   macf_tools policy navigate roadmaps_drafting
   macf_tools policy read roadmaps_drafting --from-nav-boundary
   ```

2. **Path Portability** (for framework roadmaps) - Portable path conventions:
   ```bash
   macf_tools policy read path_portability
   ```

**Why CLI tools**: Caching prevents redundant reads, line numbers enable precise citations.

---

## Questions to Answer from Policy Reading

After reading policies, **report answers to user before any state-changing tools**:

1. **What preliminary steps does roadmaps_drafting.md require?**
   - What must happen before drafting begins?
   - What exploration or user interaction is specified?

2. **What folder structure does the policy specify?**
   - Where do roadmaps go?
   - What subdirectories are required?

3. **What sections must a roadmap contain?**
   - Header format and required fields
   - Phase structure requirements
   - Success criteria format

4. **What path conventions apply to framework roadmaps?**
   - How should policies be referenced?
   - What patterns are prohibited?

5. **What delegation strategy does §3.5 require?**
   - What executor options exist (PA DIRECT vs DELEGATE)?
   - What rationale must accompany each phase assignment?
   - When should `/maceff-delegation` skill be invoked?

6. **What phase content requirements does §3.6 specify?**
   - What should phases specify (interface/behavior)?
   - What is explicitly forbidden in phase descriptions?

7. **What task pinning protocol does task_management.md require?**
   - What must happen when a roadmap is approved?
   - How are roadmap phases represented in the task system?

---

## Execution

After reporting policy-extracted answers:

1. **Follow preliminary requirements** as specified by policy
2. **Create artifacts** per policy-specified structure
3. **Apply content requirements** extracted from policy
4. **Verify against policy checklist** before completion

🚨 **CRITICAL - Roadmap vs Plan File**:
- Claude Code's native plan files (`~/.claude/plans/`) are **NOT compliant** consciousness artifacts
- Plan file content is for drafting only - it must be **transferred to a compliant roadmap CA**
- This command creates the ROADMAP only - implementation via `/maceff:todos:start` separately
- Roadmap must be comprehensive enough to resume after complete context loss

---

## Post-Drafting Checklist (MANDATORY)

After ExitPlanMode approval, complete these steps **before any implementation**:

1. **Create task atomically**:
   ```bash
   macf_tools task create mission "Title" --repo REPO --version VERSION
   ```
2. **Copy plan content** to the skeleton roadmap.md created by CLI
3. **Report** task ID and roadmap path
4. **🛑 STOP** - Await `/maceff:task:start #{TASK_ID}` for phase expansion

**Note**: The CLI creates the folder structure, skeleton roadmap.md, and task with MTMD automatically.

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths.

⚠️ **Path portability required** - Use `{FRAMEWORK_ROOT}` for policy references.

---

**Meta-Pattern**: Policy as API - this command uses `macf_tools policy` CLI commands for reading policies. CLI tools handle framework path resolution, provide caching, and output line numbers for citations.
