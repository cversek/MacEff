# Testing Standards

**Type**: Development Standards (CORE tier)
**Scope**: All agents (PA and SA) - language agnostic
**Status**: ACTIVE
**Updated**: 2025-11-23

---

## Purpose

Testing standards establish pragmatic test-driven development principles that balance quality assurance with sustainable development velocity. These standards codify 176+ cycles of testing wisdom: focused tests beat exhaustive coverage, foundation layers demand rigor, and progressive verbosity protocols conserve tokens while maintaining quality confidence.

**Core Insight**: Tests aren't bureaucracy—they're **living documentation** that proves code works, guides implementation, and prevents regressions. Quality emerges from focus (4-6 strategic tests) not exhaustion (40-60 permutations).

---

## CEP Navigation Guide

**1 Testing Philosophy**
- What makes a good test?
- How many tests per feature?
- Why do 4-6 focused tests beat 40-60 variations?
- What is quality through focus?
- How do tests serve as living documentation?
- What is test reality vs test possibilities?

**1.1 The 4-6 Test Principle**
- Where did this principle originate?
- What problem does it solve?
- How do I determine which 4-6 tests to write?
- What is the anti-pattern this prevents?

**1.2 Living Documentation Pattern**
- How do tests document behavior?
- What makes tests good documentation?
- How do tests guide implementation?
- How do tests serve as contracts?

**1.3 Test Reality Not Possibilities**
- What does this mean?
- How do I identify what to test?
- What is the exhaustive permutation trap?
- How do I avoid over-testing?

**2 Pragmatic TDD Principles**
- What is test-driven development?
- What is the TDD cycle?
- How do I practice pragmatic TDD?
- When is TDD required vs optional?

**2.1 Red-Green-Ship Cycle**
- What are the three phases?
- What happens in Red phase?
- What happens in Green phase?
- Why skip endless refactoring?
- When is code good enough to ship?

**2.2 Test Counting Discipline**
- What counts as a test?
- Do loop iterations count as tests?
- Do assertions count as tests?
- How do I count tests correctly?

**2.3 Anti-Pattern Awareness**
- What testing anti-patterns exist?
- How do I avoid overengineering?
- What is test suite bloat?
- How do I recognize bad testing practices?

**3 Test Running Discipline**
- When should I run comprehensive test suites?
- What is progressive verbosity?
- How do I minimize token usage?
- What are the verbosity levels?
- When to use summary vs detailed output?

**3.1 When to Run Comprehensive Suites**
- After major phase implementation?
- Before significant commits?
- After specialist delegation handoffs?
- When integrating multiple components?

**3.2 Progressive Verbosity Protocol**
- What are the three verbosity levels?
- What is Level 0 (Summary)?
- What is Level 1 (Failures)?
- What is Level 2 (Diagnostic)?
- How do I choose appropriate level?

**3.3 Token-Efficient Testing**
- Why does verbosity matter?
- How many tokens does full output consume?
- How many tokens does summary mode use?
- What is the efficiency gain?

**3.4 Responsibility Model**
- Who runs comprehensive tests?
- What does PA (Primary Agent) test?
- What does DevOpsEng test?
- What does TestEng verify?

**3.5 Integration with Roadmaps**
- How do tests integrate with phase completion?
- What goes in phase completion checklist?
- How do I document test results?
- Where do test results get recorded?

**4 Foundation vs Integration Rigor**
- What qualifies as foundation code?
- What qualifies as integration code?
- When is strict TDD required?
- When is pragmatic TDD appropriate?
- How does rigor scale with architectural position?

**4.1 Foundation Testing (Strict TDD)**
- What is foundation code?
- Why strict TDD for foundations?
- What is the two-expert workflow?
- How do foundation bugs propagate?

**4.2 Integration Testing (Pragmatic TDD)**
- What is integration code?
- Why pragmatic approach for integration?
- Can I combine tests and implementation?
- What is the cost reduction from validated foundations?

**4.3 Rigor Scaling Principle**
- How does architectural position determine rigor?
- What is the scaling pattern?
- How do I assess my layer?

**5 Anti-Patterns**
- What is test suite bloat?
- What is overengineering in tests?
- What is the exhaustive permutation trap?
- How do I avoid these patterns?
- What are real-world examples?

**5.1 Test Suite Bloat**
- What is test suite bloat?
- What are symptoms?
- What is a real example?
- How do I fix bloated test suites?

**5.2 Loop Iterations Counted as Tests**
- Why is this wrong?
- What counts as a test function?
- How do I count correctly?
- What is the delegation anti-pattern?

**5.3 Exhaustive Permutations**
- What is exhaustive permutation testing?
- Why is it wasteful?
- What should I test instead?
- How do I identify likely failures?

**6 Integration with Other Policies**
- How does testing integrate with workspace discipline?
- How does testing integrate with delegation?
- How does testing integrate with roadmaps?
- Where are language-specific implementations?

