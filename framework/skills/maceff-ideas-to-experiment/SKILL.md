---
name: maceff-ideas-to-experiment
description: "Pull model: convert one or more related ideas into a formal experiment. Identifies synergistic ideas, scopes investigation via MQI (when user available) or autonomous judgment (when user idle/remote), creates experiment protocol, updates idea statuses to promoted."
allowed-tools: Bash, Read, Grep, Glob, Write, AskUserQuestion
---

Convert captured ideas into formal experiments (pull model). Supports single ideas or synergistic groups.

---

## When to Invoke

- An idea (or cluster of related ideas) is ready for structured investigation
- During EXPERIMENT work mode when selecting what to investigate
- When the Markov recommender suggests EXPERIMENT

**Argument**: Idea ID(s) (e.g., `42` or `42,43,45`)

---

## Policy Engagement

```bash
macf_tools policy navigate ideas
macf_tools policy navigate experiments
macf_tools policy navigate mode_system
```

**Extract answers to these timeless questions**:

**From ideas policy**:
1. What does the policy say about the pull model for promotion?
2. What status transition does promotion require?
3. What field records what the idea became?
4. What link types connect related ideas?

**From experiments policy**:
5. What directory structure does the policy specify for experiments?
6. What sections does a formal protocol require?
7. What preliminary steps does the policy mandate?
8. What does the policy say about scope and planning before execution?

**From mode_system policy**:
9. What modes indicate the user is available for interactive questioning?
10. What modes indicate the user is idle, remote, or unreachable for MQI?
11. What behavioral obligations apply when the user is unavailable?

---

## Step 1: Identify Synergistic Ideas

Read the specified idea(s), then scan the idea bank for related captured ideas:

```bash
macf_tools idea get <id>
macf_tools idea list --status captured
```

Look for ideas that share categories, wiki-links, or conceptual overlap with the specified idea(s). Prepare a candidate cluster.

---

## Step 2: Determine User Availability

Using answers from mode_system questions 9-11, determine the appropriate scoping approach:

**User available** (no USER_IDLE, not remote): Use MQI (Many Questions Interview) via AskUserQuestion to iterate on scope:
- Which of the identified ideas should be investigated together?
- What hypothesis ties these ideas into a coherent experiment?
- What is the expected effort level?
- Should any ideas be deferred or archived?

**User idle or remote** (USER_IDLE active, or only reachable via Telegram): Use autonomous judgment:
- Select the synergistic cluster based on category/link overlap
- Formulate hypothesis from idea descriptions
- Scope conservatively (prefer smaller, validatable experiments)
- Document reasoning in task notes for user review when available
- If uncertain about scope, prefer a smaller experiment that can be extended

---

## Step 3: Create Experiment

Using {{EXPERIMENT_STRUCTURE}} and {{PROTOCOL_SECTIONS}} extracted from policy:

1. Create experiment directory and protocol per policy requirements
2. Reference all contributing ideas in the protocol's inspiration section
3. Transform idea descriptions into testable hypotheses

---

## Step 4: Update Idea Statuses

For each idea pulled into the experiment:
- Apply {{STATUS_TRANSITION}} per policy
- Record experiment path in {{PROMOTION_FIELD}}

---

## Critical Constraints

- This skill creates the experiment — it does NOT execute it unless in AUTO_MODE with authorization
- When user is available, MQI scoping is REQUIRED — don't assume which ideas belong together
- When user is unavailable, autonomous scoping must be conservative and well-documented
- Synergistic grouping surfaces connections the user may not have noticed
