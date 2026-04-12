---
name: maceff-autonomous-sprint
description: "Invoke when the user authorizes an autonomous sprint (time-bounded AUTO_MODE work). Activates AUTO_MODE via the auto-mode skill, reads the autonomous sprint policy for sustainability guidance, and prepares the agent for extended self-directed work with the Markov recommender."
allowed-tools: Bash, Read, Grep, Glob
---

Launch and sustain an autonomous sprint — time-bounded self-directed work with Markov-guided mode transitions.

---

## When to Invoke

- User authorizes an autonomous sprint ("ride the tsunami", "work for N hours", "GO!")
- User says AUTO_MODE with a time allotment
- Post-compaction recovery when a sprint timer is still active

---

## Step 1: Activate AUTO_MODE

Invoke the auto-mode skill to handle authorization, permissions, and mode switch:

```
Skill(skill: "maceff-auto-mode")
```

Follow its protocol for authorization and activation.

---

## Step 2: Read Sprint Policy

```bash
macf_tools policy navigate autonomous_sprint
macf_tools policy read autonomous_sprint
```

Extract requirements by answering:
- What does the policy specify about gate point behavior?
- What interaction protocol does the policy define for recommendations?
- What scope discipline does the policy require?
- What timer discipline does the policy specify?
- What CL thresholds does the policy define?
- What anti-patterns does the policy name?
- What accountability does the policy require?

---

## Step 3: Read Mode System

```bash
macf_tools policy navigate mode_system
```

Extract requirements by answering:
- What work modes does the policy define?
- What transition model does the policy specify?
- What skill invocation protocol does the policy require at gate points?

---

## Step 4: Set Up Sprint Infrastructure

Using requirements extracted from policies:

1. **Scope tasks** with timer
2. **Start Transcript Monitor** if not running
3. **Front-load scope** per scope discipline requirements
4. **Document sprint start** per accountability requirements

---

## Step 5: Begin Work

Start the first scoped task. The Stop hook's gate points will invoke the Markov recommender when scope completes — follow the interaction protocol extracted from the sprint policy.

---

**This skill chains**: `maceff-auto-mode` (authorization) + `autonomous_sprint` policy (sustainability) + `mode_system` policy (recommender). All three are needed for a well-governed autonomous sprint.
