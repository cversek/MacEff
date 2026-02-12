---
description: Start work on task with policy-guided context restoration
argument-hint: [task_id_or_description]
allowed-tools: Read, TaskCreate, TaskUpdate, TaskGet, TaskList, Bash(macf_tools:*)
---

Start work on a task (new or existing) by reading policy to understand context restoration, metadata requirements, and engagement patterns.

**Argument**: Task ID (e.g., `#67`) or description identifying the task to start

---

## Policy Engagement Protocol

**Read MacEff framework policies to understand engagement patterns**:

1. Task management - Metadata, hierarchy, lifecycle:
   ```bash
   macf_tools policy navigate task_management
   macf_tools policy read task_management
   ```

2. Delegation guidelines - When to delegate, specialist capabilities:
   ```bash
   macf_tools policy read delegation_guidelines
   ```

3. Roadmaps following - Strategic planning patterns:
   ```bash
   macf_tools policy read roadmaps_following
   ```

**Why CLI tools**: Caching prevents redundant reads, line numbers enable precise citations, navigate guides cognitive framing before content.

---

## Questions to Answer from Policy Reading

After reading policies, you should be able to answer:

1. **What metadata does the policy require for this task?** How do I verify completeness?
2. **What task types does the policy define?** Which type is this task?
3. **What reading discipline does the policy specify?** What must I read before starting work?
4. **How does the policy define task relationships?** What structural information exists?
5. **What blocking semantics does the policy specify?** How do I verify readiness to start?
6. **When does the policy require delegation?** What signals indicate specialist involvement?
7. **When does the policy require strategic planning?** What distinguishes planning from execution?
8. **What breadcrumb discipline does the policy specify?** How do I document work progression?
9. **What friction documentation practices does the policy define?** When and how to document obstacles?
10. **What completion protocol does the policy require?** How do I mark work finished with proper traceability?
11. **When does the policy permit direct execution?** What conditions allow skipping planning?
12. **How does the policy define meaningful updates?** What events warrant documentation?
13. **What expansion check does the policy require for parent tasks?** What must happen if phases exist in roadmap but not as child tasks?
14. **What note-taking discipline does the policy require during task execution?** When should notes be added?
15. **What types of developments warrant task notes?** What distinguishes significant events from routine steps?
16. **How do task notes integrate with the task lifecycle?** What is their relationship to completion reports?

---

## Execution

🚨 **CRITICAL: Invoking this command IS execution authorization.**

The command name is `start`, not `review`. User running this command grants permission to BEGIN WORK immediately after policy reading completes.

Using answers from policy reading:

1. **Verify task exists**: Use task tools to confirm identity and metadata
2. **Check phase expansion**: Per Q13, verify parent tasks have required children
3. **Read referenced materials**: Follow mandatory reading discipline from policy
4. **Verify readiness**: Check blocking conditions per policy semantics
5. **Mark active**: Update task lifecycle per policy protocol
6. **Create required artifacts**: Follow policy requirements for planning vs execution
7. **BEGIN EXECUTION**: Do not ask for further permission - start the work

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths or subshells.

⚠️ **Sequential execution preferred** - concurrent tool calls can cause errors.

🔒 **Respect grant system** - Request permission proactively for protected operations.

---

**Meta-Pattern**: Policy as API - this command uses `macf_tools policy` CLI commands for reading policies. CLI tools handle framework path resolution, provide caching, and output line numbers for citations.