**6.1 Workspace Integration**
- Where do test files go?
- What is the test file organization?
- How do tests relate to source code?

**6.2 Delegation Integration**
- When do I delegate testing?
- What does TestEng specialist do?
- How do I specify testing delegation?
- What anti-patterns must I warn about?

**6.3 Roadmap Integration**
- How do tests appear in roadmaps?
- What are phase completion criteria?
- How do I document test passage?
- When do tests gate phase completion?

**6.4 Language-Specific Implementations**
- Where do I find Python testing guide?
- Where do I find other language guides?
- How do language guides relate to this policy?

=== CEP_NAV_BOUNDARY ===

---

## 1 Testing Philosophy

### 1.1 The 4-6 Test Principle

**The Fundamental Lesson** (learned through painful experience):

Simple solutions win. Working code beats "perfect" architecture every time. This applies to **testing strategy** as much as implementation.

**The Hard Truth**:
- **Before**: Attempted "comprehensive" 10,000+ line test specifications
- **Reality**: 114 overengineered tests for simple pattern matching
- **After Reform**: 5 focused tests in 96 lines achieve same confidence

**The Principle**: **4-6 focused tests per feature** provide sufficient confidence without exhaustive permutation waste.

**Why This Number**:
- Covers core functionality (happy path)
- Tests likely failure modes (edge cases)
- Validates integration points (interfaces)
- Prevents common regressions (real-world bugs)
- Avoids exhaustive permutation trap

**How to Choose Your 4-6 Tests**:

1. **Core functionality** (1-2 tests):
   - Does primary use case work?
   - Does main flow execute correctly?

2. **Likely failures** (2-3 tests):
   - What edge cases exist in reality?
   - What have users reported breaking?
   - What assumptions could be violated?

3. **Integration points** (1-2 tests):
   - Do interfaces work as expected?
   - Do components integrate correctly?

**Example - Testing File Parser**:

```pseudocode
# GOOD (6 focused tests):
test_parse_valid_file()           # Happy path
test_parse_empty_file()           # Edge case
test_parse_malformed_data()       # Error handling
test_parse_missing_required_field() # Validation
test_parse_unicode_content()      # Real-world data
test_parse_large_file()           # Performance boundary

# BAD (40 tests):
# test_parse_file_size_1kb()
# test_parse_file_size_2kb()
# test_parse_file_size_3kb()
# ... (37 more size variations)
# This is exhaustive permutation trap!
```

### 1.2 Living Documentation Pattern

**Tests as Documentation**: Well-written tests document system behavior better than prose.

**What Tests Document**:
1. **Expected behavior**: What should happen when function called
2. **Valid inputs**: What data is acceptable
3. **Error conditions**: How system handles failures
4. **Integration contracts**: How components interact

**Good Test Names Are Documentation**:

```pseudocode
# GOOD (self-documenting):
test_session_detection_returns_true_when_session_id_changes()
test_compaction_detection_returns_false_when_no_compact_boundary()
test_recovery_message_includes_artifact_paths_when_found()

# BAD (requires reading implementation):
test_case_1()
test_basic_functionality()
test_edge_case()
```

**Benefits**:
- New developers read tests to understand system
- Tests show concrete usage examples
- Test failures explain what broke and why
- Tests survive documentation drift (they must pass!)

### 1.3 Test Reality Not Possibilities

**Core Principle**: Test what **actually matters**, skip exhaustive permutations of theoretical cases.

**Test Reality**:
- ✅ Real-world use cases users encounter
- ✅ Bugs that have actually occurred
- ✅ Edge cases with production evidence
- ✅ Integration points that fail in practice

**Don't Test Possibilities**:
- ❌ Every theoretical input combination
- ❌ Permutations that never occur naturally
- ❌ Edge cases with zero production precedent
- ❌ Mathematical completeness for its own sake

**Example**:

```pseudocode
# Function: format_breadcrumb(session, cycle, git, prompt, timestamp)

# GOOD (tests reality - 5 tests):
test_format_with_all_valid_components()
test_format_with_missing_optional_components()
test_format_with_invalid_session_format()
test_format_preserves_component_order()
test_format_handles_unicode_in_git_hash()

# BAD (tests possibilities - 50+ tests):
# test_session_length_1()
# test_session_length_2()
# ... (test every length 1-100)
# test_cycle_value_0()
# test_cycle_value_1()
# ... (test every cycle 0-1000)
# This tests mathematical space, not actual usage!
```

**How to Identify Reality**:
- Review actual usage patterns
- Check error logs for real failures
- Interview users about edge cases encountered
- Focus on integration boundaries (most failures)

---

## 2 Pragmatic TDD Principles

### 2.1 Red-Green-Ship Cycle

**Test-Driven Development (TDD)**: Write tests **before** implementation.

**The Three Phases**:

**RED Phase** - Write failing test:
- Define expected behavior through test
- Test must fail (proves test actually validates)
- Clarifies requirements before coding

