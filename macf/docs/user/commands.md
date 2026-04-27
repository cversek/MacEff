# Hierarchical Command Namespaces

MacEff v0.3.2 introduces colon-separated command namespaces for better organization and discoverability.

## Namespace Structure

Commands follow the pattern: `/namespace:category:action`

**Example:**
```
/maceff:task:start <task_id>  # Start work on a tracked task
/maceff:roadmap:draft         # Draft a new roadmap
/maceff:ccp                   # Create consciousness checkpoint
```

## Available Namespaces

| Namespace | Owner | Purpose |
|-----------|-------|---------|
| `maceff:*` | Framework | Core MacEff functionality |
| `ctb:*` | ClaudeTheBuilder | Agent-specific commands |

## Command Categories

### maceff:task:*
Task management commands:
- `/maceff:task:start <task_id>` - Start work on a tracked task
- `/maceff:task:archive` - Archive completed task
- `/maceff:task:create_mission` - Create a MISSION task
- `/maceff:task:create_experiment` - Create an EXPERIMENT task
- `/maceff:task:create_phase` - Create a PHASE task
- `/maceff:task:create_detour` - Create a DETOUR task

### maceff:roadmap:*
Roadmap commands:
- `/maceff:roadmap:draft` - Draft a new roadmap

### maceff:* (top-level)
Core consciousness commands:
- `/maceff:ccp` - Create consciousness checkpoint
- `/maceff:jotewr` - Create JOTEWR reflection
- `/maceff:agent_bootstrap` - Bootstrap agent consciousness
- `/maceff:scholar_annotate` - Annotate with citations

## Filesystem Mapping

Commands map to nested directories:

```
.claude/commands/
├── maceff/
│   ├── ccp.md
│   ├── jotewr.md
│   ├── task/
│   │   ├── start.md
│   │   ├── archive.md
│   │   ├── create_mission.md
│   │   ├── create_experiment.md
│   │   ├── create_phase.md
│   │   └── create_detour.md
│   └── roadmap/
│       └── draft.md
└── ctb/
    ├── ccp.md
    └── gist.md
```

## Discovery

List available commands:
```bash
ls ~/.claude/commands/
```

Or use Claude Code's `/` autocomplete to explore available namespaces.

## Migration from Flat Commands

| Old (v0.3.1) | Current |
|--------------|---------|
| `/maceff_todos_start` | `/maceff:task:start <task_id>` |
| `/maceff_roadmap_draft` | `/maceff:roadmap:draft` |
| `/maceff_ccp` | `/maceff:ccp` |

**Note**: The `:todos:` namespace from v0.3.2 was renamed to `:task:` when the underlying TodoWrite-based workflow was supplanted by the persistent task system (see `framework/policies/sets/base/development/task_management.md`). If you used `/maceff:todos:start` in older sessions, switch to `/maceff:task:start <task_id>`.

The colon separator provides clearer hierarchy and enables namespace-based organization.
