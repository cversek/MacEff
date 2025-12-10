---
description: Start work on TODO item with policy-guided context restoration
argument-hint: [todo_description_or_number]
allowed-tools: Read, TodoWrite, Bash(macf_tools:*)
---

Start work on a TODO item (new or archived) by reading policy to understand context restoration, scope assessment, and engagement patterns.

**Argument**: Description or number identifying the TODO item to start

---

## Policy Engagement Protocol

**Read MacEff framework policies to understand engagement patterns**:

1. TODO hygiene - Archive patterns, breadcrumb discipline:
   ```bash
   macf_tools policy navigate todo_hygiene
   macf_tools policy read todo_hygiene
   ```

2. Delegation guidelines - When to delegate, specialist capabilities:
   ```bash
   macf_tools policy read delegation_guidelines
   ```

3. Roadmaps following - When roadmaps required, structure patterns:
   ```bash
   macf_tools policy read roadmaps_following
   ```

**Why CLI tools**: Caching prevents redundant reads, line numbers enable precise citations, navigate guides cognitive framing before content.

---

## Questions to Answer from Policy Reading

After reading policies, you should be able to answer:

1. **Is this TODO archived?** How do I recognize and restore archived context?
2. **Does this TODO reference a roadmap/plan?** What's the mandatory reading discipline?
3. **Should I delegate this work?** What signals mandatory vs optional delegation?
4. **Does this need a detailed roadmap?** What triggers roadmap creation?
5. **Does this need a DELEG_PLAN?** What must delegation plans contain?
6. **Can I just execute?** When is simple execution appropriate?
7. **When work encounters unexpected friction, what documentation practices preserve learnings for future cycles?**
8. **What breadcrumb discipline applies?** When and how to generate breadcrumbs?

---

## Execution

🚨 **CRITICAL: Invoking this command IS execution authorization.**

The command name is `start_todo`, not `review_todo`. User running this command grants permission to BEGIN WORK immediately after policy reading completes.

Using answers from policy reading:
- Restore archived context if needed
- Read embedded plans per mandatory reading discipline
- Create roadmap/DELEG_PLAN if policy requires
- Mark TODO in_progress and **BEGIN EXECUTION** - do not ask for further permission

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths or subshells.

⚠️ **Sequential execution preferred** - concurrent tool calls can cause errors.

---

**Meta-Pattern**: Policy as API - policies guide WHEN to delegate, WHEN to create roadmaps, HOW to restore context. When policies evolve, command stays current.
