#!/usr/bin/env python3
"""Pre-commit check: detect silent exception swallowing in Python files.

Catches:
  1. except Exception:          — bare catch, no binding
  2. except:                    — bare catch, no type
  3. except BaseException:      — too broad, no binding
  4. except ... as <var>:       — bound but <var> never used in except body

A catch in 1-3 whose body ends by re-raising is not silent and is not flagged:
cleaning up a partial write under `except BaseException:` and then `raise` is
the idiom for undoing it whatever interrupted it, KeyboardInterrupt included.

Exit 0 if clean, exit 1 with details if violations found.
"""
import re
import sys
import textwrap


def _ends_by_raising(lines: list, start: int, except_indent: int) -> bool:
    """Whether the handler whose body starts at lines[start] ends with a raise.

    Only the last statement at the body's own level counts. A raise nested
    under a condition leaves the other path falling through silently.
    """
    body_indent = None
    last = None
    for text in lines[start:]:
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(text) - len(text.lstrip())
        if indent <= except_indent:
            break
        if body_indent is None:
            body_indent = indent
        if indent == body_indent:
            last = stripped
    return last is not None and re.match(r"raise\b", last) is not None


def check_file(filepath: str) -> list:
    """Check a single file for silent exception anti-patterns.

    Returns list of (line_number, line_text, reason) tuples.
    """
    violations = []
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return violations

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Pattern 1-3: bare except without 'as' binding
        # except Exception:  |  except:  |  except BaseException:
        if re.match(r'^except\s*(Exception|BaseException)?\s*:', stripped):
            if ' as ' not in stripped:
                except_indent = len(line) - len(line.lstrip())
                if _ends_by_raising(lines, i, except_indent):
                    continue
                reason = "bare catch without binding"
                violations.append((i, stripped, reason))
                continue

        # Pattern 4: except ... as <var>: where <var> is never used
        m = re.match(r'^except\s+.*\s+as\s+(\w+)\s*:', stripped)
        if m:
            var_name = m.group(1)
            # Determine the indentation of the except line
            except_indent = len(line) - len(line.lstrip())

            # Scan the except body (lines with deeper indentation)
            var_used = False
            for j in range(i, len(lines)):  # i is already 1-indexed, lines[i] is next line
                body_line = lines[j]
                if not body_line.strip():
                    continue  # skip blank lines
                body_indent = len(body_line) - len(body_line.lstrip())
                if body_indent <= except_indent and body_line.strip():
                    break  # dedented — left the except body
                # Check if var_name appears as a word (not part of another identifier)
                if re.search(r'\b' + re.escape(var_name) + r'\b', body_line):
                    var_used = True
                    break

            if not var_used:
                reason = f"'{var_name}' bound but never used in except body"
                violations.append((i, stripped, reason))

    return violations


def main():
    if len(sys.argv) < 2:
        print("Usage: check_silent_exceptions.py <file1.py> [file2.py ...]")
        sys.exit(2)

    all_violations = {}
    for filepath in sys.argv[1:]:
        violations = check_file(filepath)
        if violations:
            all_violations[filepath] = violations

    if not all_violations:
        sys.exit(0)

    print("\033[0;31m========================================\033[0m")
    print("\033[0;31mBLOCKED: silent exception anti-pattern detected\033[0m")
    print("\033[0;31m========================================\033[0m")
    print()

    for filepath, violations in all_violations.items():
        for line_no, line_text, reason in violations:
            print(f"  {filepath}:{line_no}: {reason}")
            print(f"    {line_text}")
        print()

    print(textwrap.dedent("""\
    Fix: use specific exception types, bind with 'as e', and log:

      # BAD:   except Exception:
      #           pass
      # BAD:   except Exception as e:
      #           pass    # e is never used!
      # GOOD:  except (OSError, ValueError) as e:
      #           print(f"⚠️ MACF: context: {e}", file=sys.stderr)
    """))
    sys.exit(1)


if __name__ == "__main__":
    main()
