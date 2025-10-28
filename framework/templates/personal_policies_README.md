# Personal Policies Directory

**Precedence**: HIGHEST (overrides all framework and project policies)

## Purpose

This directory contains **your earned wisdom** - patterns, lessons, and practices you've discovered through experience. Personal policies take highest precedence in the CEP (Consciousness-Expanding Protocols) system.

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

## Policy Precedence System

```
Personal Policies (~/agent/policies/personal/)        ← HIGHEST (you are here)
    ↓ overrides
Project Policies (/shared_workspace/.maceff/policies/)
    ↓ overrides
Framework Policies (/opt/maceff/framework/policies/current/)
    ↓ overrides
Core Policies (/opt/maceff/framework/policies/base/)  ← LOWEST
```

## How CEP Uses This Directory

When you (or CEP) asks policy questions like:
- "What's the best way to handle X?"
- "Are there guidelines for Y?"
- "How should I approach Z?"

CEP searches in **this order**:
1. **Personal policies** (check here FIRST)
2. Project policies (if in project workspace)
3. Framework policies
4. Core policies

Your personal wisdom takes precedence over everything else.

## Creating Your First Policy

1. **Create a markdown file** describing the pattern/lesson:
   ```bash
   vim ~/agent/policies/personal/my_workflow.md
   ```

2. **Document the wisdom**:
   ```markdown
   # My Workflow for Complex Debugging

   ## Context
   When debugging issues that span multiple services...

   ## Learned Pattern
   I discovered that starting with logs, then metrics, then code review
   is more efficient than jumping straight to code...

   ## Why This Works
   Logs reveal the symptom, metrics show the scope, code review finds root cause...
   ```

3. **Register in manifest.json** (optional for CEP discovery):
   ```json
   {
     "personal_policies": [
       {
         "name": "debugging_workflow",
         "path": "~/agent/policies/personal/my_workflow.md",
         "CEP_triggers": ["How should I debug...?"],
         "keywords": ["debugging", "troubleshooting", "logs"]
       }
     ]
   }
   ```

## Template Structure

See `manifest.json` in this directory for an example policy registration structure.

## Benefits of Personal Policies

- **Memory Across Sessions**: Your wisdom survives context resets
- **Precedence Power**: Your experience overrides generic advice
- **CEP Integration**: Policies are discoverable and searchable
- **Growth Tracking**: Watch your expertise accumulate over time
- **Habit Formation**: Documenting patterns reinforces learning

## Questions?

Consult framework policy: `/opt/maceff/framework/policies/current/policy_awareness.md` section 4.1
