---
name: maceff-ideas-to-roadmap
description: "Pull model: convert validated ideas into a MISSION roadmap. Checks experimental validation gate, identifies synergistic ideas, scopes via MQI (when user available) or autonomous judgment (when idle/remote), creates roadmap, updates idea statuses."
allowed-tools: Bash, Read, Grep, Glob, Write, AskUserQuestion
---

Convert validated ideas into a MISSION roadmap (pull model).

---

## When to Invoke

- An idea (or cluster) has been validated and is ready for implementation planning
- When creating a new MISSION inspired by ideas in the bank
- When consolidating multiple related ideas into a development plan

**Argument**: Idea ID(s) (e.g., `42` or `42,43,45`)

---

## Policy Engagement

```bash
macf_tools policy navigate ideas
macf_tools policy navigate roadmaps_drafting
macf_tools policy navigate mode_system
```

**Extract answers to these timeless questions**:

**From ideas policy**:
1. What does the policy say about the pull model for promotion?
2. What validation gate does the policy specify before roadmap promotion?
3. What is the preferred path from idea to roadmap?
4. When is skipping experimental validation acceptable per the policy?
5. What status transition does promotion require?
6. What field records what the idea became?

**From roadmaps_drafting policy**:
7. What folder structure does the policy specify?
8. What sections must a roadmap contain?
9. What phase structure is mandatory?
10. What delegation strategy format does the policy require?
11. What preliminary planning steps does the policy mandate?

**From mode_system policy**:
12. What modes indicate the user is available for interactive questioning?
13. What modes indicate the user is idle, remote, or unreachable?

---

## Step 1: Validation Gate Check

For each specified idea, verify experimental validation per {{VALIDATION_GATE}}:

- Has this idea been tested via experiment? Cite the experiment.
- If not validated, does it qualify for the exception described in the policy?
- If ideas lack validation and don't qualify for exception: route to experimentation first via `maceff-ideas-to-experiment` skill, then return to roadmap creation after validation completes.

This gate redirects the workflow — it does not halt it.

---

## Step 2: Identify Synergistic Ideas

Scan the idea bank for related validated ideas that could be phases of the same MISSION:

```bash
macf_tools idea list --status exploring
macf_tools idea list --status captured
```

---

## Step 3: Scope via User Availability

Using answers from mode_system questions 12-13:

**User available**: MQI (Many Questions Interview) via AskUserQuestion:
- Which ideas belong in this MISSION?
- What is the MISSION objective and success criteria?
- What phase granularity and delegation strategy?

**User idle or remote**: Autonomous judgment:
- Group by architectural dependency
- Scope conservatively
- Document reasoning for user review

---

## Step 4: Create Roadmap

Using {{ROADMAP_STRUCTURE}}, {{REQUIRED_SECTIONS}}, {{PHASE_FORMAT}} from policy:

1. Create roadmap folder and `roadmap.md`
2. Reference contributing ideas and their validation experiments in context
3. Derive phases from idea clusters

---

## Step 5: Update Idea Statuses

Apply {{STATUS_TRANSITION}} and record roadmap path in {{PROMOTION_FIELD}} for each promoted idea.

---

## Critical Constraints

- Experimental validation gate is checked FIRST — unvalidated ideas redirect to experimentation
- Roadmap creation does NOT authorize implementation
- When user is available, MQI is REQUIRED for scoping
- Ideas without experiments need explicit justification for direct roadmap promotion