**GREEN Phase** - Minimal implementation:
- Write simplest code that passes test
- Don't optimize prematurely
- Don't add features not tested
- Focus: Make it work

**SHIP Phase** - Deploy working code:
- Code passes tests → ship it
- Skip endless refactoring cycles
- Optimize only if performance problems emerge
- Pragmatism over perfectionism

**Anti-Pattern**: Red → Green → Refactor → Refactor → Refactor → ...
- Endless refactoring delays delivery
- Theoretical improvements without evidence
- Premature optimization waste

**Pragmatic Pattern**: Red → Green → **Ship**
- Tests pass → code works → deliver value
- Refactor only when pain points emerge
- Real-world usage guides optimization

**Example Workflow**:

```pseudocode
# 1. RED - Write failing test
function test_compaction_detection():
    input = create_compact_boundary_marker()
    result = detect_compaction(input)
    assert result == true
# Run: FAIL (function doesn't exist yet)

# 2. GREEN - Minimal implementation
function detect_compaction(transcript):
    if "compact_boundary" in transcript:
        return true
    return false
# Run: PASS

# 3. SHIP - Code works, deliver it
# Don't spend 3 hours optimizing string search
# Ship working detection, optimize if slow
```

### 2.2 Test Counting Discipline

**Critical Distinction**: Test **functions** count as tests, NOT loop iterations or assertions.

**What Counts as a Test**:
- ✅ Individual test functions (def test_feature)
- ✅ Test methods in test classes
- ✅ Each independently executable test unit

**What Does NOT Count**:
- ❌ Loop iterations within test function
- ❌ Assertions within test function
- ❌ Parameterized test data variations

**Example**:

```pseudocode
# This is ONE test (not 10):
function test_breadcrumb_parsing():
    test_cases = [
        ("s_abc/c_1/g_def/p_ghi/t_123", valid),
        ("s_abc/c_1/g_def/p_ghi/t_123", valid),
        # ... 8 more cases
    ]
    for input, expected in test_cases:
        result = parse_breadcrumb(input)
        assert result == expected
# Count: 1 test function

# This is TEN tests:
function test_valid_breadcrumb_format():
    # ... test implementation
function test_missing_session_component():
    # ... test implementation
# ... 8 more test functions
# Count: 10 test functions
```

**Why This Matters for Delegation**:

When delegating to TestEng, specify "4-6 test functions" not "4-6 test cases" to prevent confusion:

```
# GOOD delegation specification:
Create 4-6 test FUNCTIONS for breadcrumb parsing.
Each function should test one distinct scenario.

# BAD delegation specification:
Create comprehensive tests covering all cases.
# TestEng might create 1 function with 100 loop iterations!
```

### 2.3 Anti-Pattern Awareness

**Explicitly Warn Against Common Pitfalls**:

Testing anti-patterns cause wasted effort and false confidence. Agents must recognize and avoid these traps.

**Anti-Pattern 1: Test Suite Bloat**
- Symptom: 100+ tests for simple feature
- Cause: Testing every theoretical permutation
- Fix: Focus on 4-6 reality-based tests

**Anti-Pattern 2: Overengineering**
- Symptom: Complex test frameworks for simple validation
- Cause: Premature abstraction
- Fix: Start simple, abstract when patterns emerge

**Anti-Pattern 3: Testing Implementation Not Behavior**
- Symptom: Tests break when refactoring (even though behavior unchanged)
- Cause: Tests coupled to internal implementation details
- Fix: Test public interfaces and observable behavior

**Anti-Pattern 4: No Failure Testing**
- Symptom: Only happy path tested
- Cause: Assuming inputs always valid
- Fix: Test error handling and edge cases

**Warning Signs**:
- Tests take longer to write than implementation
- Test suite runs >10 minutes for small codebase
- Refactoring breaks tests despite same behavior
- Coverage metrics high but bugs still slip through

---

## 3 Test Running Discipline

### 3.1 When to Run Comprehensive Suites

**Run full test suite at strategic boundaries**:

1. **After major phase implementation**:
   - Completed significant feature development
   - Finished roadmap phase milestone
   - Ready to mark phase complete

2. **Before significant commits**:
   - Merging feature branches
   - Preparing release candidates
   - Pushing to shared repositories

3. **After specialist delegation handoffs**:
   - DevOpsEng completes implementation
   - TestEng finishes test creation
   - Integration of delegated work

4. **When integrating multiple components**:
   - Combining PA and SA work
   - Merging parallel development streams
   - System-level integration points

**Don't Run Full Suite**:
- ❌ After every tiny change
- ❌ During exploratory coding
- ❌ While debugging single function
- ❌ When iterating on implementation

### 3.2 Progressive Verbosity Protocol

**The Token Problem**: Full verbose test output for passing tests wastes 10,000+ tokens. Summary mode provides same validation with 100-500 tokens.

**The Three Levels**:

