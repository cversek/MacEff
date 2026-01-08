# Hierarchical Command Namespaces

MacEff v0.3.2 introduces colon-separated command namespaces for better organization and discoverability.

## Namespace Structure

Commands follow the pattern: `/namespace:category:action`

**Example:**
```
/maceff:todos:start      # Start work on a TODO item
/maceff:roadmap:draft    # Draft a new roadmap
/maceff:ccp              # Create consciousness checkpoint
```

## Available Namespaces

| Namespace | Owner | Purpose |
|-----------|-------|---------|
| `maceff:*` | Framework | Core MacEff functionality |
| `ctb:*` | ClaudeTheBuilder | Agent-specific commands |

## Command Categories

### maceff:todos:*
TODO management commands:
- `/maceff:todos:start` - Start work on a TODO item
- `/maceff:todos:archive` - Archive completed work
- `/maceff:todos:backup` - Backup TODO state

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
│   ├── todos/
│   │   ├── start.md
│   │   ├── archive.md
│   │   └── backup.md
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

| Old (v0.3.1) | New (v0.3.2) |
|--------------|--------------|
| `/maceff_todos_start` | `/maceff:todos:start` |
| `/maceff_roadmap_draft` | `/maceff:roadmap:draft` |
| `/maceff_ccp` | `/maceff:ccp` |

The colon separator provides clearer hierarchy and enables namespace-based organization.
