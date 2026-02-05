# Environment Configuration

This guide covers PA (Primary Agent) environment setup and the env.d extensibility pattern.

## PA Environment Curation

### Build-Time Initialization

MacEff creates a `.bash_init` file for each PA user during container startup:

```
/home/{username}/.bash_init
```

This file contains:
- Container-wide environment variables (MACEFF_ROOT, MACEFF_AGENT_ROOT, etc.)
- PATH configuration
- Project-specific environment setup

### How It Works

1. `start.py` calls `create_bash_init()` during user creation
2. `.bash_init` is generated with environment variables
3. `.bashrc` sources `.bash_init` for interactive shells
4. `BASH_ENV` points to `.bash_init` for non-interactive shells (Claude Code Bash tool)

## env.d Extensibility

### Overview

The env.d dispatch pattern allows project-specific environment customization without modifying framework code.

**Location:** `/opt/maceff/framework/env.d/*.sh`

### Script Naming Convention

Scripts are sourced in alphanumeric order:
- `10-conda.sh` - Conda environment activation
- `20-path.sh` - Additional PATH entries
- `30-aliases.sh` - Project-specific aliases

### Creating Custom Scripts

**Example: Conda activation (`10-conda.sh`):**
```bash
#!/bin/bash
# Activate project conda environment
if command -v conda &> /dev/null; then
    conda activate myproject_env
fi
```

**Example: PATH setup (`20-path.sh`):**
```bash
#!/bin/bash
# Add project binaries to PATH
export PATH="$HOME/.local/bin:$PATH"
```

### Installation

1. Create scripts in your project's `framework/env.d/` directory
2. Run `maceff-init` to copy to overlay
3. Rebuild container (scripts are copied at build-time)

## Environment Variables

| Variable | Description |
|----------|-------------|
| `MACEFF_ROOT` | Framework installation location |
| `MACEFF_AGENT_ROOT` | Agent's home directory |
| `MACEFF_AGENT_HOME_DIR` | Alias for agent home (consciousness artifacts) |
| `BASH_ENV` | Points to `.bash_init` for non-interactive shells |
| `CLAUDE_PROJECT_DIR` | Claude Code project workspace |

## CLI Proprioception Discovery

MACF provides automatic CLI awareness injection at session start, answering foundational orientation questions for agents:

### What Gets Injected

On fresh sessions (compaction recovery, `/clear`, migration), the SessionStart hook runs three CLI commands and injects their output:

| Command | Question Answered | Content |
|---------|-------------------|---------|
| `macf_tools --help` | "What can I do?" | Top-level command overview |
| `macf_tools cmd-tree` | "What's the full capability map?" | Complete command tree with arguments |
| `macf_tools env` | "Where am I?" | Environment state, paths, versions |

### When It Fires

Proprioception injection is **conditional on session freshness**:

- **Fresh session** (post-compaction, `/clear`, migration): Full injection (~2000 tokens)
- **Resume session** (`/resume`): No injection (agent retains working memory)

This matches awareness intensity to actual context loss — maximum awareness for maximum amnesia, minimal disruption for continuity.

### Manual Discovery

Agents can always run these commands manually for orientation:

```bash
macf_tools --help       # Command overview
macf_tools cmd-tree     # Full command tree with arguments
macf_tools env          # Environment state
```

See [Hooks Guide](hooks.md#1-session_start) for implementation details.

## Debugging

Use `macf_tools env` to display current environment configuration:

```bash
macf_tools env           # Pretty-printed output
macf_tools env --json    # Machine-readable JSON
```

See [CLI Reference](cli-reference.md#env) for detailed output format.
