# DETOUR: Path Finding Disambiguation - COMPLETED

**Archived**: 2025-12-24 01:20 AM EST
**Status**: COMPLETED
**Breadcrumb**: s_1b969d39/c_308/g_1cdf3a4

---

## Archived TODO Hierarchy

```
↪️ DETOUR: Path Finding Disambiguation [detours/2025-12-24_Path_Finding_Disambiguation.md]
  ✅ D.1: Define new functions [s_1b969d39/c_308/g_c03b6a6/p_69414ce1/t_1766555335]
     - find_maceff_root(): MacEff installation location
     - find_project_root(): Claude project workspace
     - find_agent_home(): Agent's sacred home (persists across projects)
     - 11 tests added in test_paths.py
  ✅ D.2: Migrate call sites [s_1b969d39/c_308]
     - manifest.py → find_maceff_root (framework policies)
     - cycles.py → find_agent_home (agent config)
     - agent_events_log.py → find_agent_home (SACRED!)
     - recovery.py → find_maceff_root (recovery policies)
     - cli.py → find_agent_home (agent init)
     - utils/__init__.py → exports added
  ✅ D.3: Update container setup [s_1b969d39/c_308/g_1cdf3a4]
     - Added MACEFF_AGENT_HOME_DIR=$HOME to start.py bash_init
```

---

## Commits

- `b400eb2`: feat(paths): three-way path semantics - DETOUR D.1 + D.2
- `1cdf3a4`: feat(container): add MACEFF_AGENT_HOME_DIR env var

---

## Key Achievement

**Agent continuity is SACRED** - Event log now persists at `{MACEFF_AGENT_HOME_DIR}/.maceff/agent_events_log.jsonl` across project reassignments.

---

**End Archive**
