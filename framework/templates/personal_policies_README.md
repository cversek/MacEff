# Personal Policies Directory

Read with `macf_tools policy read personal:<name>`. No setup needed.

## Purpose

This directory holds **your earned wisdom**: patterns, lessons and rules you've discovered through experience, and that you must still hold after a compaction.

**A personal policy augments the framework. It never replaces it.** A name the framework has always reads the framework's copy, and `personal:<name>` reads yours. On how you work, your policy guides you. It never lifts a boundary.

## What Belongs Here

### ✅ Document These

- **Discovered Patterns**: "I learned that approach X works better than Y for task Z"
- **Project Conventions**: Project-specific standards you want to remember
- **Proven Practices**: Techniques that consistently work well for you
- **Decision Records**: Why you chose approach A over B (for future reference)
- **Workflow Optimizations**: Personal efficiency patterns you've developed

### ❌ Don't Document These

- Framework-level policies (those belong in `/opt/maceff/framework/policies/`)
- Temporary notes or work-in-progress thoughts
- Project-specific data (use project workspace instead)
- Generic best practices (use framework policies)

## Creating Your First Policy

1. **Create a markdown file** describing the pattern/lesson:
   ```bash
   vim ~/agent/policies/personal/my_workflow.md
   ```

2. **Use the framework's format**, so `navigate` stops at the boundary: see `macf_tools policy read policy_writing`.

3. **Say when it applies.** A policy nobody reads binds nothing. To surface one when a task of some type starts, declare it in `manifest.json`:
   ```json
   {
     "personal_policies": [
       {"name": "debugging_workflow", "task_types": ["BUG"]}
     ]
   }
   ```
   A declaration naming a policy that isn't here is reported.

## Benefits of Personal Policies

- **Memory Across Sessions**: Your wisdom survives context resets
- **Discoverable**: `policy list`, `search` and `recommend` all reach them
- **Growth Tracking**: Watch your expertise accumulate over time
- **Habit Formation**: Documenting patterns reinforces learning

## Questions?

Consult framework policy: `macf_tools policy navigate policy_awareness`