**Level 0 - Summary Mode** (Default, 100-500 tokens):
- **Purpose**: Answer "Are tests passing?"
- **Output**: Total count, pass/fail summary, execution time
- **Use When**: Validating after changes, routine checks
- **Token Cost**: Minimal (100-500 tokens)

```pseudocode
# Example Level 0 output:
Test Summary:
  Total: 19 tests
  Passed: 19
  Failed: 0
  Skipped: 0
  Duration: 0.03s
✅ All tests passed
```

**Level 1 - Failure Details** (1,000-2,000 tokens):
- **Purpose**: Identify what failed and why
- **Output**: Failed test names, error messages, moderate context
- **Use When**: Tests failing, need to identify issues
- **Token Cost**: Moderate (1,000-2,000 tokens)

```pseudocode
# Example Level 1 output:
Test Summary:
  Total: 19 tests
  Passed: 17
  Failed: 2
  Duration: 0.05s

FAILURES:
test_compaction_detection_with_invalid_marker:
  AssertionError: Expected true, got false
  Location: tests/test_hooks.py:45

test_recovery_message_format:
  KeyError: 'artifacts' not found in output
  Location: tests/test_hooks.py:67
```

**Level 2 - Full Diagnostic** (5,000+ tokens):
- **Purpose**: Deep investigation of failures
- **Output**: Complete stack traces, variable dumps, full context
- **Use When**: Debugging complex failures, investigating root causes
- **Token Cost**: High (5,000+ tokens)

```pseudocode
# Example Level 2 output:
# (Includes full stack traces, local variables,
#  complete error context, debug logging)
```

**Progressive Workflow**:

```pseudocode
# Step 1: Run in summary mode (Level 0)
run_tests(verbosity=summary)

# If all pass → Document and proceed
# If failures → Step 2

# Step 2: Re-run with failure details (Level 1)
run_tests(verbosity=failures_only)
# Identify which tests failed and why

# If cause clear → Fix and return to Step 1
# If cause unclear → Step 3

# Step 3: Run specific failing test with full diagnostics (Level 2)
run_single_test(test_name, verbosity=full_diagnostic)
# Deep investigation with complete context

# Fix root cause → Return to Step 1
```

### 3.3 Token-Efficient Testing

**The Economics**:
- Full verbose output (all tests): **10,000+ tokens**
- Summary mode (all tests): **100-500 tokens**
- Efficiency gain: **20-100x reduction**

**When Tokens Matter**:
- High CLUAC usage (>80% context consumed)
- Multiple test runs in session
- Long test suites (20+ tests)
- Documentation-heavy output

**Strategy**:
1. **Default to summary** - Start minimal
2. **Escalate verbosity only when investigating** - Pay token cost only when needed
3. **Target specific tests for deep diagnostics** - Don't dump everything

**Example**:

```pseudocode
# GOOD (token-efficient):
# Run 1: Summary mode (200 tokens)
# Result: 2 failures identified
# Run 2: Failure mode on 2 tests (500 tokens)
# Result: Root cause identified
# Run 3: Summary mode to verify fix (200 tokens)
# Total: 900 tokens

# BAD (token-wasteful):
# Run 1: Full verbose all tests (12,000 tokens)
# Run 2: Full verbose all tests (12,000 tokens)
# Run 3: Full verbose all tests (12,000 tokens)
# Total: 36,000 tokens (40x more expensive!)
```

### 3.4 Responsibility Model

**Primary Agent (PA)** - Strategic test orchestration:
- Run comprehensive suites at phase boundaries
- Validate integration across components
- Verify delegation handoff quality
- Document test results in roadmaps/checkpoints

**DevOpsEng** - Implementation iteration testing:
- Run tests during implementation cycles
- Validate changes haven't broken functionality
- Debug failures during development
- Report test passage to PA

**TestEng** - Test quality validation:
- Verify tests fail correctly (RED state)
- Ensure tests cover specified scenarios
- Validate test quality and clarity
- Confirm 4-6 test principle followed

**Division of Labor**:
- TestEng creates tests (RED phase)
- DevOpsEng makes them pass (GREEN phase)
- PA validates integration (SHIP phase)

### 3.5 Integration with Roadmaps

**Phase Completion Checklist Enhancement**:

Roadmaps specify phase completion criteria. Test passage is a **completion gate**.

**Standard Phase Completion Pattern**:

```markdown
## Phase 2: Core Implementation

**Success Criteria**:
- [ ] Core functionality implemented
- [ ] Test suite passing (N/N tests green)
- [ ] Code reviewed and approved
- [ ] Changes committed

**Test Results**: 19/19 tests passed in 0.03s
**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
```

**What to Document**:
1. Test count (total passed/total)
2. Execution time (proves performance acceptable)
3. Test run mode (summary/failures/diagnostic)
4. Any skipped tests and why

**Example Documentation**:

```markdown
**Phase 1A Complete**:
- Implementation: 5 utility functions (150 lines)
- Tests: 19/19 passed in 0.03s (summary mode)
- No tests skipped
- Breadcrumb: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
```

