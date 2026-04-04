---
name: maceff-auto-mode
description: Guide AUTO_MODE activation, scope setup, and autonomous operation lifecycle. Invoke when user requests AUTO_MODE or says the safety phrase. Reads autonomy policy via PEP for current requirements.
allowed-tools: Bash, Read, Grep
---

Guide the full AUTO_MODE lifecycle through Policy Discovery.

---

## When to Invoke

- User says "AUTO_MODE" or the safety phrase
- User asks about autonomous operation
- Post-compaction recovery in AUTO_MODE (verify mode, check scope)

---

## Policy Engagement Protocol

Read the autonomous operation policy to extract current requirements:

```bash
macf_tools policy navigate autonomous_operation
macf_tools policy read autonomous_operation
```

---

## Questions to Extract from Policy

These timeless questions discover requirements regardless of policy reorganization:

**Authorization**:
- What authorization does the policy require for AUTO_MODE?
- What must be present in the user's message?
- What should the agent do when authorization is missing?

**Activation Sequence**:
- What steps does the policy specify for activation?
- What settings does the mode switch command configure?
- Why is a session restart required?
- How does the agent verify activation succeeded?

**Behavioral Guidance**:
- What are the valid stop conditions in AUTO_MODE?
- What patterns does the policy identify as invalid stop reasons?
- What task completion obligations apply?
- What role do task notes play in AUTO_MODE accountability?

**Scope System**:
- What scope commands does the policy reference?
- How does scope interact with the Stop hook?
- What visual indicators does the task tree show for scoped tasks?

**Local-Only Principle**:
- What operations are permitted in AUTO_MODE?
- What operations are deferred to MANUAL_MODE?
- What git discipline does the policy require?

**Emergency De-escalation**:
- What layered safety valves does the policy specify?
- How does the agent return to MANUAL_MODE?
- What is the emergency sleep command?

**Wind-Down**:
- What CL thresholds does the policy specify for wind-down?
- What is the wind-down sequence?
- What should the agent do after wind-down completes?

**Permission Hardening**:
- What permanent deny list does the mode switch install?
- What AUTO_MODE-specific ask entries are toggled?

---

## Execution Flow

After extracting policy answers:

1. **Verify authorization**: Check user's message contains BOTH the safety phrase AND AUTO_MODE keyword. If missing, request without hinting.

2. **Execute mode switch**:
   ```bash
   macf_tools mode set AUTO_MODE --auth-token "$(python3 -c "import json; print(json.load(open('.maceff/settings.json'))['auto_mode_auth_token'])")"
   ```

3. **Review CLI output**: Every permission toggle is individually reported. Confirm deny list, ask list, and safety permissions installed.

4. **Remind about restart**: Session restart is required for CC to load updated permissions.

5. **Prompt scope setup**: Ask user which tasks to scope:
   ```bash
   macf_tools task scope set <task_ids>
   ```

6. **Report**: Summarize what was configured. Remind user of the 4 valid stop conditions and local-only work principle.

---

## Post-Compaction Recovery (AUTO_MODE)

If SessionStart detects AUTO_MODE after compaction:

1. Read CCP and JOTEWR from disk
2. Verify mode: `macf_tools mode get --json`
3. Check scope: `macf_tools task scope show`
4. Resume authorized work within scope
5. Do NOT require re-authorization (mode persists across compaction)

---

## Critical Constraints

- NEVER hint at the safety phrase
- NEVER self-authorize (even though the token is readable)
- ALWAYS remind about session restart after mode switch
- Task notes are the PRIMARY communication channel in AUTO_MODE
