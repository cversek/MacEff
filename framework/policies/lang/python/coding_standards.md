# Python Coding Standards

**Version**: 1.0
**Tier**: LANG
**Category**: Python
**Status**: ACTIVE
**Updated**: 2025-12-13
**Parent**: base/development/coding_standards.md

---

## Policy Statement

Python-specific implementation patterns for the Error Visibility Stance defined in the base coding standards policy.

## Scope

Applies to all Python code written within MacEff framework projects.

---

## CEP Navigation Guide

**0 Exception Type Selection**
- What exception types should I catch?
- Why avoid bare `except:`?
- When is `except Exception:` wrong, and when is it the correct choice?
- How do I write a guard rather than a handler?

**1 Stderr Warning Pattern**
- How do I warn to stderr in Python?
- What is the standard message format?

**2 Event Logging Pattern**
- How do I log to the event system?
- What if event logging fails?

**3 Common Exception Types**
- File operations?
- JSON parsing?
- Subprocess calls?
- Network/socket operations?

**5 Path Resolution in Python**
- What is the `.parent` chain anti-pattern?
- When is single `.parent` acceptable?
- What MACF discovery functions exist?

**6 Reading the Event Log**
- Why is a hardcoded `limit=` on an event scan a smell?
- What unit should a scan be bounded in?
- When is an unbounded scan the cheaper choice?
- How do I keep "not found" from becoming a claim about state?

---

## 0 Exception Type Selection

### Never: Bare except

```python
# FORBIDDEN - catches KeyboardInterrupt, SystemExit (PEP 8 violation)
except:
    pass
```

### Avoid in a HANDLER: Generic Exception

```python
# AVOID - a handler this broad has reasoned about nothing
except Exception:
    pass
```

Note what is wrong with that example: **both** the breadth and the `pass`. They are separable faults, and the `pass` is the worse one — it is silent swallowing, forbidden everywhere regardless of breadth.

### Required in a HANDLER: Specific Types

```python
# CORRECT - declares understanding of failure modes
except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
    # handle with visibility
```

### Correct in a GUARD: Generic Exception, Announced

A guard exists so a best-effort path cannot take down an essential one. It
recovers nothing, so nothing depends on which exception occurred — and an
enumerated guard eventually meets a type its author did not foresee and crashes
for exactly the thing it was protecting against.

```python
# CORRECT - a guard, and it says so
try:
    send_optional_notification(text)
except Exception as e:
    # Deliberately broad: this is a GUARD, not a handler. Notification is
    # best-effort and must never take down the caller.
    print(f"⚠️ MACF: notification failed (continuing): {e}", file=sys.stderr)
```

`except Exception` does not catch `KeyboardInterrupt` or `SystemExit`, which
derive from `BaseException`. That is precisely why this form is permitted and
the bare form is not: interrupts and termination still reach the process.

**Wrap the best-effort call, not the block containing it.** A guard whose scope
creeps to cover neighbouring operations converts their real failures into
absorbed ones.

The discriminating question is in the base policy — `macf_tools policy navigate
coding_standards`, "Catch Breadth Follows PURPOSE": *does any behaviour depend on
WHICH exception this was?*

---

## 1 Stderr Warning Pattern

### Standard Pattern

```python
import sys  # Module-level import REQUIRED

# ...later in code...
except SpecificError as e:
    print(f"⚠️ MACF: {operation} failed ({fallback}): {e}", file=sys.stderr)
    return fallback_value
```

### Message Format

- Prefix: `⚠️ MACF:` (identifies source)
- Operation: What was attempted
- Fallback: What alternative was taken (in parentheses)
- Error: The exception message

Example: `⚠️ MACF: Config read failed (using default): [Errno 2] No such file`

---

## 2 Event Logging Pattern

### Critical Operations

```python
import sys  # Module-level import REQUIRED

# ...later in code...
except Exception as e:
    print(f"⚠️ MACF: {operation} failed: {e}", file=sys.stderr)
    try:
        from macf.agent_events_log import append_event
        append_event("error", {
            "source": "module.function_name",
            "error": str(e),
            "error_type": type(e).__name__,
            "fallback": "description_of_fallback"
        })
    except Exception as log_e:
        print(f"⚠️ MACF: Event logging also failed: {log_e}", file=sys.stderr)
```

### Key Points

- Always warn to stderr BEFORE attempting event log
- Catch event logging failures separately
- If event logging fails, warn about that too (NEVER SILENT)

---

## 3 Common Exception Types

### File Operations

```python
except (FileNotFoundError, PermissionError, OSError) as e:
```

### JSON Parsing

```python
except (json.JSONDecodeError, KeyError, TypeError) as e:
```

### Subprocess/Commands

```python
except (subprocess.CalledProcessError, OSError, FileNotFoundError) as e:
```

### Network/Socket

```python
except (socket.error, OSError, ConnectionError) as e:
```

### Config Loading

```python
except (ImportError, OSError, KeyError) as e:
```

### Directory Creation

```python
except OSError as e:
```

---

## 4 Warn + Reraise Pattern (Utility Functions)

### Implementation

```python
def read_json(path: Path) -> dict:
    """Utility function with warn + reraise pattern."""
    import sys
    try:
        if not path.exists():
            print(f"⚠️ MACF: JSON file not found ({path.name})", file=sys.stderr)
            raise FileNotFoundError(f"JSON file not found: {path}")
        with open(path, 'r') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ MACF: JSON read failed ({path.name}): {e}", file=sys.stderr)
        raise  # Caller decides fallback
```

### Caller Pattern

```python
# Caller wraps with try/except and provides fallback
try:
    data = read_json(config_path)
except (FileNotFoundError, OSError, json.JSONDecodeError):
    data = {}  # Caller's explicit fallback decision
```