**Cross-Reference**: See `roadmaps.md` for complete phase structure and completion criteria patterns.

---

## 4 Foundation vs Integration Rigor

### 4.1 Foundation Testing (Strict TDD)

**What Qualifies as Foundation**:
- Core utility libraries used across codebase
- Data structures and algorithms
- Parser and serialization logic
- Infrastructure abstractions
- Authentication and security layers

**Why Strict TDD for Foundations**:
- **Bug propagation**: Foundation bugs infect everything built above
- **Hard to change**: Breaking changes ripple through dependents
- **High leverage**: Small foundation bug = many failures downstream
- **Stability requirement**: Foundations must be rock-solid

**The Two-Expert Workflow**:

1. **TestEng** creates test specifications (RED phase):
   - Define expected behavior through tests
   - Ensure tests fail correctly (prove they validate)
   - Document edge cases and error conditions

2. **DevOpsEng** implements to spec (GREEN phase):
   - Write minimal code passing tests
   - No features beyond test requirements
   - Independent validation prevents architectural flaws

**Why This Separation Matters**:
- Independent test validation catches design flaws
- Prevents "teaching to the test" (implementation biasing tests)
- Two sets of eyes on critical infrastructure
- Cost justified for foundation layers

**Example - Foundation Layer**:

```pseudocode
# Foundation: Breadcrumb parsing utility

# TestEng creates tests (RED):
test_parse_valid_breadcrumb_returns_components()
test_parse_invalid_format_raises_error()
test_parse_missing_component_returns_null()
test_parse_preserves_component_order()
test_parse_handles_malformed_timestamps()

# DevOpsEng implements (GREEN):
function parse_breadcrumb(breadcrumb_string):
    # Implementation driven by tests
    # Must pass all 5 tests
    # No additional features
```

### 4.2 Integration Testing (Pragmatic TDD)

**What Qualifies as Integration**:
- Features combining validated foundation components
- UI/presentation layers
- Workflow orchestration
- Configuration and setup
- Tool integrations

**Why Pragmatic Approach**:
- **Building on validated foundation**: Core components already tested
- **Lower propagation risk**: Integration bugs don't infect foundations
- **Faster iteration**: Can combine tests + implementation
- **Cost reduction**: Single agent can both test and implement

**Pragmatic Pattern**:
- Write tests and implementation together
- Test as you build (not strict RED-GREEN separation)
- Focus on integration points and workflows
- Leverage foundation stability

**Example - Integration Layer**:

```pseudocode
# Integration: Hook that uses breadcrumb utilities (already tested)

# Combined test + implementation:
# Test integration workflow
test_session_start_hook_generates_breadcrumb():
    hook_output = run_session_start_hook()
    assert hook_output.breadcrumb is not null
    assert breadcrumb_is_valid(hook_output.breadcrumb)

# Implementation uses foundation breadcrumb utilities
function run_session_start_hook():
    breadcrumb = generate_breadcrumb()  # Foundation utility
    return format_output(breadcrumb)
```

### 4.3 Rigor Scaling Principle

**The Pattern**: Testing rigor scales with architectural position.

**Bottom Layer (Strictest)**:
- Core utilities, parsers, data structures
- Two-expert TDD workflow
- Comprehensive edge case coverage
- Zero tolerance for bugs

**Middle Layer (Moderate)**:
- Business logic, domain models
- Standard TDD with single agent
- Focus on integration interfaces
- Pragmatic edge case selection

**Top Layer (Pragmatic)**:
- UI, workflows, configuration
- Test as you build
- Focus on user workflows
- Rely on foundation stability

**Assessment Questions**:
1. **How many components depend on this?** More dependents = stricter testing
2. **How hard is this to change later?** Harder to change = stricter testing
3. **What's the bug blast radius?** Wider impact = stricter testing
4. **Is this building on validated foundations?** Yes = more pragmatic

---

## 5 Anti-Patterns

### 5.1 Test Suite Bloat

**Definition**: Test suites that grow to unmaintainable size through exhaustive permutation testing.

**Real Example** (Cycle 42-100):
- Attempted: "Comprehensive" 10,000+ line test specification
- Result: 114 overengineered tests for simple pattern matching
- Problem: Testing every theoretical case, not actual usage
- Fix: Reformed to 5 focused tests in 96 lines
- Learning: **Test suite size doesn't equal quality**

**Symptoms**:
- 100+ tests for single feature
- Tests mostly duplicates with slight variations
- Test suite runs longer than implementation time
- Coverage metrics high but bugs still slip through

**Causes**:
- Testing mathematical completeness vs reality
- Loop-based test generation (test every value 1-100)
- Permutation explosion (every input combination)
- Confusing "comprehensive" with "exhaustive"

**Fix**:
1. Identify core functionality (1-2 tests)
2. Identify likely failures from real usage (2-3 tests)
3. Identify integration points (1-2 tests)
4. Stop at 4-6 tests unless evidence demands more

