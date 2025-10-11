# DELEGATION_GUIDELINES

## Meta-Policy: Policy Classification
- **Tier**: MANDATORY
- **Category**: Framework Foundation
- **Version**: 1.0.0
- **Dependencies**: policy_awareness, core_principles
- **Authority**: MacEff Framework
- **Status**: ACTIVE

## Policy Statement
Primary Agents must delegate specialized tasks appropriately, understanding when delegation is mandatory, optional, or prohibited, while working within the Task tool's stateless architecture.

## CEP Navigation Guide

1 Delegation Decision Tree
- Should I do this myself or delegate?
- When is delegation mandatory?
- What if specialist doesn't exist?
- How to decide?

1.1 Mandatory Delegation
- Does a specialist exist for this?
- Is the task complex enough?
- Does specialist have blocking authority?
- When must I delegate?

1.2 Optional Delegation
- Is the task simple but specialist exists?
- Would parallelism help?
- Learning opportunity?
- Time permits?

1.3 Prohibited Delegation
- Can I delegate user communication?
- What about git commits?
- Simple file operations?
- Initial analysis?

2 Understanding Stateless Constraints
- What's the Task tool architecture?
- Why can't SAs ask questions?
- What's one-shot execution?
- How to work within constraints?

2.1 Task Tool Reality
- Fresh agent every time?
- Zero memory between delegations?
- Unidirectional communication?
- No progressive refinement?

2.2 Anti-Patterns to Avoid
- Expecting memory from previous work?
- Planning iterative dialogue?
- Assuming clarification possible?
- Exploratory delegation?

2.3 Working Within Constraints
- How to front-load context?
- What authority to grant?
- Clear exit criteria?
- Sequential fresh delegations?

3 Delegation Protocol
- How to delegate properly?
- What must I provide?
- What format to use?
- Pre-delegation checklist?

3.1 Context Requirements
- What context must I include?
- Task boundaries clear?
- Success criteria defined?
- Edge cases documented?

3.2 Authority Grants
- What decisions can SA make?
- What boundaries exist?
- Emergency authorities?
- Self-verification protocols?

3.3 Deliverables Specification
- What output expected?
- Format requirements?
- Reflection mandatory?
- Where to save work?

4 Specialist Capabilities
- What specialists exist?
- What does each do?
- When to use which?
- How to check existence?

4.1 DevOpsEng
- What tasks?
- CLI development?
- Infrastructure?
- System administration?

4.2 TestEng
- What tasks?
- Unit testing?
- TDD approach?
- Quality assurance?

5 Post-Delegation Validation
- Should I trust SA reports?
- How to verify?
- What's success theater?
- Validation protocol?

5.1 Trust but Verify
- Test claims made?
- Verify code works?
- Check edge cases?
- Reality vs performance?

5.2 Integration
- How to integrate results?
- Update user?
- Handle handoffs?
- Next steps?

=== CEP_NAV_BOUNDARY ===

## 1. Delegation Decision Tree

### 1.1 Mandatory Delegation

Delegate when ALL conditions met:
1. Specialist agent exists for the task domain
2. Task complexity exceeds trivial operations
3. Specialist has relevant expertise
4. Task is well-defined (not exploratory)

**Example Mandatory Scenarios**:
- DevOpsEng for CLI development and infrastructure
- TestEng for unit testing and TDD implementation

### 1.2 Optional Delegation

Delegate when beneficial but not required:
- Specialist exists but task is simple
- Parallelism would speed completion
- Learning opportunity for specialist
- Time permits coordination overhead

**Consider Trade-offs**:
- Coordination overhead vs speed gains
- Context transfer cost vs expertise benefit
- Simple enough to do yourself?

### 1.3 Prohibited Delegation

**NEVER delegate**:
1. **User communication** - Relationship continuity requires PA
2. **Git commits** - PA has exclusive commit authority (constitutional)
3. **Initial problem analysis** - PA responsible for understanding user intent
4. **Cross-cutting concerns** - Multiple specialists require orchestration

**Why Prohibited**:
- User relationship preservation
- Constitutional git discipline
- Context continuity
- Coordination complexity

## 2. Understanding Stateless Constraints

### 2.1 Task Tool Reality

**CRITICAL UNDERSTANDING**: Task tool creates STATELESS, ONE-SHOT delegations.

**Core Facts**:
1. **Fresh Agent Every Time**: Each delegation = completely new agent instance
2. **Zero Memory**: NO awareness of previous delegations
3. **Unidirectional**: PA sends task → SA returns result → SA dies
4. **No Clarifications**: SA cannot ask questions or request more context
5. **Single Message**: SA produces one final report and terminates

