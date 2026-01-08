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

5. **What TODO integration does roadmaps_following.md require?**
   - How must new roadmaps be pinned to the TODO list?
   - What emoji/format distinguishes roadmap items?

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
- This command creates the ROADMAP only - implementation via `/maceff_todos_start` separately
- Roadmap must be comprehensive enough to resume after complete context loss

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths.

⚠️ **Path portability required** - Use `{FRAMEWORK_ROOT}` for policy references.

---

**Meta-Pattern**: Policy as API - this command uses `macf_tools policy` CLI commands for reading policies. CLI tools handle framework path resolution, provide caching, and output line numbers for citations.