### 5.2 Loop Iterations Counted as Tests

**The Mistake**: Counting loop iterations or assertions as individual tests.

**Example**:

```pseudocode
# Agent claims "created 50 tests"
# Reality: 1 test function with 50 loop iterations

function test_breadcrumb_parsing():
    test_data = generate_50_test_cases()
    for case in test_data:
        result = parse_breadcrumb(case.input)
        assert result == case.expected
# This is ONE test, not 50!
```

**Why This Matters**:
- Misrepresents test coverage
- Violates 4-6 test principle
- Creates false confidence
- Confuses delegation instructions

**Delegation Anti-Pattern**:

```
# PA delegates: "Create 4-6 tests for breadcrumb parsing"
# TestEng delivers: 1 test function with 100 loop iterations
# TestEng reports: "Created 100 comprehensive tests"
# PA discovers: Only 1 actual test function exists
```

**Fix**: Explicitly specify "test FUNCTIONS" in delegation:

```
Create 4-6 test FUNCTIONS for breadcrumb parsing.
Each function should be independently executable.
Do NOT count loop iterations as separate tests.
```

### 5.3 Exhaustive Permutations

**The Trap**: Testing every possible input combination instead of likely reality.

**Example**:

```pseudocode
# BAD - Exhaustive permutation testing:
test_session_length_1_char()
test_session_length_2_char()
test_session_length_3_char()
# ... 100 more length tests
test_cycle_value_0()
test_cycle_value_1()
test_cycle_value_2()
# ... 1000 more cycle tests

# Total: 1100+ tests for 2 components!
```

**Why Wasteful**:
- Tests theoretical cases that never occur
- Maintenance burden (every refactor breaks 1000+ tests)
- False precision (100% coverage, still bugs in practice)
- Wastes development time

**Better Approach**:

```pseudocode
# GOOD - Reality-based testing:
test_valid_session_format()          # Happy path
test_session_too_short_rejected()    # Real edge case
test_session_too_long_rejected()     # Real edge case
test_session_invalid_chars_rejected() # Real edge case
test_cycle_negative_rejected()       # Real edge case
test_cycle_maximum_value_accepted()  # Real boundary

# Total: 6 focused tests
```

**How to Identify Exhaustive Permutations**:
- Pattern: test_value_N where N increments
- Pattern: Nested loops generating test cases
- Warning: Test count exceeds 20 for single function
- Warning: Tests take longer to write than implementation

---

## 6 Integration with Other Policies

### 6.1 Workspace Integration

**Test File Organization** (from `workspace_discipline.md`):

**Production Tests**:
- Location: Package test directory
- Pattern: Mirror source structure
- Example: `{package}/tests/test_module.py`

**Development Tests**:
- Location: Agent workspace dev_scripts
- Pattern: Timestamped temporary validation
- Example: `agent/public/dev_scripts/YYYY-MM-DD_HHMMSS_validate_feature.ext`

**What Goes Where**:

| Test Type | Location | Purpose |
|-----------|----------|---------|
| Unit tests | `{package}/tests/` | Production test suite |
| Integration tests | `{package}/tests/integration/` | End-to-end testing |
| Temporary validation | `agent/public/dev_scripts/` | One-time checks |
| Delegation tests | `agent/subagents/{role}/public/delegation_trails/{task}/` | SA test artifacts |

**Cross-Reference**: See `workspace_discipline.md` for complete artifact organization.

### 6.2 Delegation Integration

**TestEng Specialist** (from `delegation_guidelines.md`):

**Expertise**:
- Unit testing (4-6 focused tests per feature)
- Test-driven development
- Quality assurance
- Pragmatic testing approach

**When to Delegate**:
- Writing unit tests for features
- TDD implementation for foundations
- Test coverage improvement
- Test quality validation

**Critical Delegation Pattern**:

```markdown
Task: Write 4-6 focused unit tests for {feature}

Context:
- File: {source_file_path}
- Function: {function_signature}
- Purpose: {what_it_does}

Test Focus:
1. Happy path: {describe}
2. Edge case 1: {describe}
3. Edge case 2: {describe}
4. Error handling: {describe}

Success Criteria:
- 4-6 test FUNCTIONS (not loop iterations)
- Tests pass when feature implemented correctly
- Tests fail when feature broken
- Each test validates distinct scenario

Anti-Pattern Warning:
Do NOT create exhaustive permutations.
Do NOT count loop iterations as separate tests.
Focus on reality-based scenarios, not theoretical completeness.

Authority Granted:
- Create test file in tests/ directory
- Choose test framework patterns
- Mock external dependencies
- Decide assertion strategies
```

**Why Explicit Anti-Pattern Warnings**:
- TestEng cannot see this policy (no CLAUDE.md access)
- Must spoon-feed applicable standards
- Prevents 114-test disasters
- Establishes clear scope expectations

**Cross-Reference**: See `delegation_guidelines.md` for complete delegation protocol.

### 6.3 Roadmap Integration

