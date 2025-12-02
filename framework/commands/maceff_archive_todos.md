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

1. `framework/policies/base/development/todo_hygiene.md` - TODO archival patterns
2. `framework/policies/base/development/workspace_discipline.md` - Artifact naming conventions

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

---

## Execution

Using answers from policy reading, execute the archival pattern as policy describes.

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths or tool flags (`git -C`).

⚠️ **Sequential execution preferred** - concurrent tool calls can cause errors. Parallelize only when truly independent.

---

**Meta-Pattern**: Policy as API - read current policy state, apply dynamically. When policy evolves, command stays current without updates.
