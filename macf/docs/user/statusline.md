# Statusline

MacEff statusline displays consciousness-aware status in Claude Code's UI.

## Output Format

```
{agent} | {project} | {environment} | {tokens} CLUAC {level}
```

Example: `manny | NeuroVEP | Container Linux | 60k/200k CLUAC 70`

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
| Agent | .maceff/config.json | "unknown" |
| Project | MACF_PROJECT env or .claude/ detection | omitted |
| Environment | Auto-detected | "Unknown" |
| Tokens | Session JSONL | 0 |
| CLUAC | Calculated | 100 |

## Commands

- `macf_tools statusline` - Generate statusline output
- `macf_tools statusline install` - Install to Claude Code