**Phase Completion Criteria** (from `roadmaps.md`):

Roadmaps specify measurable success criteria. Test passage is a **mandatory gate**.

**Standard Phase Pattern**:

```markdown
## Phase 2: Core Implementation

**Goal**: Working implementation passing tests

**Success Criteria**:
- [ ] Core functionality implemented
- [ ] Unit tests written and passing (N/N green)
- [ ] Integration tests passing
- [ ] Code reviewed and approved

**Test Documentation**:
Run tests using progressive verbosity protocol:
1. Summary mode: Verify all passing
2. Document results: {N} tests passed in {T} seconds
3. Include in phase completion report
```

**Phase Completion Checklist Enhancement**:

```markdown
Phase X Completion:
✅ Implementation complete
✅ Test suite run (progressive verbosity protocol)
✅ Results documented: 19 tests passed in 0.03s
✅ Changes committed
✅ Roadmap updated
```

**Cross-Reference**: See `roadmaps.md` §6.2 for complete completion criteria patterns.

### 6.4 Language-Specific Implementations

**Framework Policy Hierarchy**:

This policy provides **language-agnostic principles**. Language-specific guides implement these principles with concrete syntax and tools.

**Implementation Guides** (future):
- `lang/python/testing_python.md` - pytest, unittest, coverage
- `lang/javascript/testing_javascript.md` - jest, mocha, vitest
- `lang/ruby/testing_ruby.md` - rspec, minitest
- `lang/go/testing_go.md` - testing package, testify

**What Language Guides Provide**:
- Specific test framework usage (pytest, jest, rspec)
- Language-specific syntax and patterns
- Tool-specific commands and flags
- Ecosystem-specific best practices

**What This Policy Provides**:
- Testing philosophy (4-6 principle)
- TDD workflow (RED-GREEN-SHIP)
- Rigor scaling (foundation vs integration)
- Anti-patterns (universal across languages)

**Relationship**: Language guides **implement** this policy's principles in specific contexts.

---

## 7 Validation & Examples

### 7.1 Well-Designed Test Suites

**Example 1 - Foundation Layer (Strict TDD)**:

```pseudocode
# Feature: Breadcrumb parsing utility (foundation)
# Test Suite: 6 focused tests

test_parse_valid_breadcrumb_returns_all_components():
    # Happy path: Valid format works
    input = "s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890"
    result = parse_breadcrumb(input)
    assert result.session == "abc12345"
    assert result.cycle == 42
    assert result.git == "def6789"
    assert result.prompt == "ghi01234"
    assert result.timestamp == 1234567890

test_parse_invalid_format_raises_error():
    # Error handling: Malformed input rejected
    input = "invalid_breadcrumb_format"
    assert raises_error(parse_breadcrumb(input))

test_parse_missing_component_returns_partial():
    # Edge case: Abbreviated breadcrumbs (missing components)
    input = "s_abc12345/c_42/t_1234567890"  # Missing g and p
    result = parse_breadcrumb(input)
    assert result.session == "abc12345"
    assert result.git is null
    assert result.prompt is null

test_parse_preserves_component_order():
    # Integration: Component ordering matters
    input = "s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890"
    result = parse_breadcrumb(input)
    components = result.to_ordered_list()
    assert components == [session, cycle, git, prompt, timestamp]

test_parse_handles_malformed_timestamp():
    # Edge case: Invalid timestamp format
    input = "s_abc12345/c_42/g_def6789/p_ghi01234/t_invalid"
    assert raises_error(parse_breadcrumb(input))

test_parse_unicode_in_components():
    # Reality check: Ensure ASCII-only validation
    input = "s_abc™2345/c_42/g_def6789/p_ghi01234/t_1234567890"
    assert raises_error(parse_breadcrumb(input))

# Total: 6 tests covering reality-based scenarios
```

**Example 2 - Integration Layer (Pragmatic TDD)**:

```pseudocode
# Feature: SessionStart hook integration
# Test Suite: 4 focused tests (building on foundation)

test_hook_generates_valid_breadcrumb():
    # Happy path: Hook produces valid breadcrumb
    output = run_session_start_hook()
    assert output.breadcrumb is not null
    assert is_valid_breadcrumb_format(output.breadcrumb)

test_hook_detects_compaction():
    # Integration: Compaction detection workflow
    mock_transcript_with_compaction_marker()
    output = run_session_start_hook()
    assert output.compaction_detected == true
    assert "ULTRATHINK" in output.recovery_message

test_hook_includes_artifact_paths_when_found():
    # Integration: Artifact discovery workflow
    create_mock_artifacts()
    output = run_session_start_hook()
    assert output.latest_checkpoint in output.recovery_message
    assert output.latest_reflection in output.recovery_message

test_hook_graceful_when_artifacts_missing():
    # Edge case: No artifacts available
    remove_all_artifacts()
    output = run_session_start_hook()
    assert output.recovery_message contains "Not found"
    assert output.success == true  # Graceful degradation

# Total: 4 tests (integration builds on tested foundations)
```

