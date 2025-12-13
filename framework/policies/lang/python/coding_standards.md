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
- Why avoid `except Exception:`?

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

---

## 0 Exception Type Selection

### Never: Bare except

```python
# FORBIDDEN - catches KeyboardInterrupt, SystemExit (PEP 8 violation)
except:
    pass
```

### Avoid: Generic Exception

```python
# AVOID - hides unexpected failures
except Exception:
    pass
```

### Required: Specific Types

```python
# CORRECT - declares understanding of failure modes
except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
    # handle with visibility
```

---

## 1 Stderr Warning Pattern

### Standard Pattern

```python
except SpecificError as e:
    import sys
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
except Exception as e:
    import sys
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
# CORRECT
except FileNotFoundError as e:
    import sys
    print(f"⚠️ MACF: File not found (using None): {e}", file=sys.stderr)
    return None
```

---

## Cross-References

- **base/development/coding_standards.md**: Philosophy and principles
- **base/development/testing.md**: Testing error visibility
- **base/development/cli_development.md**: CLI patterns
