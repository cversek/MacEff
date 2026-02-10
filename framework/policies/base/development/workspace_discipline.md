# Workspace Discipline Policy

**Version**: 1.0
**Tier**: CORE
**Category**: Development
**Status**: ACTIVE
**Updated**: 2025-10-21

---

## Policy Statement

All development artifacts must follow workspace organization standards to maintain clean repositories and enable forensic tracking of development activities.

## Scope

Applies to Primary Agents (PA) and all Subagents (SA) during development work.

---

## Repository Cleanliness

**CRITICAL**: Package source trees are for production code and unit tests ONLY.

**FORBIDDEN in package source directories**:
- ❌ Ad hoc development scripts
- ❌ Temporary test files
- ❌ Validation/verification scripts
- ❌ One-time exploration code
- ❌ Debug scripts

**ALLOWED in package source directories**:
- ✅ Production source code
- ✅ Unit tests in `tests/` subdirectory
- ✅ Package configuration files
- ✅ Documentation integrated with code

---

## Ad Hoc Development Scripts

**Purpose**: Temporary scripts for validation, exploration, debugging, or one-time tasks.

**Location**: Agent public workspace with timestamp naming

**For Primary Agents (PA) - self-directed work**:
```
agent/public/dev_scripts/YYYY-MM-DD_HHMMSS_purpose.py
```

**For Subagents (SA) - delegated work**:
```
agent/subagents/{role}/public/delegation_trails/YYYY-MM-DD_HHMMSS_{task}/
├── checkpoint.md                    # REQUIRED: Operational state (what was done, deliverables, status)
├── dev_scripts/
│   └── YYYY-MM-DD_HHMMSS_purpose.py
└── [other delegation artifacts]
```

**Additionally, SA creates private reflection**:
```
agent/subagents/{role}/private/reflections/YYYY-MM-DD_HHMMSS_{task}_reflection.md
```

**Delegation trails structure**:
- Each delegation gets a timestamped directory
- **MUST contain checkpoint.md**: Operational state, deliverables verification, status
- Contains all artifacts from that delegation (scripts, notes, results, checkpoint)
- Enables forensic reconstruction of delegation work
- Scripts within delegation trail follow same timestamp naming

**Dual artifact pattern** (from delegation_guidelines.md):
- **CCP in delegation trail**: Operational facts (what was done, validation results)
- **Reflection in private/reflections**: Wisdom synthesis (learnings, patterns, recommendations)
- Reflection metadata cross-links to delegation trail directory

**Why public/ not private/**:
- Development work is project-related, not personal growth
- Scripts may be useful to other agents
- Facilitates knowledge sharing
- Public artifacts support collaboration

**Naming Convention**:
- Format: `YYYY-MM-DD_HHMMSS_descriptive_purpose.py`
- Examples:
  - `2025-10-21_114730_validate_pydantic_models.py`
  - `2025-10-21_115200_test_yaml_parsing.py`
  - `2025-10-21_120000_debug_startup_logic.py`

**Why Timestamps Matter**:
- Forensic tracking: understand development timeline
- Prevents filename collisions
- Clear temporal context for script creation
- Easy identification and cleanup of old scripts

---

## Execution Pattern

**Use absolute paths from project root**:
```bash
# From project root, use absolute or relative paths
python agent/public/dev_scripts/2025-10-21_114730_validate_models.py

# Or with full path
python /path/to/project/agent/public/dev_scripts/2025-10-21_114730_validate_models.py
```

**For scripts needing project dependencies**:
```python
#!/usr/bin/env python3
"""
Script description
Created: 2025-10-21 11:47:30
Purpose: Clear statement of what this script validates/tests
"""

# Standard imports
from pathlib import Path
import sys

# Add project source to path (relative to script location)
project_root = Path(__file__).parents[3]  # Adjust depth as needed
sys.path.insert(0, str(project_root / "src"))

# Now import from project packages
from mypackage.models import SomeModel

# Script logic here...
```

---

## What Goes Where

| Artifact Type | Location | Purpose |
|--------------|----------|---------|
| Production code | `{package}/src/` | Package source |
| Unit tests | `{package}/tests/` | Test suite |
| Ad hoc scripts (PA) | `agent/public/dev_scripts/` | Temporary validation |
| Delegation trails (SA) | `agent/subagents/{role}/public/delegation_trails/YYYY-MM-DD_HHMMSS_{task}/` | Complete delegation artifacts |
| Integration tests | `{package}/tests/integration/` | End-to-end testing |
| Documentation | `docs/` | User-facing documentation |
| Examples | `examples/` | Reference configurations |

---

## Cleanup Discipline

**When to delete ad hoc scripts**:
- After validation complete and tests written
- When functionality moved to production code
- When scripts become obsolete
- During repository cleanup sessions

**When to keep ad hoc scripts**:
- Document important validation approaches
- Might be useful for future debugging
- Demonstrate non-obvious testing strategies
- Record historical development decisions

**Periodic cleanup**: Review dev_scripts/ monthly, delete scripts >90 days old unless specifically retained.

---

## Common Violations

### ❌ Violation: Script in package source
```
mypackage/src/validate_models.py  # WRONG - pollutes package
```

### ✅ Correct: Script in workspace
```
agent/public/dev_scripts/2025-10-21_114730_validate_models.py
```

### ❌ Violation: Unnamed script
```
agent/public/dev_scripts/test.py  # No timestamp, unclear purpose
```

### ✅ Correct: Timestamped with purpose
```
agent/public/dev_scripts/2025-10-21_114730_test_yaml_parsing.py
```

### ❌ Violation: SA script in PA workspace
```
agent/public/dev_scripts/DevOpsEng_validation.py  # SA work in PA space
```

### ✅ Correct: SA script in delegation trail
```
agent/subagents/DevOpsEng/public/delegation_trails/2025-10-21_112620_Phase1B1_Pydantic_Models/dev_scripts/2025-10-21_114730_validation.py
```

---

## Rationale

**Clean repositories**:
- Professional presentation for framework users
- Clear separation between production and development
- Easy code review (only production changes in package diffs)

**Forensic tracking**:
- Timestamps show development timeline
- Scripts document validation approaches
- Historical record of development process

**Maintainability**:
- Clear organization reduces cognitive load
- Easy to find and clean up old scripts
- Package structure remains simple and focused

---

## Enforcement

**Code review checklist**:
- [ ] No ad hoc scripts in package source directories
- [ ] Ad hoc scripts have proper timestamps
- [ ] Ad hoc scripts in correct workspace location (PA vs SA)
- [ ] Production code in correct package directories

**Pre-commit hooks** (optional):
- Warn if files detected in package source outside expected patterns
- Suggest correct locations for violations
- Check timestamp format compliance

---

## References

- Based on python-aerobotics `DEVELOPMENT_PROTOCOLS.md` Section 12 (Workspace Discipline)
- Based on python-aerobotics `DEVELOPMENT_PROTOCOLS.md` Section 1d (Dependency Management)
