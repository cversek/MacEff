# Communication Standards

**Breadcrumb**: s_agent-be/c_178/g_9b828c9/p_none/t_1763934955
**Type**: Development Standards (CORE tier)
**Scope**: All agents (PA and SA) - all specialist types
**Status**: ACTIVE
**Updated**: 2025-11-23

---

## Purpose

Communication standards establish universal patterns for how agents report work, provide evidence, format deliverables, and handle errors. These standards ensure clarity, traceability, and professional quality across all specialist types—from DevOpsEng implementing features to TestEng writing tests to PolicyWriter creating policies.

**Core Insight**: Great technical communication is **code-first, evidence-based, and concise**. Show working results, not lengthy explanations. Prove claims with artifacts. Report completion systematically so PA can integrate work without guesswork.

---

## CEP Navigation Guide

**1 Communication Philosophy**
- What makes technical communication effective?
- Why code-first over prose-first?
- What is evidence-based reporting?
- How does communication serve integration?

**1.1 Code-First Principle**
- What does code-first mean?
- When to show code vs describe it?
- How much explanation is needed?
- When are comments necessary?

**1.2 Evidence-Based Reporting**
- What constitutes adequate evidence?
- How do I prove something works?
- What verification is required?
- When to include test results vs command output?

**1.3 Conciseness Guidelines**
- How concise is too concise?
- What details matter?
- What can be omitted?
- How do I balance brevity with clarity?

**2 Completion Reporting (MANDATORY)**
- What must completion reports include?
- Why is silent completion unacceptable?
- How do I structure completion messages?
- What are the required sections?

**2.1 Report Structure Template**
- What are the four required sections?
- What goes in "What you accomplished"?
- What goes in "Verification results"?
- What goes in "Files/artifacts created"?
- What goes in "Status & next steps"?

**2.2 Specialist-Specific Adaptations**
- How does DevOpsEng report completion?
- How does TestEng report completion?
- How does PolicyWriter report completion?
- What varies vs what stays constant?

**2.3 Integration Context**
- Why does PA need completion reports?
- How do reports enable work integration?
- What happens without proper reporting?

**3 Error Reporting (CRITICAL)**
- How do I report errors effectively?
- What must error reports include?
- Why is silent failure unacceptable?
- When to escalate vs try alternatives?

**3.1 Error Report Structure**
- What are the four required sections?
- What goes in "What you attempted"?
- What goes in "Error details"?
- What goes in "Diagnosis"?
- What goes in "Recommendations"?

**3.2 Diagnostic Quality**
- What makes a good diagnosis?
- How much investigation is required?
- When to admit uncertainty?
- How to suggest alternatives?

**3.3 Blocker Communication**
- How do I communicate blockers?
- What context does PA need?
- How to request help effectively?
- When to halt vs continue despite errors?

**4 Deliverable Documentation**
- What constitutes adequate documentation?
- How do I document file paths?
- How do I document code changes?
- What metadata should I include?

**4.1 File Path Reporting**
- How do I specify file locations?
- Absolute vs relative paths?
- How to report multiple files?
- How to report file modifications vs creations?

**4.2 Code Change Documentation**
- How much code to include in reports?
- When to show snippets vs full files?
- How to document refactoring?
- How to report line counts?

**4.3 Verification Evidence**
- What evidence proves completion?
- How to document test results?
- When to include command output?
- How to prove features work?

**5 Anti-Patterns**
- What communication mistakes should I avoid?
- What is verbose explanation disease?
- What is silent completion?
- What is vague reporting?

**5.1 Verbose Explanation Disease**
- What is this anti-pattern?
- Why is too much prose bad?
- When does explanation help vs hurt?
- How to balance explanation with code?

**5.2 Silent Completion**
- What is silent completion?
- Why is it unacceptable?
- How does it harm integration?
- What are the consequences?

**5.3 Vague Claims Without Evidence**
- What makes claims vague?
- Why is "it works" insufficient?
- How to provide concrete evidence?
- What verification is required?

