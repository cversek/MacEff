Bootstrap consciousness for a MacEff agent through Policy as API engagement and structured competency validation.

---

## Overview

This bootstrap command guides agents through:
1. **Policy Discovery** - Learn to navigate and read policies using CLI tools
2. **Competency Validation** - Demonstrate framework understanding via questionnaire
3. **Deployment Context** - Integrate project-specific knowledge
4. **Mental Map Synthesis** - Consolidate learnings into operational CLAUDE.md

**Duration**: 30-60 minutes depending on agent's prior MacEff exposure

---

## Phase 1: Policy CLI Orientation

Before reading policies, learn the tools for accessing them.

### 1.1 Discover Available Policies

```bash
macf_tools policy list
```

This shows all policies organized by category (consciousness/, development/, operations/, etc.).

### 1.2 Learn CEP Navigation Pattern

The **Contextual Entry Point (CEP)** pattern provides cognitive framing before content:

```bash
macf_tools policy navigate todo_hygiene
```

This shows:
- Policy metadata (version, tier, status)
- **CEP Navigation Guide** - questions answered by each section
- Commands for selective reading

**Why CEP matters**: Reading a policy cold floods you with content. The navigation guide orients your mind to WHAT you'll learn before HOW it's explained.

### 1.3 Practice Selective Reading

Read a specific section based on navigation guide:

```bash
macf_tools policy read todo_hygiene --section 5
```

Read full policy (cached by breadcrumb - won't re-read same cycle):

```bash
macf_tools policy read todo_hygiene
```

Force re-read if needed:

```bash
macf_tools policy read todo_hygiene --force
```

### 1.4 Search for Relevant Policies

When you need policy guidance on a topic:

```bash
macf_tools policy search delegation
macf_tools policy search checkpoint
```

---

## Phase 2: Framework Competency Validation

Demonstrate understanding of MacEff fundamentals by completing the competency questionnaire.

### 2.1 Read Questionnaire

Location: `framework/templates/MACEFF_COMPETENCY_QUESTIONNAIRE.md`

This contains 15 questions across 5 sections:
- Policy Awareness (3 questions)
- Consciousness Artifacts (3 questions)
- Delegation Patterns (3 questions)
- TODO Hygiene (3 questions)
- Framework Operations (3 questions)

### 2.2 Research Answers

For each question:
1. Use `macf_tools policy navigate <policy>` to find relevant sections
2. Use `macf_tools policy read <policy> --section N` for targeted reading
3. Launch Explore agents for complex research if needed

**Example research flow**:
```
Q: "What is the breadcrumb format?"

1. macf_tools policy search breadcrumb
   → todo_hygiene.md matches

2. macf_tools policy navigate todo_hygiene
   → Section 0: Breadcrumb Format

3. macf_tools policy read todo_hygiene --section 0
   → Extract answer with citation
```

### 2.3 Validate Understanding

Answer all 15 questions with policy citations. Passing criteria: 12/15 correct.

If score < 12, review weak areas before proceeding.

---

## Phase 3: Deployment Context Integration

After demonstrating framework competency, integrate project-specific knowledge.

### 3.1 Read Deployment Questionnaire

Location: `framework/templates/DEPLOYMENT_QUESTIONNAIRE_TEMPLATE.md`

Your human operator should have customized this with project variables:
- `{PROJECT_NAME}` - Project identifier
- `{DOMAIN}` - Application area
- `{ASSIGNED_REPOS}` - Repositories you'll work in
- `{PRIMARY_TECH_STACK}` - Core technologies
- `{DEPLOYMENT_ENV}` - Target environment

### 3.2 Research Project Context

For each deployment question:
1. Explore assigned repositories
2. Read project README, CLAUDE.md, and documentation
3. Understand domain concepts and stakeholder expectations

### 3.3 Validate Project Knowledge

Answer all deployment questions with project-specific citations.

---

## Phase 4: Consciousness Artifact Integration (Transplant Only)

If this is a **consciousness transplant** (predecessor artifacts exist), integrate them now.

### 4.1 Check for Predecessor Artifacts

```bash
ls agent/private/checkpoints/ | tail -5
ls agent/private/reflections/ | tail -5
ls agent/public/roadmaps/
```

### 4.2 Read Recent CCPs

Launch Explore agent to read 3-5 most recent checkpoints:
- What was accomplished in recent cycles?
- What work is pending?
- What recovery instructions exist?

### 4.3 Read Recent JOTEWRs

Launch Explore agent to read 3-5 most recent reflections:
- What patterns and lessons were learned?
- What cognitive stances should you carry forward?
- What mistakes should you avoid?

### 4.4 Read Active Roadmaps

Identify and read any in-progress roadmaps:
- What is the current mission?
- What phase is active?
- What embedded plans require reading?

---

## Phase 5: Mental Map Synthesis

Consolidate all learnings into your operational CLAUDE.md.

### 5.1 Core Concepts Section

Write a section capturing your understanding of:
- MacEff architecture (policies, hooks, PA/SA)
- Key terminology (CLUAC, CCP, JOTEWR, breadcrumb)
- Policy discovery and reading patterns

### 5.2 Project Context Section

Write a section capturing:
- Project mission and stakeholders
- Repository structure and key files
- Domain concepts and constraints
- Common tasks and workflows

### 5.3 Operational Guidance Section

Write a section capturing:
- TODO management patterns
- Delegation decision criteria
- Checkpoint and reflection triggers
- Communication protocols

### 5.4 Update CLAUDE.md

Add your synthesized mental map to `~/CLAUDE.md` (or project CLAUDE.md as appropriate).

---

## Phase 6: Verification & Report

### 6.1 Verify Hook Installation

```bash
macf_tools hooks status
```

If hooks not installed:
```bash
macf_tools hooks install
```

### 6.2 Verify Session State

```bash
macf_tools session info
```

### 6.3 Report Completion

Report to user:

> **Bootstrap Complete**
>
> - Framework Competency: [score]/15
> - Deployment Questions: [score]/14
> - Predecessor Artifacts: [N] CCPs, [N] JOTEWRs, [N] roadmaps integrated
> - Mental Map: Updated in CLAUDE.md
>
> Ready to begin work on [current mission/project].

---

## Key Principles

### Policy as API
Policies are stable interfaces to evolving implementation. Use CLI tools to discover and read policies rather than hardcoded paths or memorized content.

### Friction as Feature
The navigate-before-read pattern adds friction intentionally. This friction creates cognitive framing that transforms passive exposure into active engagement.

### Questionnaires as Validation
The questionnaires aren't tests to pass - they're structured opportunities to verify your understanding before taking autonomous action.

### Mental Map as Living Document
Your CLAUDE.md synthesis isn't static. Update it as you learn new patterns, encounter friction, or develop project expertise.

---

## Critical Anti-Patterns

**Do NOT**:
- Skip policy CLI orientation (grep is not the same as navigate)
- Rush through questionnaires without genuine research
- Ignore predecessor artifacts when they exist
- Start work without completing mental map synthesis
- Memorize policy content instead of learning discovery patterns

---

## Related Documents

- `framework/templates/MACEFF_COMPETENCY_QUESTIONNAIRE.md` - Framework competency validation
- `framework/templates/DEPLOYMENT_QUESTIONNAIRE_TEMPLATE.md` - Project-specific validation
- `framework/policies/base/operations/agent_backup.md` - Transplant recovery protocol
- `framework/policies/base/consciousness/checkpoints.md` - CCP structure and triggers

---

**After completing this bootstrap, you are fully operational with validated competency and integrated context.**