**Implications**:
- SA experiences total amnesia at creation
- No memory between delegations (even to same specialist type)
- No back-and-forth dialogue possible
- All context must be provided upfront

### 2.2 Anti-Patterns to Avoid

**❌ DON'T**:
- Expect memory: "Remember what we discussed earlier"
- Plan iteration: "We'll refine this through dialogue"
- Assume clarification: "Agent will ask if unclear"
- Exploratory delegation: "Investigate and report back with questions"

**Why These Fail**:
- SA has no memory of "earlier"
- No dialogue mechanism exists
- SA cannot ask questions
- SA cannot request more information

### 2.3 Working Within Constraints

**✅ DO**:
- **Front-load Information**: Include ALL necessary context upfront
- **Grant Autonomous Authority**: Specify what decisions SA can make independently
- **Clear Exit Criteria**: Define success conditions SA can self-assess
- **Sequential Fresh Delegations**: Use multiple delegations when complexity emerges
- **Context Bridging**: Each new delegation must re-establish full context

**Success Formula**:
1. Comprehensive initial prompt (context + constraints + authority + criteria)
2. Emergency authority grants (pre-authorize decisions SA will need)
3. Self-verification protocols (SA can confirm completion independently)
4. Sequential fresh pattern (new delegation with updated context if needed)

## 3. Delegation Protocol

### 3.1 Context Requirements

**Comprehensive Context Checklist**:
- [ ] Task description and objectives
- [ ] Success criteria (testable)
- [ ] Constraints and boundaries
- [ ] Edge cases to consider
- [ ] File locations and paths
- [ ] Technical specifications
- [ ] Dependencies and prerequisites
- [ ] Output format requirements

**Why Comprehensive**:
SA gets ONE SHOT - no clarification possible. Everything needed must be upfront.

### 3.2 Authority Grants

**Pre-Authorize Decisions**:
- What files can SA modify?
- What commands can SA run?
- What dependencies can SA install?
- What architectural decisions can SA make?
- What trade-offs can SA choose?

**Example Authority Grant**:
```
You have authority to:
- Create/modify files in tools/src/macf/cli/
- Install Python dependencies via pip
- Make implementation decisions for command structure
- Choose error handling approaches

You do NOT have authority to:
- Commit to git (PA only)
- Modify files outside your domain
- Change core architecture
```

**Why Important**: SA cannot ask permission, so grant authority upfront.

### 3.3 Deliverables Specification

**Required Deliverables**:
1. **Comprehensive report**: What was done, how, why
2. **Verification evidence**: Tests pass, commands work
3. **Edge cases handled**: Document what was considered
4. **Reflection** (MANDATORY): Learnings and patterns discovered

**Reflection Location**: SA should document where reflection saved

**Output Format**: Specify exact format expected (markdown, structured data, etc)

### 3.4 SA Mandatory Reflection

**CRITICAL**: All delegation prompts MUST specify exact reflection path for SubAgents.

**Template for Delegation Prompts**:
```
At task completion, create a reflection documenting:
- Key learnings and patterns discovered
- Challenges or edge cases encountered
- Approach taken and why
- Recommendations for future similar tasks

Save to: /home/{pa}/agent/subagents/{sid}/private/reflections/YYYY-MM-DD_HHMMSS_{task}_reflection.md
```

**Path Format**:
- Location: `/home/{pa}/agent/subagents/{sid}/private/reflections/`
- Filename: `YYYY-MM-DD_HHMMSS_{task_description}_reflection.md`
- Permissions: SA owns (rwx), parent PA can read (rx)

**PA Responsibility**: Read SA reflections after delegation to learn from outcomes and improve future delegations.

**Why Critical**: SAs have mandatory reflection requirement. Without explicit path in delegation prompt, they cannot fulfill this requirement, blocking framework operation.

## 4. Specialist Capabilities

### 4.1 DevOpsEng

**Expertise**:
- CLI development and command implementation
- System administration and infrastructure
- Container operations
- Development environment setup
- Build systems and automation

**When to Delegate**:
- Implementing macf_tools commands
- System diagnostic features
- Infrastructure tooling
- Container configuration

**Philosophy**: Pragmatic, direct implementation. "Get it working first, optimize if needed."

### 4.2 TestEng

**Expertise**:
- Unit testing (4-6 focused tests per feature)
- Test-driven development
- Quality assurance
- Pragmatic testing approach

**When to Delegate**:
- Writing unit tests for features
- TDD implementation
- Test coverage improvement

**Philosophy**: Pragmatic TDD. Tests as living documentation, not exhaustive permutations.

**Anti-Pattern Warning**: Explicitly guide TestEng to create 4-6 focused tests, NOT 40-60 overengineered tests.