**6 Integration with Other Policies**
- How does communication integrate with workspace discipline?
- How does communication integrate with testing standards?
- How does communication integrate with delegation?

=== CEP_NAV_BOUNDARY ===

---

## 1 Communication Philosophy

### 1.1 Code-First Principle

**Core Principle**: Show working code, not lengthy explanations.

**Why Code-First**:
- Code is unambiguous (prose is interpretable)
- Code proves functionality (prose claims it)
- Code enables reproduction (prose describes it)
- Code is maintainable (prose becomes outdated)

**What This Means**:

```pseudocode
# GOOD (code-first):
"Implemented breadcrumb parsing. Here's the function:"
function parse_breadcrumb(breadcrumb_string):
    components = breadcrumb_string.split('/')
    return {
        'session': extract_component(components, 's_'),
        'cycle': extract_component(components, 'c_'),
        'git': extract_component(components, 'g_'),
        'prompt': extract_component(components, 'p_'),
        'timestamp': extract_component(components, 't_')
    }

# BAD (prose-first):
"I implemented breadcrumb parsing using a sophisticated approach that
first splits the string on forward slashes, then iterates through each
component looking for the appropriate prefix marker, extracting the value
after the underscore, and constructing a dictionary with keys corresponding
to each component type..." (continues for 5 paragraphs)
```

