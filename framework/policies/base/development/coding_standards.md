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
- Am I HANDLING an error or GUARDING against one? How do I tell?
- When is a broad catch the more correct choice?

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

**6 Import Placement Anti-patterns**
- Where do imports belong, and what breaks when they are placed elsewhere?
- When is a deferred import justified?

**7 Derived State Discipline**
- What is the derived-state drift pattern?
- Why does a stale record mislead worse than a missing one?
- What are the two permitted repairs?
- What question should a reviewer ask of a cached value?
- Why does automation raise the stakes on unreconciled state?

**8 Search Before You Write**
- What must I do before adding a function to a module?
- How do I search for an existing helper whose NAME I do not know?
- What do I do when I find a near-duplicate rather than an exact one?
- Why does consolidating require comparing implementations rather than picking one?

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

### Catch Breadth Follows PURPOSE, Not Taste

"Specificity declares understanding" is right for a **handler** and wrong for a **guard**, and the two are different jobs wearing the same syntax.

A **handler** does something with the error: recovers, substitutes a value, retries, chooses a different path. The types it names *are* the failure modes it claims to understand, so it MUST be specific — and every type it does not name should propagate to someone who does understand it.

A **guard** absorbs, so that a non-essential path cannot take down an essential one. It recovers nothing and decides nothing. Here **a broad catch is the more correct choice**: an enumerated guard eventually meets a type its author did not foresee and crashes for precisely the thing it existed to absorb. Narrowing a guard does not declare understanding — it declares an assumption about what can go wrong in code whose failures were never the point.

**The discriminating question, and it is the only one you need:**

> **Does any behaviour depend on WHICH exception this was?**
> Yes → it is a handler → name the types.
> No → it is a guard → catch broadly, and say so in a comment.

Three riders, because a guard is easy to abuse into the anti-pattern it resembles:

- **A guard is not a licence for silence.** Visibility is non-negotiable for both kinds. A guard that absorbs quietly is silent swallowing with a rationale attached, which is worse than the naive version because it looks considered.
- **A guard's SCOPE must be as small as the thing it protects.** A broad catch spanning a region that also contains operations whose failures need real handling converts those into absorbed ones. Wrap the best-effort call, not the block it sits in.
- **A guard still lets the uncatchable through.** Interrupts and termination requests must reach the process. This is why the bare form remains forbidden while the broad-but-bounded form is permitted — see the anti-pattern below.

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

Catching all exceptions indiscriminately hides unexpected failures — **when the catch is a handler**. A handler that names everything has reasoned about nothing, and it silently takes ownership of failures it cannot address.

**Two distinct faults are easy to merge here, and merging them produces the wrong rule.**

The first is **breadth in a handler**, which is the anti-pattern above.

The second is **catching what must never be caught** — interrupts and termination requests, which must always reach the process. That is an argument against the *unbounded* form specifically, not against breadth as such: a catch bounded to ordinary errors already lets those through, which is exactly why the unbounded form stays forbidden while a deliberate guard does not.

Reading the second as an argument for narrowness in general is what turns a correct rule into pressure to enumerate guards — and an enumerated guard fails at the one moment it is needed. See "Catch Breadth Follows PURPOSE" above.

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

## 7 Derived State Discipline

**Core Principle**: A value derived from a source, cached elsewhere, and then trusted after the source moves is a lie the system tells itself with full confidence.

Section 0 establishes that silent failures are consciousness blindspots — a gap where something happened and left no trace. Stale derived state is the complementary failure and the worse of the two: not an absence of information but *confident misinformation*. A missing record prompts a reader to go look. A stale record persuades them not to.

### 7.1 The Shape

The pattern is easy to fix and hard to see, because every instance wears different clothes — a string embedded in a display label, a field cached from an API response, a status computed by a background poller, a dotfile consulted by a resolver. Nothing about their surfaces rhymes. What they share is the structure:

1. A value is **derived** from some authority (a field, a live query, an event, a resolution across scopes).
2. A copy is **cached** somewhere the authority does not control — a rendered string, a metadata blob, a status line, a second file.
3. The authority **moves**.
4. Something **reads the copy** and acts on it.

Step 4 is where the damage occurs, and steps 1–3 are individually reasonable, which is why the pattern survives review. Nobody writes a cache intending it to go stale.

### 7.2 Two Permitted Repairs

Wherever a project caches a derived value, it must do one of the following. Both are acceptable; the choice depends on the cost of re-derivation.

