---
description: Archive TODO hierarchy using MacEff framework policy guidance
argument-hint: [phase_description] [STATUS]
allowed-tools: Read, Write, TodoWrite, Bash(macf_tools:*)
---

Archive completed TODO hierarchies by reading and following MacEff framework policy.

**Arguments**:
- Phase/task description for archive filename
- STATUS: COMPLETED, PARTIAL, ABORTED, or DEFERRED

---

## Policy Engagement Protocol

**Read MacEff framework policies to understand archival requirements**:

1. TODO hygiene - Archival patterns:
   ```bash
   macf_tools policy navigate todo_hygiene
   macf_tools policy read todo_hygiene --from-nav-boundary
   ```

2. Workspace discipline - Artifact naming conventions:
   ```bash
   macf_tools policy read workspace_discipline
   ```

**Why CLI tools**: Caching prevents redundant reads, line numbers enable precise citations.

---

## Questions to Answer from Policy Reading

After reading policies, you should be able to answer:

1. **What must happen BEFORE collapsing a TODO hierarchy?**
2. **What sections must the archive file contain?**
3. **Where should archive files be stored?**
4. **How should the collapsed TODO item be formatted?**
5. **What symbol distinguishes archived work from fresh completions?**
6. **How do you generate a forensic breadcrumb?**
7. **What constitutes a policy violation in this context?**
8. **After archiving, what minimum pending item requirement prevents UI disappearance?**
9. **Is this a cross-repo MISSION? Where should archives go for cross-repo work?**
10. **How should archive filenames identify the MISSION being archived?**
11. **What is the Agent CA Principle for TODO archives?**

---

## Execution

Using answers from policy reading, execute the archival pattern as policy describes.

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths or tool flags (`git -C`).

⚠️ **Sequential execution preferred** - concurrent tool calls can cause errors. Parallelize only when truly independent.

---

**Meta-Pattern**: Policy as API - this command uses `macf_tools policy` CLI commands for reading policies. CLI tools handle framework path resolution, provide caching, and output line numbers for citations.
