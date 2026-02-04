# MacEff Friction Points

Running log of deployment friction discovered during operations. Informs fixes and documentation improvements.

**Repositories**:
- MacEff: https://github.com/cversek/MacEff
- MannyMacEff: https://github.com/manny-dev-neurofieldz/MannyMacEff

---

## FP#1: Container Name Hardcoded in Scripts

**Date Discovered**: 2026-02-01

**Symptom**: SSH access scripts fail after version bump with "container not found"

**Root Cause**: Scripts hardcode container name instead of deriving dynamically

**Fix**: [MannyMacEff@8724cb2](https://github.com/manny-dev-neurofieldz/MannyMacEff/commit/8724cb2) - Dynamic detection via `docker compose ps` with fallback pattern matching

**Prevention**: All scripts should derive container name from docker-compose

---

## FP#2: SSH Keys Not Persisting After Rebuild

**Date Discovered**: 2026-01-30

**Symptom**: SSH access fails after container rebuild

**Root Cause**: SSH authorized_keys generated at runtime, not persisted to volume

**Workaround**: Re-run SSH setup after rebuild (`make setup-access`)

**Status**: Open - needs proper volume persistence

---

## FP#3: Search Service Timeout (Non-Fatal)

**Date Discovered**: 2026-01-29

**Symptom**: Policy search times out during startup

**Root Cause**: sqlite-vec index build on large policy corpus

**Impact**: Non-blocking - search works after warmup

**Status**: Open - consider lazy initialization

---

## FP#4: Python Version Mismatch (Host Mode)

**Date Discovered**: 2026-02-01

**Symptom**: `pip install -e .` fails on macOS system Python 3.9.6

**Root Cause**: macf_tools requires Python 3.10+, undocumented

**Fix**: [MacEff@fad957e](https://github.com/cversek/MacEff/commit/fad957e) - Added Host Mode Installation section to README with Homebrew/Conda instructions

---

## FP#5: PyYAML Missing from Dependencies

**Date Discovered**: 2026-02-01

**Symptom**: `ModuleNotFoundError: No module named 'yaml'` on virgin install

**Root Cause**: PyYAML in `[test]` extras only, but required for task YAML parsing

**Fix**: [MacEff@0593cc0](https://github.com/cversek/MacEff/commit/0593cc0) - Added to main dependencies in pyproject.toml

---

## FP#6: Stale Container Name in Config

**Date Discovered**: 2026-02-04

**Symptom**: `deploy.py install` fails "Container not running" despite container running

**Root Cause**: `.maceff/config.json` has hardcoded `container_name` that becomes stale after version bump

**Fix**: Manual update of config.json when bumping versions

**Prevention**: Single source of truth - derive from docker-compose.yml

---

## FP#7: Workspace Directory Ownership

**Date Discovered**: 2026-02-04

**Symptom**: Manual `git clone` into workspace fails "Permission denied"

**Root Cause**: `/workspace` created by root during container init

**Fix**: Use Named Agents declarative config (`projects.yaml`) instead of manual clone

**Prevention**: All project setup through `deploy.py install`

---

## Template

```markdown
## FP#N: Title

**Date Discovered**: YYYY-MM-DD

**Symptom**: What operator sees

**Root Cause**: Why it happens

**Fix**: [Repo@hash](URL) - Description (or "Status: Open")

**Prevention**: How to avoid
```