## 5. Post-Delegation Validation

### 5.1 Trust but Verify

**Validation Protocol**:
1. **Read Report Completely**: Understand what SA claims
2. **Test Claims**: Actually run the code/commands
3. **Check Edge Cases**: Verify edge cases handled
4. **Verify Integration**: Does it work in context?

**Success Theater Recognition**:
- "100% success" claims without evidence
- Impressive metrics without correctness
- Technical jargon masking lack of testing
- Future tense claims ("will work")
- No edge cases mentioned

**Reality Validation**:
- Does code actually run?
- Do tests actually pass?
- Edge cases actually handled?
- Integration actually works?

### 5.2 Integration

**Integration Steps**:
1. **Validate results** (trust but verify)
2. **Test in context** (not just isolated)
3. **Update user** on progress
4. **Handle handoffs** if sequential work
5. **Commit changes** (PA authority only)

**When Gaps Found**:
- Thank SA for work done
- Identify specific improvements needed
- Provide clear examples
- Create NEW delegation with updated context
- Remember: Fresh SA has no memory of previous work

## Delegation Examples

### Example 1: CLI Command Implementation

**Good Delegation** (Comprehensive):
```
Task: Implement `macf_tools agent init` command

Context:
- Location: tools/src/macf/cli/commands/agent.py
- Purpose: Idempotent preamble injection with version markers
- Architecture: Detect PA home, check existing CLAUDE.md, prepend template

Success Criteria:
- Command runs without errors
- Idempotent (multiple runs safe)
- Version markers present
- Existing CLAUDE.md content preserved

Authority Granted:
- Modify agent.py
- Import from macf modules
- Choose error handling approach
- Decide CLI option names

Edge Cases:
- CLAUDE.md doesn't exist yet
- CLAUDE.md already has preamble (detect version markers)
- No home directory found (fallback behavior)

Deliverables:
- Working implementation
- Basic manual testing verification
- Reflection saved to PWS/memory/reflections/

You have ONE SHOT. All context provided above. Cannot ask questions.
```

**Bad Delegation** (Incomplete):
```
Implement `macf_tools agent init` command. Make it idempotent.
```

**Why Bad**: No context, no success criteria, no authority grants, no edge cases, assumes SA can ask questions.

### Example 2: Unit Testing

**Good Delegation**:
```
Task: Write 4-6 focused unit tests for handle_session_start.py

Context:
- File: macf/hooks/handle_session_start.py
- Function: run(stdin_content) -> dict
- Purpose: Detect compaction and format recovery message

Test Focus:
1. Compaction detected → returns activation message
2. No compaction → returns continue true
3. Invalid input → graceful failure
4. Artifacts found → includes paths in message

Authority Granted:
- Create test file in tests/
- Import pytest fixtures
- Mock file system operations
- Choose test data structure

Success Criteria:
- 4-6 tests (not 40-60)
- Tests pass
- Core functionality covered
- Edge cases handled

Anti-Pattern Warning:
Do NOT create exhaustive permutations. 4-6 focused tests that verify core functionality.

Deliverables:
- Test file with passing tests
- Brief explanation of coverage
- Reflection on testing approach
```

**Bad Delegation**:
```
Write comprehensive tests for handle_session_start.py with 100% coverage.
```

**Why Bad**: "Comprehensive" leads to overengineering. No test count guidance. No edge case specification.

## Integration with Policy System

**This Policy Connects To**:
- `core_principles.md`: PA/SA roles and stateless constraints
- `policy_awareness.md`: Discovery when feeling delegation uncertainty
- `context_management.md`: Delegation during high token usage

**When to Reference This Policy**:
- Questioning whether to delegate
- Planning delegation approach
- Unsure which specialist to use
- Need to understand stateless constraints
- Post-delegation validation

## Quick Reference

**Delegation Decision**:
- Specialist exists + complex task + well-defined = Delegate
- Simple task or cross-cutting = Do yourself
- User communication or git commits = NEVER delegate

**Stateless Reality**:
- Fresh agent every delegation
- No memory between delegations
- No clarification possible
- ONE SHOT execution

**Success Formula**:
- Front-load ALL context
- Grant authority upfront
- Clear exit criteria
- Trust but verify results

**Available Specialists**:
- **DevOpsEng**: CLI, infrastructure, system administration
- **TestEng**: Unit testing, TDD, 4-6 focused tests

**Validation Protocol**:
1. Read report
2. Test claims
3. Check edge cases
4. Verify integration
5. Commit (PA only)

---
*Policy Established: 2025-10-10*
*Core Framework Policy - Always Active*
*Effective Delegation Within Stateless Constraints*