---

## 5 Path Resolution in Python

### The `.parent` Chain Anti-pattern

```python
# FRAGILE - hardcodes directory structure
base_dir = Path(__file__).parent.parent.parent
hooks_dir = Path(__file__).parent.parent.parent / '.claude' / 'hooks'

# ROBUST - uses discovery
from macf.utils import find_project_root
project_root = find_project_root()
hooks_dir = project_root / '.claude' / 'hooks'
```

### Why This Matters

The `.parent` chain pattern caused 9 integration tests to silently skip for months:
- Test file at: `macf/tests/integration/test_hook_execution.py`
- Expected: `parent.parent.parent` → project root
- Actual: `parent.parent.parent` → `macf/` (one level too deep)
- Result: Tests skipped, hooks never validated

### MACF Discovery Functions

```python
from macf.utils import find_project_root, get_session_dir, get_hooks_dir

# Project root with multi-priority detection
project_root = find_project_root()

# Session-scoped directories
session_dir = get_session_dir(session_id)
hooks_log_dir = get_hooks_dir(session_id)
```

### When `.parent` Is Acceptable

Single `.parent` for sibling file access within same package is acceptable:

```python
# OK - accessing sibling in same directory
sibling_path = Path(__file__).parent / "config.json"

# NOT OK - navigating up multiple levels
project_root = Path(__file__).parent.parent.parent  # FRAGILE
```

---

## 6 Reading the Event Log

Section 2 covers writing to the event log. This covers reading it back, where the
recurring defect is not the read but what a *failed* read is taken to mean.

### 6.1 A hardcoded `limit=` on an event scan is a smell

```python
# Suspect
for event in read_events(limit=200, reverse=True):
    if event.get("event") == "user_activity_detected":
        return event["timestamp"]
return None          # "no activity" — or "I stopped looking"?
```

The scan is bounded in **rows** while the question is about **time**. Every
unrelated write consumes the budget, so the window silently shrinks as the log
gets busy — and the miss is returned as a value indistinguishable from a real
negative. See the compiled-false-absence trap in `empiricism` for why this is a
distinct failure from an ordinary bad search.

### 6.2 Prefer no bound when the scan exits on its first match

Most of these scans `return` or `break` as soon as they find what they came for.
Such a scan **already costs nothing in the common case** — the limit only ever
takes effect when the event is absent, which is exactly the case it gets wrong.

```python
# Better: self-limiting on match, honest when absent
for event in read_events(limit=None, reverse=True):
    if event.get("event") == "mode_change":
        return event["data"].get("enabled", True)
return False
```

### 6.3 When a bound is genuinely needed, bound in the unit you are measuring

If the question is *did X happen in the last N minutes*, stop at the first event
older than N minutes. An age cannot be shrunk by volume, and the loop still
terminates early on a busy log:

```python
def had_activity_since(cutoff_epoch):
    for event in read_events(limit=None, reverse=True):
        ts = parse_epoch(event.get("timestamp"))
        if ts is not None and ts < cutoff_epoch:
            return False        # reverse order: everything beyond is older
        if event.get("event") == "user_activity_detected":
            return True
    return False
```

Reframing the question is often the whole fix. *When did X last happen* must
reach an event of unbounded age; *did X happen since T* only ever has to reach
T.

The third category — lifetime state, scanned until found — still degrades when
the event has **never** occurred, since the scan then reads the whole log. A row
limit cannot fix that; it answers wrongly rather than slowly. The structural
remedy is to remove the category: cycle-scope every query and require
cross-cycle state to re-assert itself at the boundary, so the worst case is one
cycle regardless of how long the log grows. That also makes a miss mean exactly
one thing — *not established this cycle* — which is what dissolves the compiled
false absence rather than merely bounding it.

### 6.4 Do not let `None`-is-falsy encode a decision

```python
# The default is invisible — it falls out of Python's truthiness
last = lookup()
if last and (now - last) > timeout:
    mark_idle()
```

Make the fallback explicit at the call site — a sentinel the caller must handle,
or the default passed as a parameter. Where a default must be chosen, choose by
**cost of being wrong**: a default that grants *care* is cheap; one that grants
*authority*, or silently withdraws a safeguard, is not.

### 6.5 Anti-pattern summary

| smell | why | instead |
|---|---|---|
| `read_events(limit=<int literal>)` | bounded in rows, question is in time | `limit=None`, or bound by age |
| `return None` / `return False` on miss | conflates absent with unreachable | sentinel, or explicit parameter |
| caller relies on falsiness | the default is invisible | state the fallback where it is chosen |

This is enforced twice: **MACEFF006** flags a hardcoded numeric `limit=` on an
event scan in this tree, and `read_events` raises a `DeprecationWarning` at
runtime for callers the linter never runs against. A genuinely justified one stays possible — suppress it at the site with
`# noqa: MACEFF006 - <reason>`, the way other exceptions are recorded. The point
is that the choice becomes visible and auditable, not that it is forbidden.

## Anti-Pattern Examples

### Silent Pass

```python
# FORBIDDEN
except FileNotFoundError:
    pass  # No evidence this happened
```

### Silent Return

```python
# FORBIDDEN
except Exception:
    return None  # Where did the error go?
```

### Correct Alternative

```python
import sys  # Module-level import REQUIRED

# ...later in code...
# CORRECT
except FileNotFoundError as e:
    print(f"⚠️ MACF: File not found (using None): {e}", file=sys.stderr)
    return None
```

---


---

## Cross-References

- **base/development/coding_standards.md**: Philosophy and principles
- **base/development/testing.md**: Testing error visibility
- **base/development/cli_development.md**: CLI patterns

---

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs — Python
     expression of the error-visibility discipline. -->

[[silent_failure]] [[methodology]] [[tooling]]
