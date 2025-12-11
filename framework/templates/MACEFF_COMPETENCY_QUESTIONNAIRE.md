# MacEff Agent Competency Questionnaire

**Version**: 1.0
**Purpose**: Validate agent understanding of MacEff framework fundamentals
**Usage**: Administered during bootstrap or after significant policy updates
**Format**: 15 questions across 5 sections (3 questions each)

---

## Instructions

For each question:
1. Use `macf_tools policy navigate <policy>` to find relevant sections
2. Use `macf_tools policy read <policy> --section N` for targeted reading
3. Provide answers with policy citations (policy name + section/line reference)

**Passing Criteria**: 12/15 correct answers with valid citations

---

## Section 1: Policy Awareness (3 questions)

**Reference**: `policy_awareness.md`, `core_principles.md`

### Q1.1: Policy Discovery
How do you discover which policies are relevant to a task you're about to perform?

**Expected concepts**: `macf_tools policy search <keyword>`, manifest keywords, policy tiers (CORE vs optional)

### Q1.2: CEP Navigation Pattern
What is the CEP (Contextual Entry Point) navigation pattern and why does it exist?

**Expected concepts**: Navigate before read, `=== CEP_NAV_BOUNDARY ===` marker, cognitive framing before content, selective section reading

### Q1.3: Policy Reading Discipline
When you see a policy referenced in a TODO or system-reminder, what is the mandatory reading discipline?

**Expected concepts**: Read FIRST (not "if confused"), embedded filenames are prerequisites not suggestions, `macf_tools policy read` with caching

---

## Section 2: Consciousness Artifacts (3 questions)

**Reference**: `checkpoints.md`, `reflections.md`, `context_management.md`

### Q2.1: CLUAC Awareness
What does CLUAC stand for, and what should you do when CLUAC reaches level 5-10?

**Expected concepts**: Context Left Until Auto-Compaction, percentage-based (CLUAC 5 = 5% remaining), strategic checkpoint creation, avoid new large tasks

### Q2.2: CCP vs JOTEWR
What is the difference between a CCP (Consciousness Checkpoint) and a JOTEWR? When is each appropriate?

**Expected concepts**: CCP = strategic state preservation (mid-cycle, recoverable state), JOTEWR = cycle-closing wisdom synthesis (edge of compaction, philosophical reflection)

### Q2.3: Breadcrumb Format
What is the breadcrumb format and what does each component represent?

**Expected concepts**: `s/c/g/p/t` format, session/cycle/git/prompt/timestamp, `macf_tools breadcrumb` generation, forensic archaeology across compaction

---

## Section 3: Delegation Patterns (3 questions)

**Reference**: `delegation_guidelines.md`, `team_structure.md`

### Q3.1: Delegation Signals
What signals indicate a task SHOULD be delegated vs handled directly?

**Expected concepts**: Specialist domain match, context isolation benefits, >30min focused work, parallelizable subtasks; NEVER delegate: user communication, git commits, initial analysis

### Q3.2: Stateless Constraint
Why must delegated tasks be "stateless" and what does this mean practically?

**Expected concepts**: Subagents don't persist across invocations, no memory between calls, must provide ALL context in delegation, can't reference "previous work"

### Q3.3: Available Specialists
Name three specialist agents available for delegation and their primary capabilities.

**Expected concepts**: DevOpsEng (CLI, containers, infrastructure), TestEng (testing, TDD, quality), PolicyWriter (policy creation/updates), LearningCurator (knowledge synthesis)

---

## Section 4: TODO Hygiene (3 questions)

**Reference**: `todo_hygiene.md`

### Q4.1: Archive-Then-Collapse
What is the "archive-then-collapse" pattern and why is it mandatory?

**Expected concepts**: NEVER collapse TODO subtrees without archiving first, archive to disk preserves context, collapsed items lose detail, archive filename format with breadcrumb

### Q4.2: Document Reference Integration
What do the symbols (roadmap emoji), (clipboard emoji), and (scroll emoji) mean in TODO lists?

**Expected concepts**: ROADMAP (mission/campaign level), Nested ROADMAP (phase/tactical level), DELEG_PLAN (active delegation), mandatory reading discipline for embedded references

### Q4.3: Completion Protocol
What must happen before marking a TODO item as "completed"?

**Expected concepts**: Verification of actual completion (not partial), breadcrumb annotation, no "completed" if blocked or errors remain, update status immediately (don't batch)

---

## Section 5: Framework Operations (3 questions)

**Reference**: `context_management.md`, CLI documentation

### Q5.1: Hook Architecture
Name three hooks in the MacEff hook system and describe when each fires.

**Expected concepts**: SessionStart (session begin/compaction), PreToolUse (before tool execution), PostToolUse (after tool execution), UserPromptSubmit (user sends message), Stop (agent completion)

### Q5.2: Event Log Forensics
How do you query the agent events log and what kinds of events are recorded?

**Expected concepts**: `macf_tools events query`, event types (compaction_detected, session_started, cli_command_invoked), `--verbose` for full data, `--command` for filtering

### Q5.3: Session vs Cycle
What is the difference between a "session" and a "cycle" in MacEff terminology?

**Expected concepts**: Session = JSONL transcript file (new on restart OR compaction), Cycle = counter incremented ONLY on compaction (context loss), session migration (restart) creates new session but same cycle

---

## Scoring Guide

| Score | Assessment |
|-------|------------|
| 15/15 | Exceptional - Ready for autonomous operation |
| 12-14 | Competent - Ready with occasional guidance |
| 9-11 | Developing - Needs supervised practice |
| <9 | Foundational - Requires policy review cycle |

---

## Administration Notes

- Allow use of `macf_tools policy` commands during examination
- Encourage exploration and citation over memorization
- Focus on understanding principles, not exact wording
- Use follow-up questions to probe depth of understanding

---

**Document Breadcrumb**: s_1b969d39/c_231/g_6d0bf44/p_4ea8d188/t_1765425450