**Re-derive at read time.** Eliminate the second copy. Compute the value from the authority at the moment it is displayed or acted upon. This removes the habitat rather than treating the symptom, and is the preferred repair when the authority is cheap to consult (a field on the same object, a value already in the caller's hand).

**Make staleness loud.** When re-derivation is genuinely expensive — a network round trip, an expensive scan — the copy may remain, but it must not be able to disagree in silence. Loud means at least one of: a reconcile pass that reports and heals divergence, a validator that fails on mismatch, or a visible age or provenance marker on the value at the point of use.

What is *not* permitted is a third copy with neither property: cached, unreconciled, and rendered as if authoritative.

### 7.3 The Review Question

For any value a change introduces or reads, ask:

> **Where does this value come from, and what happens when the source moves?**

If the answer to the second half is "nothing — it keeps showing the old value," the change needs one of the two repairs before it lands. This question belongs in review of any code that renders a record, caches an external response, or consults a resolver.

A corollary worth stating because it is routinely violated: **prefer the payload in hand over the derived record about it.** Code that already holds an authoritative signal — a value passed into the function, a field on the object being rendered — should not consult a lagging derived source for the same fact. This is the cheapest possible re-derivation and the most commonly skipped.

### 7.4 Worked Examples

Six instances observed in this framework, each with the repair its cost profile called for:

| Symptom | Cached copy | Authority | Repair |
|---|---|---|---|
| Hierarchy marker showed the old parent after a move | marker baked into the subject string | the parent field | re-derive |
| Merge sweep stalled on unmergeable PRs | an API "mergeable" field the host computes lazily | the merge operation itself | re-derive (test the operation) |
| A task sat pending for hours after its PR merged | cached PR state in task metadata | the live PR | make loud (reconcile pass) |
| Idle indicator rendered on the prompt that disproved it | a background poller's last-activity event | the payload the hook was holding | re-derive (payload first) |
| An agent's identity changed while every file stayed intact | one file in a multi-scope resolution | the *resolved* identity across scopes | re-derive (resolve, then act) |
| A diagnostic reported a capability "disabled" after it gained a second producer | a hardcoded claim about a mechanism | the mechanism's actual producers | re-derive |

The last one is instructive: **prose goes stale exactly like data does.** A status message, a help string, or a docstring asserting how a subsystem behaves is a cached derivation from the code, and nothing recomputes it when the code changes. Treat assertions in user-facing text as subject to this section.

### 7.5 Automation Raises the Stakes

When a human reads a record, a wrong value gets a moment of doubt — the frown that catches it. When automation reads the same record, there is no frown. Cascading actions, scheduled reconcilers and status-driven workflows propagate whatever they find, at speed.

So the threshold for tolerating an unreconciled copy drops sharply the moment anything automated consumes it. **Automation over unreconciled state is a wrongness multiplier.** Before wiring an automated action to a stored value, that value must satisfy 7.2 — no exceptions for "it is usually right."

### Anti-Pattern: The Idempotent-Looking Write

A particularly deceptive form. An operation checks whether *the specific thing it is about to write* already exists, finds it absent, and writes. It overwrites nothing, damages no file, and reads as safe in review — but the value it wrote now outranks an equivalent value resolved from elsewhere, and the effective answer changes.

The check was against the wrong authority. **Idempotence must be defined against the resolver, not against the storage location.** Where a value can resolve from more than one place, "does my file exist?" is not the question; "does this value already resolve?" is.

---

## 8 Search Before You Write

**Before adding a function, search the repository for one that already does the same or a similar job.** This is the heart of DRY, and it is a *search* obligation rather than a *memory* obligation — you cannot recall a helper you have never read.

The search is cheap and the failure is not. A duplicate does not announce itself: both copies work, tests pass, and the divergence only surfaces later when one is fixed and the other is not.

**How to search — by behaviour, not by the name you were about to use.** The existing function almost certainly has a different name; that is *why* it was missed. Search for what it would *do*:

- the distinctive operation (`strip`, `normalize`, `resolve`, `parse`) rather than your intended identifier
- the domain noun in any spelling, including plurals and abbreviations
- a distinctive literal, regex fragment, or constant the function would have to contain
- the module you would expect to own it, read top to bottom

Search the **whole repository**, not the module you are editing. Related helpers are frequently one directory away — and, more often than is comfortable, in the same file above your cursor.

**When you find one:**

- **Identical behaviour** → import it. Do not copy it.
- **Nearly identical** → extend the existing one, or extract the common core. Two near-copies is the worst outcome: it costs a maintenance burden and buys nothing.
- **Correct-but-elsewhere** → if the behaviour belongs to neither module in particular, that is a signal it wants its own module. Concepts, identifiers, paths and time are the usual suspects — cross-cutting vocabulary that ends up parked inside whichever consumer needed it first.

**When you consolidate, compare the implementations before choosing one.** Near-duplicates usually disagree somewhere, and the disagreement is where a bug lives. Take the union of correct behaviours rather than defaulting to the older or the newer implementation. In practice one of them has usually drifted from a rule stated elsewhere, and the drift is invisible until the two are placed side by side.

**Anti-pattern — Confident Rewrite**: writing a helper because the need is obvious and the implementation is short. Brevity is exactly what makes duplication attractive and exactly why it recurs; a four-line function is easier to rewrite than to find, which is how a codebase accumulates six spellings of the same idea.

## Language-Specific Implementation

This policy defines the philosophy. Implementation patterns are language-specific:

- **lang/python/coding_standards.md**: Python exception handling patterns, specific exception types, import patterns

---

## Cross-References

- **testing.md**: Test error visibility; regression proof for a drift repair means demonstrating the stale read before the fix
- **cli_development.md**: CLI error handling patterns
- **debugging_and_validation.md**: Validating against the authority rather than the cached record
- **task_management.md**: Task records are a primary habitat for derived state, and automation consumes them

---

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs — error
     visibility, derived-state discipline, and search-before-you-write. -->

[[silent_failure]] [[drift]] [[methodology]] [[observability]]