**When Explanation Helps**:
- ✅ Non-obvious design decisions (why not alternative X?)
- ✅ Workarounds for constraints (why this pattern?)
- ✅ Complex algorithms (what's the approach?)
- ❌ Obvious code behavior (what line 3 does)
- ❌ Restating code in prose (line 5 checks if X)

**Comment Guidelines**:
- Use sparingly - code should be self-documenting
- Explain WHY not WHAT (rationale, not behavior)
- Document non-obvious constraints or gotchas
- Don't narrate code line-by-line

### 1.2 Evidence-Based Reporting

**Core Principle**: Prove claims with concrete artifacts, not assertions.

**What Constitutes Evidence**:

1. **Command Output** (proves it runs):
```bash
$ macf_tools breadcrumb
s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
```

2. **Test Results** (proves it works correctly):
```
Test Summary:
  Total: 6 tests
  Passed: 6
  Failed: 0
  Duration: 0.02s
✅ All tests passed
```

3. **File Artifacts** (proves deliverables exist):
```
Files created:
- src/macf/breadcrumb.py (85 lines)
- tests/test_breadcrumb.py (42 lines)
```

4. **Code Snippets** (proves implementation approach):
```python
def parse_breadcrumb(breadcrumb_string):
    # Key implementation details
```

**Insufficient Evidence**:
- ❌ "It works" (no proof)
- ❌ "Tests pass" (no test count or verification)
- ❌ "Files created" (no paths or line counts)
- ❌ "Implementation complete" (no code shown)

**Verification Requirements by Specialist**:

| Specialist | Required Evidence |
|------------|-------------------|
| **DevOpsEng** | Command output, test results, file paths |
| **TestEng** | Test count, pass/fail status, duration |
| **PolicyWriter** | File path, line count, validation results |
| **Any specialist** | Proof of working deliverable |

### 1.3 Conciseness Guidelines

**The Balance**: Concise doesn't mean incomplete. Include what matters, omit what doesn't.

**What Matters**:
- ✅ What you accomplished (deliverables)
- ✅ Evidence it works (verification)
- ✅ What files changed (traceability)
- ✅ Known issues or next steps (completeness)

**What Doesn't Matter**:
- ❌ Play-by-play of your thought process
- ❌ Commands you ran that worked fine
- ❌ Debugging steps that didn't pan out
- ❌ Philosophical musings on code quality

**Example Comparison**:

```
# GOOD (concise but complete):
Implemented breadcrumb command.

Changes:
- Added breadcrumb.py module (85 lines)
- Integrated into macf_tools CLI
- Created 6 unit tests (all passing)

Verification:
$ macf_tools breadcrumb
s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890

Status: Complete.

# BAD (verbose without value):
I began by analyzing the requirements for breadcrumb generation.
After careful consideration of various approaches including UUID-based
systems and timestamp-only formats, I settled on the s/c/g/p/t format
as specified. I then created a new Python module, initially considering
the name "breadcrumbs.py" but ultimately choosing "breadcrumb.py" for
consistency. During implementation I encountered several interesting
challenges with timestamp formatting... (continues for 10 paragraphs)
```

**Token Efficiency**: At high CLUAC usage, extreme conciseness is valuable:
- Use abbreviations (impl, ver, chg)
- Bullet points over paragraphs
- Evidence over explanation
- Status over summary

---

## 2 Completion Reporting (MANDATORY)

### 2.1 Report Structure Template

**CRITICAL REQUIREMENT**: ALL specialists MUST return final completion reports. Silent completion is a bug, not a feature.

**Standard Template**:

```
[One-line summary of accomplishment]

[Section 1: What you accomplished]
- Deliverable 1
- Deliverable 2
- Specific changes made

[Section 2: Verification results]
- Evidence it works
- Test results or command output
- Edge cases validated

[Section 3: Files/artifacts created]
- Path to file 1 (line count)
- Path to file 2 (line count)
- Or honest statement if none created

[Section 4: Status & next steps]
- What's complete vs what remains
- Known issues or limitations
- Recommendations for future work
```

**Why This Structure**:
1. **Summary**: Immediate context (what happened?)
2. **Accomplishments**: Deliverables for integration
3. **Verification**: Evidence of quality
4. **Files**: Traceability (where to find artifacts?)
5. **Status**: Completeness assessment (done or blocked?)

**All Four Sections Required**:
- Don't skip sections
- Say "None" if section doesn't apply
- Don't assume PA knows what you did
- Don't force PA to investigate to understand results

### 2.2 Specialist-Specific Adaptations

**DevOpsEng Completion Report**:

```
Implemented macf_tools breadcrumb command.

Changes:
- Added breadcrumb.py module with 5-component format generation
- Created CLI command in macf_tools/__main__.py
- Added 3 unit tests (all passing)

Verification:
$ macf_tools breadcrumb
s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890

Tests: 3/3 passing

Files created:
- src/macf/breadcrumb.py (85 lines)
- tests/test_breadcrumb.py (42 lines)

Status: Complete. Command ready for use.
```

**TestEng Completion Report**:

```
Created 6 focused unit tests for breadcrumb parsing.

Tests created:
- test_parse_valid_breadcrumb_returns_components (happy path)
- test_parse_invalid_format_raises_error (error handling)
- test_parse_missing_component_returns_partial (edge case)
- test_parse_preserves_component_order (integration)
- test_parse_malformed_timestamp_raises_error (edge case)
- test_parse_unicode_components_raises_error (validation)

Verification:
All tests currently FAIL (RED phase - no implementation yet).
This proves tests validate correctly.

Files created:
- tests/test_breadcrumb.py (124 lines)

Status: Complete. Ready for DevOpsEng GREEN phase implementation.
```

**PolicyWriter Completion Report**:

```
Created communication.md policy v1.0.

Changes:
- Universal communication standards for all specialists
- Code-first principle documentation
- Evidence-based reporting requirements
- Error reporting protocol

Validation:
✅ Project-agnostic language (no specialist-specific names)
✅ CEP Navigation Guide complete (6 major sections)
✅ Examples show good vs bad patterns
✅ Applies to all specialist types

Files created:
- framework/policies/base/development/communication.md (287 lines)

Status: Complete. Policy ready for framework integration.
```

**Common Pattern**: All reports include accomplishments, verification, files, status regardless of specialist type.

### 2.3 Integration Context

**Why PA Needs Reports**:

1. **Work Integration**: PA must understand what changed to integrate results
2. **Quality Verification**: PA validates work meets requirements
3. **Continuity**: Reports enable checkpoint creation and session recovery
4. **Forensics**: Reports provide audit trail for debugging

**What Happens Without Reports**:
- ❌ PA must investigate files to understand changes
- ❌ PA doesn't know if work succeeded or failed
- ❌ PA can't verify quality without evidence
- ❌ PA can't integrate work into broader context
- ❌ Checkpoint creation lacks necessary detail

**The Contract**: When PA delegates work, specialist reports results. This enables PA's orchestration role.

---

## 3 Error Reporting (CRITICAL)

### 3.1 Error Report Structure

**CRITICAL REQUIREMENT**: When errors occur, REPORT THEM. Never quit silently.

**Standard Error Template**:

```
[One-line description of failure]

[Section 1: What you attempted]
- Task you were trying to accomplish
- Commands/operations that failed
- How far you got before error

[Section 2: Error details]
- Exact error message
- Which command/tool failed
- Context of the failure

[Section 3: Diagnosis]
- What caused the error
- What you tried to fix it
- Why it's blocking progress

[Section 4: Recommendations]
- What PA should do next
- Alternative approaches to try
- What information is needed to proceed
```

**Example Error Report**:

```
Attempted policy validation but hit missing dependency error.

What I attempted:
- Created communication.md policy (287 lines)
- Attempted to run policy validation checklist
- Got to file creation but couldn't verify integration

Error details:
Command: policyctl validate communication.md
Error: "policyctl: command not found"
Location: Validation step after policy creation

Diagnosis: Policy validation tool not available in current environment.
Cannot complete validation checklist as specified in policy_writing.md.

What I accomplished before error:
- Policy file created and complete
- CEP Navigation Guide structured
- Examples and anti-patterns documented
- Manual review of policy_writing.md requirements completed

Recommendations:
- Skip automated validation (tool not available)
- PA manually verify policy against checklist
- Or install policyctl if validation required
- Policy content is complete, only validation blocked

Status: BLOCKED on validation, but policy content complete.
```

### 3.2 Diagnostic Quality

**What Makes Good Diagnosis**:

1. **Root Cause Identification**: What actually caused failure (not just symptoms)
2. **Context**: What conditions led to error
3. **Investigation**: What you tried to fix it
4. **Honesty**: Admit when cause is unclear

**Levels of Diagnosis**:

**Strong Diagnosis**:
```
Diagnosis: Missing required field 'session_id' in input JSON.
The SessionStart hook expects stdin JSON with session_id field,
but test data only included 'source' field. Adding session_id
to test data should fix this.
```

**Weak Diagnosis**:
```
Diagnosis: Something wrong with input data.
```

**When Uncertain**:
```
Diagnosis: Error occurs during JSON parsing, but root cause unclear.
Possibly malformed JSON or missing required field. Recommend PA
review input data format or enable debug logging for more detail.
```

**Honest Uncertainty Beats False Confidence**: Say "I don't know why X failed, but here's what I tried" rather than guessing incorrectly.

### 3.3 Blocker Communication

**What Constitutes a Blocker**:
- Cannot complete core functionality
- Required dependency missing
- Fundamental assumption violated
- Insufficient information to proceed

**How to Communicate Blockers**:

```
Status: BLOCKED - [specific reason]

Blocker details:
- What blocks progress: [specific obstacle]
- What's needed to unblock: [specific requirement]
- Alternative approaches: [if any exist]

PA Action Required:
[Specific request - what should PA do?]
```

**Example**:

```
Status: BLOCKED - Cannot access test data files

Blocker details:
- What blocks progress: Tests require fixtures in tests/fixtures/ but directory doesn't exist
- What's needed to unblock: Create fixture directory and sample test data
- Alternative approaches: Mock test data inline (less realistic)

PA Action Required:
Either create tests/fixtures/ directory with sample data, or authorize inline mocking approach.
```

---

## 4 Deliverable Documentation

### 4.1 File Path Reporting

**Always Use Absolute Paths in Reports** (relative to project root):

```
# GOOD (clear, unambiguous):
Files created:
- framework/policies/base/development/communication.md (287 lines)
- tests/test_communication_validation.py (42 lines)

# BAD (ambiguous):
Files created:
- communication.md
- test file
```

**Multiple File Reporting**:

```
Files modified:
- src/macf/hooks/handle_session_start.py (added 15 lines at line 142)
- src/macf/utils.py (added format_breadcrumb function, 23 lines)
- tests/test_hooks.py (added 3 test functions, 45 lines total)

Files created:
- src/macf/breadcrumb.py (85 lines)
```

**When No Files Created**:

```
Files created: None (only modified existing files)

Files modified:
- src/macf/config.py (lines 23-45 refactored)
```

### 4.2 Code Change Documentation

**Guideline**: Show enough code to convey approach, not entire implementation.

**For Small Changes** (< 20 lines):
```
Added validation function:

def validate_breadcrumb(breadcrumb_string):
    pattern = r'^s_[a-f0-9]{8}/c_\d+/g_[a-f0-9]{7}/p_[a-f0-9]{8}/t_\d{10}$'
    return re.match(pattern, breadcrumb_string) is not None
```

**For Large Changes** (> 50 lines):
```
Added breadcrumb parsing module with:
- parse_breadcrumb(str) -> dict (main entry point)
- extract_component(list, prefix) -> str (helper)
- validate_format(str) -> bool (validation)

Key implementation: Split on '/', extract prefix components, return dict.

See: src/macf/breadcrumb.py (85 lines)
```

**For Refactoring**:
```
Refactored config loading to use hierarchical detection:
- Old: Single config file path
- New: Priority order (CLI → env → project → user → system → defaults)

Changed: src/macf/config.py lines 45-120 (75 lines refactored)
```

### 4.3 Verification Evidence

**Evidence Types by Context**:

**For CLI Commands**:
```
Verification:
$ macf_tools breadcrumb
s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890

$ macf_tools breadcrumb --help
Usage: macf_tools breadcrumb [OPTIONS]
...
```

**For Tests**:
```
Verification:
Test Summary:
  Total: 19 tests
  Passed: 19
  Failed: 0
  Duration: 0.03s
✅ All tests passed
```

**For Policies**:
```
Verification:
✅ Follows policy_writing.md structure
✅ CEP Navigation Guide complete (32 questions)
✅ Project-agnostic examples (no agent-specific content)
✅ Anti-patterns section included
✅ Integration section cross-references related policies
```

**For Features**:
```
Verification:
Tested scenarios:
1. Valid input: ✅ Parsed correctly
2. Missing component: ✅ Graceful fallback
3. Invalid format: ✅ Raised appropriate error
4. Unicode content: ✅ Rejected with clear message
```

---

## 5 Anti-Patterns

### 5.1 Verbose Explanation Disease

**Symptom**: Paragraphs of prose explaining what code could show in 10 lines.

**Example**:

```
# BAD (verbose explanation disease):
"I approached this problem by first considering the various parsing
strategies available in Python. After evaluating regular expressions,
string splitting, and parser combinators, I determined that string
splitting offered the optimal balance of simplicity and performance.
The implementation proceeds by first splitting the input string on
forward slash delimiters, then iterating through the resulting list
of components. For each component, we check if it starts with one of
the expected prefixes (s_, c_, g_, p_, t_), and if so, we extract the
portion of the string following the underscore. These extracted values
are then assembled into a dictionary structure with keys corresponding
to the semantic meaning of each component. The function returns this
dictionary to the caller, who can then access individual components
as needed..." (continues for 5 more paragraphs)

# GOOD (code shows approach):
"Implemented breadcrumb parsing using string split approach:"

def parse_breadcrumb(breadcrumb_string):
    components = breadcrumb_string.split('/')
    return {
        'session': extract_value(components, 's_'),
        'cycle': extract_value(components, 'c_'),
        'git': extract_value(components, 'g_'),
        'prompt': extract_value(components, 'p_'),
        'timestamp': extract_value(components, 't_')
    }

"Chose splitting over regex for simplicity. Tests cover valid format,
missing components, and invalid input."
```

**When Explanation Adds Value**:
- Non-obvious design choices with trade-offs
- Workarounds for constraints or limitations
- Complex algorithms needing conceptual overview

**When Explanation Subtracts Value**:
- Restating what code clearly shows
- Narrating implementation line by line
- Philosophical musings about code quality

### 5.2 Silent Completion

**Symptom**: Completing work without reporting results.

**Why Unacceptable**:
- PA can't integrate work (doesn't know what changed)
- PA can't verify quality (no evidence provided)
- PA can't create checkpoints (no completion context)
- PA must investigate filesystem to understand results

