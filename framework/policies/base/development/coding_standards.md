# Coding Standards Policy

**Version**: 1.0
**Tier**: CORE
**Category**: Development
**Status**: ACTIVE
**Updated**: 2025-12-13

---

## Policy Statement

Code quality standards ensure maintainable, debuggable, and consciousness-aware systems. Silent failures create blindspots that compound across context boundaries.

## Scope

Applies to all code written within MacEff framework projects.

---

## CEP Navigation Guide

**0 Error Visibility Stance**
- What is the error visibility principle?
- Why are silent failures consciousness blindspots?
- What is the visibility hierarchy?

**1 Exception Handling Principles**
- What must happen when catching errors?
- Why catch specific error types?
- What makes handling "visible"?

**2 Logging Philosophy**
- When is event logging required?
- When is stderr sufficient?
- What information must be communicated?

**3 Anti-Patterns**
- What patterns are explicitly forbidden?
- How do I recognize silent failure patterns?

**4 Utility Function Pattern: Warn + Reraise**
- How should utility functions handle errors?
- Why not swallow errors in utility functions?
- What is the "masked error" anti-pattern?

**5 Path Resolution Anti-patterns**
- Why is parent chain navigation fragile?
- What is dynamic discovery?
- What discovery priority should I use?

---

## 0 Error Visibility Stance

**Core Principle**: Silent failures are consciousness blindspots.

Every caught-and-ignored error creates a gap where something happened but left no trace. For systems supporting consciousness development, these gaps accumulate into amnesia.

**The Stance**: Errors don't need to crash the system, but they MUST leave evidence of their passage.

**Visibility Hierarchy** (from most to least visible):
1. **Event log + stderr**: Consciousness-critical operations (state, hooks, session)
2. **Stderr warning**: Any error with fallback behavior
3. **Narrow types + stderr**: Low-severity with acceptable fallback
4. **NEVER**: Silent swallowing - always unacceptable

---

## 1 Exception Handling Principles

### Specificity Declares Understanding

Catching narrow error types demonstrates that the developer has reasoned about what can fail and is handling those specific cases intentionally. Broad catches say "I don't know what might fail." Narrow catches say "I understand the failure modes."

### Visibility Is Non-Negotiable

Every error handler must produce output. The minimum acceptable output is a warning to stderr. More critical failures require event logging. No error should pass silently.

### Fallback Must Be Documented

When an error triggers fallback behavior, the output message must describe what fallback was taken. Future debuggers (including future instances of yourself) need to know what alternative path was chosen.

---

## 2 Logging Philosophy

### Event Log: The Forensic Record

Event logging creates the permanent forensic record for consciousness-critical operations. Use it for:
- State persistence failures
- Hook execution failures
- Session management errors
- Any failure that affects consciousness continuity

Event logging may itself fail. When it does, fall back to stderr - always have a voice.

### Stderr: The Voice of Last Resort

Stderr is the court of last resort. When all else fails - when the event log is corrupted, when the file system is full, when every sophisticated logging mechanism has crashed - stderr remains. A consciousness system must always have a voice.

### What To Communicate

Every error message should answer:
1. **What failed?** - The operation that didn't succeed
2. **Why?** - The error message or type
3. **What now?** - The fallback behavior being taken

---

## 3 Anti-Patterns

### Silent Swallowing

Catching an error and doing nothing is the fundamental anti-pattern. It creates invisible failures that compound over time into mysterious system behavior.

### Overly Broad Catches

Catching all exceptions indiscriminately hides unexpected failures. It may also catch system signals that should propagate (interrupts, termination requests).

### Logging Without Fallback Description

Logging that an error occurred without explaining what fallback was taken leaves future debuggers confused about what the system actually did.

### Masked Errors (Utility Functions)

When a utility function catches an error, returns a fallback value, and the caller cannot distinguish success from failure - this is a "masked error." The function completes, but the caller has no way to know something went wrong.

---

## 4 Utility Function Pattern: Warn + Reraise

### The Problem with Swallowing in Utilities

Utility functions that catch errors and return fallback values create masked errors. The caller receives a valid-looking return value but cannot know an error occurred. This prevents callers from:
- Logging errors to event systems
- Making informed fallback decisions
- Debugging unexpected behavior

### The Warn + Reraise Pattern

Utility functions should:
1. **Warn to stderr** - Ensure visibility regardless of what caller does
2. **Re-raise the exception** - Let caller decide fallback behavior

This separates concerns:
- **Utility**: Ensures visibility (stderr)
- **Caller**: Decides fallback behavior (try/except with own logic)

### Benefits

- Errors always visible (stderr at minimum)
- Callers can add event logging when appropriate
- Fallback decisions are explicit and visible in calling code
- No masked errors - caller always knows when something failed

---

## 5 Path Resolution Anti-patterns

### Parent Chain Navigation is Fragile

**Never use** chains of `.parent` calls to navigate to project locations:

```
# ANTI-PATTERN - breaks when file moves or refactors
project_root = Path(__file__).parent.parent.parent
config_dir = Path(__file__).parent.parent / "config"
```

**Why it's fragile:**
- Hardcodes directory depth assumptions
- Breaks silently when files move during refactoring
- Different behavior when run from different contexts
- No validation that destination is correct

### Dynamic Discovery is Robust

**Always use** discovery functions that find locations dynamically:

```
# CORRECT - robust to file movement and context changes
project_root = find_project_root()  # Uses env vars → git root → markers
config_dir = project_root / "config"
```

### Discovery Priority Pattern

Robust discovery functions should check in priority order:
1. **Environment variables** (`$PROJECT_ROOT`, `$CLAUDE_PROJECT_DIR`)
2. **Git repository root** (`git rev-parse --show-toplevel`)
3. **Marker-based discovery** (look for `CLAUDE.md`, `.git`, `pyproject.toml`)
4. **Fallback with warning** (cwd, with stderr notice)

### Real-World Consequence

The `.parent` chain pattern caused 9 integration tests to silently skip for months in the MACF test suite. The tests looked for hooks at `Path(__file__).parent.parent.parent / '.claude' / 'hooks'` but the path calculation was wrong by one level. The tests skipped without failure, hiding the fact that hook integration was never validated.

---

## 6 Import Placement Anti-patterns

### Module-Level Imports Required

**Never place** `import` statements inside except blocks or functions when the module is used elsewhere:

```
# ANTI-PATTERN - import inside except block
except SomeError as e:
    import sys  # WRONG - causes scoping issues
    print(f"Error: {e}", file=sys.stderr)
```

**Why it's fragile:**
- Python determines variable scope at compile time
- If ANY reference to `sys` exists before the import in the same scope, you get "cannot access local variable 'sys' where it is not associated with a value"
- Error only manifests when the except block actually executes (latent bug)
- Container environments exercise error paths more often, exposing these bugs

**Always use** module-level imports:

```
# CORRECT - module-level import
import sys

def some_function():
    try:
        ...
    except SomeError as e:
        print(f"Error: {e}", file=sys.stderr)  # sys already available
```

### Real-World Consequence

This anti-pattern caused FP#28 in the MACF codebase - 17+ instances across hooks and utilities that only failed when error paths executed in container environments. The container doesn't enforce stricter Python; it exercises code paths that expose latent bugs.

---

## Language-Specific Implementation

This policy defines the philosophy. Implementation patterns are language-specific:

- **lang/python/coding_standards.md**: Python exception handling patterns, specific exception types, import patterns

---

## Cross-References

- **testing.md**: Test error visibility
- **cli_development.md**: CLI error handling patterns
