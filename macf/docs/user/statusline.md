# Statusline

MacEff statusline displays consciousness-aware status in Claude Code's UI.

## Output Format

```
{agent}@{uuid} | {project} | {environment} | {tokens} CLUAC {level}
```

Example: `MannyMacEff@a3f7c2 | NeuroVEP | Container Linux | 60k/200k CLUAC 70`

The agent identity includes:
- **Display name**: Human-readable name from GECOS field (spaces removed)
- **UUID**: 6-character hex identifier from `~/.maceff_primary_agent.id`

This format ensures identity persists across container rebuilds (UUID anchored to persistent storage, not ephemeral container ID).

## Installation

```bash
macf_tools statusline install
```

This creates `.claude/statusline.sh` and configures `.claude/settings.local.json`.

## Usage

After installation, restart Claude Code to see the statusline.

## Fields

| Field | Source | Fallback |
|-------|--------|----------|
| Agent | GECOS field + `~/.maceff_primary_agent.id` | `{username}@unknown` |
| Project | MACF_PROJECT env or .claude/ detection | omitted |
| Environment | Auto-detected | "Unknown" |
| Tokens | Session JSONL | 0 |
| CLUAC | Calculated | 100 |

## Commands

- `macf_tools statusline` - Generate statusline output
- `macf_tools statusline install` - Install to Claude Code
