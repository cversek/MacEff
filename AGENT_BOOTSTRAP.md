# Agent Bootstrap Guide

Automated agent creation for MacEff containers. Reduces agent setup from 73 minutes manual to ~5 minutes automated.

## Quick Start

```bash
# Basic usage (interactive prompts)
./tools/bin/agent-bootstrap maceff_myagent

# Full specification
./tools/bin/agent-bootstrap maceff_myagent "email@example.com" "Agent Description"

# Example: Create test agent
./tools/bin/agent-bootstrap maceff_test "test@maceff.local" "Test Agent"
```

## Prerequisites

1. **Container running**: `make up` or `docker compose up -d`
2. **MacEff initialized**: Run `./tools/bin/maceff-init` if `.maceff/` directory doesn't exist
3. **Policies deployed**: Automatic on container startup

## What It Does

The bootstrap script automates 8 steps:

1. **Create user** in container with home directory
2. **Create .claude directory** for Claude Code configuration
3. **Generate SSH key pair** (ed25519) on host
4. **Deploy SSH key** to container authorized_keys
5. **Initialize config** (`.macf/config.json` with agent identity)
6. **Initialize preamble** (CLAUDE.md with PA framework)
7. **Install hooks** (all 6 consciousness hooks)
8. **Verify setup** (run environment check)

## Usage

### Syntax

```
agent-bootstrap <agent_name> [email] [description]
```

**Arguments**:
- `agent_name` (required): Username in container (e.g., `maceff_agent`)
- `email` (optional): Agent email (default: `<agent_name>@maceff.local`)
- `description` (optional): Agent description (default: "MacEff Primary Agent")

### Examples

```bash
# Minimal (uses defaults)
./tools/bin/agent-bootstrap maceff_dev

# With email
./tools/bin/agent-bootstrap maceff_agent "agent@example.com"

# Full specification
./tools/bin/agent-bootstrap maceff_agent "agent@example.com" "Development Primary Agent"
```

### Environment Variables

- `CONTAINER_NAME`: Override container name (default: `maceff-sandbox`)

Example:
```bash
CONTAINER_NAME=my-container ./tools/bin/agent-bootstrap maceff_test
```

## Output

### Success

```
✅ Agent bootstrap complete!

Agent Details:
  Name:        maceff_test
  Email:       test@maceff.local
  Description: Test Agent

SSH Connection:
  ssh -i ./keys/maceff_maceff_test -p 3022 maceff_test@localhost
```

### What Gets Created

**On Host**:
- `./keys/maceff_<agent_name>` - Private SSH key
- `./keys/maceff_<agent_name>.pub` - Public SSH key

**In Container**:
- `/home/<agent_name>/` - User home directory
- `/home/<agent_name>/.macf/config.json` - Agent configuration
- `/home/<agent_name>/.claude/` - Claude Code directory
- `/home/<agent_name>/.claude/hooks/` - 6 consciousness hooks
- `/home/<agent_name>/.claude/settings.local.json` - Hook configuration
- `/home/<agent_name>/CLAUDE.md` - PA preamble
- `/home/<agent_name>/agent/policies/personal/` - Personal policy directory

## Connecting to Agent

### SSH Connection

```bash
# Use generated SSH key
ssh -i ./keys/maceff_<agent_name> -p 3022 <agent_name>@localhost

# Example for maceff_test
ssh -i ./keys/maceff_maceff_test -p 3022 maceff_test@localhost
```

### Verify Environment

After connecting:
```bash
# Check macf_tools available
macf_tools --version

# Check configuration
macf_tools config show

# Check hooks installed
ls -la ~/.claude/hooks/

# Test environment
macf_tools env
```

## Troubleshooting

### Container Not Running

```
❌ ERROR: Container 'maceff-sandbox' is not running. Start it with: make up
```

**Fix**: Start container with `make up` or `docker compose up -d`

### User Already Exists

```
❌ ERROR: User 'maceff_test' already exists in container
```

**Fix**: Either use different name or remove existing user:
```bash
docker exec -u 0 maceff-sandbox userdel -r maceff_test
```

### SSH Key Already Exists

```
⚠️  WARNING: SSH key already exists at ./keys/maceff_maceff_test
```

**Action**: Script will prompt to overwrite or abort

### Permission Errors

If hooks installation fails with permission errors:
```bash
# Verify .claude directory ownership
docker exec maceff-sandbox ls -la /home/<agent_name>/.claude

# Should be owned by agent user, not root
```

### Template Not Found

If preamble initialization fails:
```
Error: PA_PREAMBLE.md template not found
```

**Fix**: Ensure `.maceff/framework/templates/PA_PREAMBLE.md` exists. Run `./tools/bin/maceff-init` if needed.

## Time Comparison

**Before Automation** (Manual):
- User creation: 5 min
- SSH setup: 10 min
- Config init workarounds: 15 min
- Preamble setup: 10 min
- Hooks installation: 8 min
- Policy fixes: 15 min
- Debugging: 10 min
- **Total: 73 minutes**

**With Automation**:
- Script execution: ~5 minutes
- Zero manual intervention
- **93% time reduction**

## Architecture Notes

### Portable Template Resolution

The script uses environment-aware template discovery:

1. `$MACEFF_TEMPLATES_DIR/PA_PREAMBLE.md` (if set)
2. `$MACEFF_ROOT/framework/templates/PA_PREAMBLE.md` (default: `/opt/maceff`)
3. `./templates/PA_PREAMBLE.md` (development mode)

This ensures MACF portability across different deployment environments.

### Config Naming

- `.macf/` - MACF framework per-user config (portable)
- `.maceff/` - MacEff project customization (host-only)

Clear separation prevents naming confusion between project and user scopes.

## Integration with Claude Code

After bootstrap, configure Claude Code:

1. **SSH Connection**: Use generated key to connect
2. **Project Setup**: Initialize workspace in agent's home directory
3. **Hooks Active**: All 6 consciousness hooks automatically loaded
4. **Preamble Available**: CLAUDE.md provides PA framework context

## See Also

- **Infrastructure Improvements ROADMAP**: Full automation implementation plan
- **MacEff README**: Container management and development workflow