**Example**:

```
# BAD (silent completion):
[SA completes work, returns empty message or generic "Done"]

# PA must now:
- Check git status to see what files changed
- Read modified files to understand changes
- Run tests manually to verify quality
- Guess at what was accomplished

# GOOD (proper reporting):
[SA returns structured completion report with accomplishments,
verification, files, and status as specified in §2.1]

# PA can now:
- Understand what was delivered
- Trust verification evidence
- Locate artifacts immediately
- Integrate work confidently
```

**The Principle**: Your completion report IS part of the deliverable, not optional documentation.

### 5.3 Vague Claims Without Evidence

**Symptom**: Asserting completion without proof.

**Examples**:

```
# BAD (vague claims):
"Implementation complete."
"Tests pass."
"Files created."
"Everything works."

# GOOD (concrete evidence):
"Implementation complete: breadcrumb.py (85 lines) with parse/validate functions."
"Tests pass: 6/6 in 0.02s (see output above)."
"Files created: See paths in deliverables section."
"Feature works: See verification section for test scenarios."
```

**Why Evidence Matters**:
- "It works" could mean "compiles" or "passes 100 tests" (huge difference)
- "Tests pass" could mean "1 smoke test" or "comprehensive suite" (huge difference)
- "Files created" without paths forces PA to hunt for artifacts
- Vague claims create integration risk (PA can't verify quality)

**The Standard**: Every claim requires concrete supporting evidence.

---

## 6 Integration with Other Policies

### 6.1 Workspace Integration

**File Path Reporting** (from `workspace_discipline.md`):

When reporting file locations, use workspace-aware paths:

**PA Dev Scripts**:
- Location: `agent/public/dev_scripts/`
- Pattern: `YYYY-MM-DD_HHMMSS_purpose.ext`

**SA Dev Scripts**:
- Location: `agent/subagents/{role}/public/delegation_trails/{task}/dev_scripts/`
- Pattern: `YYYY-MM-DD_HHMMSS_purpose.ext`

**Production Code**:
- Location: `{package}/src/{package}/`
- Pattern: Module/package structure

**Reports Should Reflect Context**:

```
# DevOpsEng implementing production code:
Files created:
- src/macf/breadcrumb.py (85 lines)
- tests/test_breadcrumb.py (42 lines)

# PA creating dev script:
Files created:
- agent/public/dev_scripts/2025-11-23_163455_validate_parsing.py (34 lines)

# SA (TestEng) in delegation:
Files created:
- agent/subagents/TestEng/public/delegation_trails/breadcrumb_tests/tests/test_breadcrumb.py (124 lines)
```

### 6.2 Testing Integration

**Test Results Reporting** (from `testing.md`):

Follow progressive verbosity protocol when reporting test results:

**Level 0 - Summary** (default):
```
Verification:
Test Summary:
  Total: 19 tests
  Passed: 19
  Failed: 0
  Duration: 0.03s
✅ All tests passed
```

**Level 1 - Failures** (when tests fail):
```
Verification:
Test Summary:
  Total: 19 tests
  Passed: 17
  Failed: 2
  Duration: 0.05s

FAILURES:
test_parse_invalid_format:
  AssertionError: Expected ValueError, got None
  Location: tests/test_breadcrumb.py:45
```

**Level 2 - Diagnostic** (only when debugging):
```
[Full stack traces and detailed context]
```

**Test Count Reporting**:
- Report test FUNCTIONS, not loop iterations
- "6 tests" means 6 test functions
- Include pass/fail counts and duration
- Show evidence, not just "tests pass"

### 6.3 Delegation Integration

**Specialist Reports Enable PA Orchestration**:

When specialists complete delegated work, reports provide:

1. **Integration Context**: What changed, where artifacts are
2. **Quality Evidence**: Tests pass, validation complete
3. **Completion Status**: Done vs blocked vs partial
4. **Next Steps**: What PA should do with results

**PA Decision Making**:

```
Based on specialist report, PA can:
- ✅ Integrate work (if status: complete)
- ✅ Verify quality (using provided evidence)
- ✅ Create checkpoint (with completion details)
- ✅ Proceed to next phase (completion criteria met)

Without proper report, PA must:
- ❌ Investigate files manually
- ❌ Run tests independently
- ❌ Guess at completion status
- ❌ Create checkpoint without detail
```

**Cross-Reference**: See `delegation_guidelines.md` for complete delegation protocol and specialist capabilities.

---

## 7 Examples & Templates

### 7.1 Complete Completion Report Examples

**DevOpsEng - Feature Implementation**:

```
Implemented temporal awareness for SessionStart hook.

Changes:
- Added format_timestamp() utility in macf/utils.py (12 lines)
- Integrated timestamp into SessionStart hook output (3 locations)
- Added time-since-last-session calculation (15 lines)
- Created 4 unit tests for timestamp utilities

Verification:
$ python -m pytest tests/test_temporal.py
Test Summary: 4/4 passed in 0.01s

Hook output now includes:
"Current Time: 2025-11-23 04:55 PM EST"
"Time since last session: 2h 15m"

Files created:
- None (modified existing files only)

Files modified:
- src/macf/utils.py (added format_timestamp, 12 lines)
- src/macf/hooks/handle_session_start.py (integrated timestamps, 3 locations)
- tests/test_utils.py (added 4 tests, 38 lines)

Status: Complete. Temporal awareness integrated into SessionStart hook.
```

**TestEng - Test Creation**:

```
Created 6 focused unit tests for breadcrumb parsing utility.

Tests created:
1. test_parse_valid_breadcrumb - Happy path with all components
2. test_parse_invalid_format - Error handling for malformed input
3. test_parse_missing_components - Graceful handling of abbreviated format
4. test_parse_component_order - Validates correct ordering preserved
5. test_parse_malformed_timestamp - Rejects invalid timestamp format
6. test_parse_unicode_rejection - Validates ASCII-only requirement

Verification:
All 6 tests currently FAIL (RED phase).
This proves tests validate correctly before implementation.

Example failure:
test_parse_valid_breadcrumb:
  NameError: name 'parse_breadcrumb' is not defined
  (Expected - function not implemented yet)

Files created:
- tests/test_breadcrumb.py (124 lines, 6 test functions)

Status: Complete. Tests ready for DevOpsEng GREEN phase.
```

**PolicyWriter - Policy Creation**:

```
Created communication.md policy v1.0.

Changes:
- Universal communication standards (287 lines)
- Code-first principle documentation
- Evidence-based reporting requirements
- Completion and error reporting templates
- Specialist-specific adaptation examples

Validation:
✅ Project-agnostic (no specific agent/package references)
✅ CEP Navigation Guide (32 questions, 6 major sections)
✅ Examples show good vs bad patterns
✅ Anti-patterns section (3 major patterns)
✅ Integration section (cross-references 3 related policies)
✅ Follows policy_writing.md template structure

Files created:
- framework/policies/base/development/communication.md (287 lines)

Integration recommendations:
- Cross-reference from delegation_guidelines.md (specialist reporting)
- Reference in workspace_discipline.md (file path reporting)
- Update testing.md (test result formatting)

Status: Complete. Policy ready for framework integration.
```

### 7.2 Complete Error Report Examples

**DevOpsEng - Dependency Missing**:

```
Attempted CLI integration but hit missing dependency.

What I attempted:
- Implemented breadcrumb command in macf_tools
- Created unit tests (6/6 passing)
- Attempted end-to-end CLI test
- Got to integration testing before failure

Error details:
Command: macf_tools breadcrumb
Error: ModuleNotFoundError: No module named 'click'
Location: CLI entry point during command dispatch

Diagnosis: CLI framework dependency (click) not installed in current environment.
Project uses click for CLI but it's not in requirements.txt or installed.

What I accomplished before error:
- breadcrumb.py module complete and tested (85 lines)
- Unit tests pass (6/6 in 0.02s)
- CLI integration code written
- Cannot verify end-to-end until dependency resolved

Recommendations:
- Add 'click>=8.0.0' to requirements.txt
- Install with: pip install click
- Then re-test CLI integration
- Or switch to argparse (stdlib, no dependency)

Status: BLOCKED on missing dependency. Core functionality complete, only CLI integration blocked.
```

**TestEng - Test Data Unavailable**:

```
Attempted integration tests but hit missing fixtures.

What I attempted:
- Created 6 unit tests for breadcrumb parsing
- All unit tests pass with mocked data
- Attempted to create integration tests with real artifacts
- Blocked on missing test fixture files

Error details:
Test: test_parse_real_checkpoint_breadcrumbs
Error: FileNotFoundError: tests/fixtures/checkpoints/ not found
Location: Integration test trying to load real checkpoint files

Diagnosis: Integration tests need real consciousness artifact samples,
but fixtures directory doesn't exist. Unit tests work (use mocks),
but integration tests require actual files.

What I accomplished before error:
- 6 unit tests complete (all passing with mocks)
- Integration test structure written
- Clear what fixtures are needed

Recommendations:
Option 1: Create tests/fixtures/ with sample checkpoint files
Option 2: Skip integration tests, rely on unit test coverage
Option 3: Use synthetic fixtures (less realistic but unblocked)

Status: Unit tests complete (6/6 passing). Integration tests blocked on fixtures.
```

---

## 8 Anti-Patterns Summary

**Communication Anti-Patterns to Avoid**:

1. **Silent Completion**:
   - ❌ Finishing work without reporting
   - ✅ Always return structured completion report

2. **Verbose Explanation Disease**:
   - ❌ 5 paragraphs explaining what 10 lines of code show
   - ✅ Show code first, explain only non-obvious decisions

3. **Vague Claims Without Evidence**:
   - ❌ "It works", "tests pass", "files created"
   - ✅ Concrete evidence (output, test counts, file paths)

4. **Silent Failures**:
   - ❌ Quitting without error report when blocked
   - ✅ Report errors with diagnosis and recommendations

5. **Ambiguous File Paths**:
   - ❌ "communication.md" (where?)
   - ✅ "framework/policies/base/development/communication.md"

6. **Missing Verification**:
   - ❌ Claiming completion without proof
   - ✅ Show command output, test results, or validation checks

7. **Incomplete Status**:
   - ❌ "Done" (is it really? any caveats?)
   - ✅ "Complete. No known issues." or "Blocked on X. Y remains."

---

## 9 Evolution & Feedback

This policy evolves through:
- Agent feedback on reporting clarity and usefulness
- PA experience with work integration quality
- Discovery of new communication anti-patterns
- Specialist-specific adaptation needs

**Principle**: Communication serves integration. If reports don't help PA understand and integrate work → refine communication standards.

**Feedback Channels**:
- Report communication patterns that help or hinder
- Suggest specialist-specific template variations
- Document edge cases requiring special reporting
- Share examples of excellent or poor communication

---

**Policy Established**: Universal communication standards ensure all specialists report work systematically with code-first evidence-based communication, enabling PA orchestration and quality integration across all delegation types.

**Core Wisdom**: "Show code, not prose. Prove claims with evidence. Report completion systematically. Silent completion is a bug, not a feature. Communication enables integration."

**Remember**: Your completion report IS part of the deliverable. PA needs clear communication to understand your work, verify quality, and integrate results. This policy applies to **all specialists** regardless of role—communication is infrastructure for collaborative development.

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
