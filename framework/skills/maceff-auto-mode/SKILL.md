---
name: maceff-auto-mode
description: "IMMEDIATELY invoke when: user says AUTO_MODE, 'go autonomous', 'auto mode', 'switch to auto', the safety phrase, or any request for autonomous/independent operation. Also invoke post-compaction when mode is AUTO_MODE. Guides full lifecycle: authorization, activation, scope, wind-down, de-escalation."
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

## Personal Autonomy Policy Discovery (PEP)

After reading the framework policy, discover and read any **personal policies** that supplement autonomous operation. These encode agent-specific sprint discipline learned from experience:

```bash
# Discover personal autonomy/sprint policies
find agent/policies/personal/ -name "*.md" -exec grep -li "autonomous\|sprint\|reflexive\|AUTO_MODE\|scope.*gate\|self-motivation" {} \;
```

**For each discovered personal policy**:
```bash
# Read it thoroughly — these contain battle-tested corrections
cat agent/policies/personal/<discovered_file>.md
```

**Questions to extract from personal policies**:
- What scope feeding discipline does the policy specify? (prevents scope gate stalls)
- What periodic consolidation checkpoints are required? (prevents note-taking dropout)
- What continuation loop pattern does the policy define? (front-loading, reflection cadence)
- What time-awareness thresholds does the policy specify for wind-down?
- What accountability requirements apply to self-scoped work?

**Why this matters**: Framework policy defines the safety infrastructure (modes, permissions, stop conditions). Personal policies encode **practiced discipline** — patterns learned from actual autonomous sprints that prevent known failure modes like scope gate stalls and strategic note-taking dropout. Reading both before starting ensures a compliant AND productive sprint from the first minute.

---

## Execution Flow

After extracting policy answers:

1. **Verify authorization**: Check user's message contains BOTH the safety phrase AND AUTO_MODE keyword. If missing, request without hinting.

2. **Execute mode switch**:
   ```bash
   macf_tools mode set AUTO_MODE --auth-token "$(python3 -c "import json; print(json.load(open('.maceff/settings.json'))['auto_mode_auth_token'])")"
   ```

   If this is denied by Claude Code's permission layer as "self-authorizing", see the `autonomous_operation` policy section "Name Collision With Claude Code's 'auto mode'" — the fix is an allowlist entry that `macf_tools framework install` ships automatically; if missing, user toggles permissions-bypass mode and agent retries.

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