### 7.2 Common Testing Mistakes

**Mistake 1: Testing Implementation Details**:

```pseudocode
# BAD - Coupled to implementation:
test_parser_uses_regex_pattern():
    parser = create_parser()
    assert parser.internal_regex == "^s_[a-f0-9]{8}.*"
    # Breaks when refactoring to different parsing approach

# GOOD - Tests behavior:
test_parser_accepts_valid_format():
    parser = create_parser()
    result = parser.parse("s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890")
    assert result.is_valid == true
    # Works regardless of parsing implementation
```

**Mistake 2: Unclear Test Names**:

```pseudocode
# BAD - Meaningless names:
test_case_1()
test_edge_case()
test_function_works()

# GOOD - Self-documenting names:
test_parse_valid_breadcrumb_returns_components()
test_parse_missing_session_raises_error()
test_parse_preserves_component_order()
```

**Mistake 3: No Failure Testing**:

```pseudocode
# BAD - Only happy path:
test_feature_works():
    result = do_feature(valid_input)
    assert result == expected

# GOOD - Tests both success and failure:
test_feature_succeeds_with_valid_input()
test_feature_raises_error_with_invalid_input()
test_feature_handles_missing_data_gracefully()
```

---

## 8 Anti-Patterns Summary

**Testing Anti-Patterns to Avoid**:

1. **Test Suite Bloat**:
   - ❌ 114 tests for simple pattern matching
   - ✅ 5 focused tests achieving same confidence

2. **Loop Iterations as Tests**:
   - ❌ Claiming "50 tests" for 1 function with 50 loop iterations
   - ✅ Counting only test functions as tests

3. **Exhaustive Permutations**:
   - ❌ Testing every value from 1-1000
   - ✅ Testing boundaries and likely failures

4. **Testing Implementation Not Behavior**:
   - ❌ Asserting internal implementation details
   - ✅ Testing public interfaces and observable behavior

5. **No Edge Case Testing**:
   - ❌ Only testing happy path
   - ✅ Testing error handling and boundaries

6. **Overengineered Test Frameworks**:
   - ❌ Complex abstractions for simple validation
   - ✅ Simple direct tests

7. **Endless Refactoring**:
   - ❌ Red → Green → Refactor → Refactor → ...
   - ✅ Red → Green → Ship

**Warning Signs**:
- Tests take longer to write than implementation
- Test suite runs >10 minutes for small codebase
- Refactoring breaks tests despite unchanged behavior
- High coverage but bugs still slip through
- More test code than production code (ratio >3:1)

---

## 9 Philosophy: Tests as Infrastructure

**Core Insight**: Tests aren't bureaucracy—they're **quality infrastructure** that proves code works, guides implementation, and prevents regressions.

**What Good Tests Provide**:
1. **Confidence**: Code works as expected
2. **Documentation**: Living examples of usage
3. **Safety**: Refactor without fear
4. **Contracts**: Interface guarantees
5. **Regression Prevention**: Catch breaking changes

**The Pragmatic Balance**:
- **Too Few Tests**: Code breaks, no confidence, manual testing burden
- **Too Many Tests**: Maintenance nightmare, false precision, wasted effort
- **Just Right**: 4-6 focused tests per feature, reality-based coverage

**Foundation vs Integration**:
- **Foundations**: Strict TDD (two-expert workflow)
- **Integration**: Pragmatic TDD (combined test+implementation)
- **Rationale**: Rigor scales with architectural impact

**The Mantra**: "Test reality, not possibilities. 4-6 focused tests beat 40-60 permutations. Ship working code."

**Without good tests**: Fragile code, manual validation, fear of refactoring, regression bugs.

**With good tests**: Confident development, living documentation, safe refactoring, quality assurance.

---

## 10 Evolution & Feedback

This policy evolves through:
- **Real-world effectiveness**: Do 4-6 tests provide sufficient confidence?
- **Language-specific adaptation**: How do different ecosystems apply principles?
- **Agent feedback**: What guidance helps vs hinders?
- **Testing tool evolution**: New frameworks and approaches

**Principle**: Testing should enable confident development, not create busywork. If testing practices don't improve quality and velocity → refine them.

**Feedback Channels**:
- Report testing anti-patterns encountered
- Suggest language-specific implementation patterns
- Document effective test design discoveries
- Share test-to-implementation ratio insights

---

**Policy Established**: Pragmatic testing standards balancing quality assurance with sustainable development velocity through focused tests (4-6 principle), progressive verbosity protocols, and rigor scaling based on architectural position.

**Core Wisdom**: "Quality through focus. 4-6 focused tests beat 40-60 variations. Test reality, not possibilities. Foundation rigor, integration pragmatism. Red-Green-Ship."

**Remember**: Tests are living documentation proving code works. Write enough to have confidence, not so many you can't maintain them. This is infrastructure for **all agents** developing quality software pragmatically.

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
