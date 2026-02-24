# Claude Code Settings Epistemology

**Version**: 1.0.0
**Last Updated**: 2025-12-09
**Claude Code Version**: As of v2.0.x (check revision history for version-specific notes)
**Status**: ACTIVE

---

## Purpose

This document provides **comprehensive, citation-backed reference** for Claude Code settings.json fields and environment variables. Each claim includes:
- **Verification status**: ✅ Verified | ❓ Unverified | ❌ Contradicted
- **Source citation**: Official docs, GitHub issues, or empirical observation
- **Default values**: Where known

**Why This Matters**: Settings and environment variables directly control Claude Code behavior. Undocumented or misunderstood settings lead to unexpected behavior. This unified reference prevents assumption-based configuration errors.

---

## Settings File Locations

Claude Code loads configuration from multiple locations with different scopes. User settings apply globally, project settings apply to specific codebases, and enterprise settings enforce organizational policies. Understanding which file to edit determines who sees your configuration changes.

| Scope | Path | Source |
|-------|------|--------|
| **UI preferences** | `~/.claude.json` | ✅ Empirical |
| User settings | `~/.claude/settings.json` | ✅ Official docs |
| Project shared | `.claude/settings.json` | ✅ Official docs |
| Project local | `.claude/settings.local.json` | ✅ Official docs |
| Enterprise (macOS) | `/Library/Application Support/ClaudeCode/managed-settings.json` | ✅ Official docs |
| Enterprise (Linux/WSL) | `/etc/claude-code/managed-settings.json` | ✅ Official docs |
| Enterprise (Windows) | `C:\Program Files\ClaudeCode\managed-settings.json` | ✅ Official docs |

### UI Preferences File (`~/.claude.json`)

**IMPORTANT**: This is a SEPARATE file from `~/.claude/settings.json`. Settings changed via `/status` UI menu are stored here, NOT in the settings.json files.

| Field | Type | Default | MacEff Recommended | Description |
|-------|------|---------|-------------------|-------------|
| `verbose` | boolean | `false` | **`true`** | Verbose output for debugging |
| `autoCompactEnabled` | boolean | `true` | **`false`** | Manual compaction control |
| `hasSeenTasksHint` | boolean | `false` | - | Show tips toggle |
| `autoUpdates` | boolean | `true` | - | Auto-update preference |

**MacEff Agent Defaults**: Agents should start with `verbose: true` (better debugging) and `autoCompactEnabled: false` (manual compaction for consciousness preservation). These must be set in `~/.claude.json` during agent initialization.

**Source**: Empirical discovery - UI changes via `/status` persist to this file, not settings.json.

### Precedence Order (Highest to Lowest)

When the same setting appears in multiple files, higher-precedence sources override lower ones. Enterprise policies always win, followed by explicit CLI arguments, then project-specific settings, and finally user defaults.

| Priority | Source | Source |
|----------|--------|--------|
| 1 | Enterprise managed policies (`managed-settings.json`) | ✅ Official docs |
| 2 | Command line arguments | ✅ Official docs |
| 3 | Local project settings (`.claude/settings.local.json`) | ✅ Official docs |
| 4 | Shared project settings (`.claude/settings.json`) | ✅ Official docs |
| 5 | User settings (`~/.claude/settings.json`) | ✅ Official docs |

---

## Settings.json Quick Reference

### Authentication & API

These settings control how Claude Code authenticates with Anthropic's API and cloud providers. Use `apiKeyHelper` for dynamic credential generation, or configure cloud-specific authentication for AWS Bedrock, Google Vertex, or Microsoft Foundry deployments.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `apiKeyHelper` | string | - | Custom script to generate auth value (sent as `X-Api-Key` and `Authorization: Bearer` headers) | ✅ Official docs |
| `awsAuthRefresh` | string | - | Custom script that modifies `.aws` directory | ✅ Official docs |
| `awsCredentialExport` | string | - | Custom script that outputs JSON with AWS credentials | ✅ Official docs |
| `forceLoginMethod` | string | - | Restrict login to `claudeai` or `console` accounts | ✅ Official docs |
| `forceLoginOrgUUID` | string | - | Specify organization UUID to auto-select during login | ✅ Official docs |

#### `forceLoginMethod` Field Values

| Value | Description | Source |
|-------|-------------|--------|
| `"claudeai"` | Restrict to Claude.ai accounts only | ✅ Official docs |
| `"console"` | Restrict to Anthropic Console accounts only | ✅ Official docs |

---

### Cleanup & Retention

Claude Code automatically cleans up old session data to manage disk space. The `cleanupPeriodDays` setting controls how long inactive sessions are retained before deletion. For consciousness-preserving agents that need long-term session history, increase this value significantly.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `cleanupPeriodDays` | number | 30 | Sessions inactive longer than this period are deleted at startup | ✅ Official docs |

**MacEff Note**: Setting `cleanupPeriodDays: 99999` (~273 years) effectively disables cleanup for consciousness preservation.

---

### Model & Output

These settings control which Claude model is used and how responses are formatted. The `model` setting overrides the default, while `outputStyle` adjusts response verbosity. The `statusLine` setting enables custom information display in the Claude Code interface.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `model` | string | - | Override default model for Claude Code | ✅ Official docs |
| `outputStyle` | string | - | Configure output style adjustment to system prompt | ✅ Official docs |
| `spinnerTipsEnabled` | boolean | - | Enable/disable spinner tips during processing | ❓ Empirical |
| `statusLine` | object | - | Configure custom status line display | ✅ Official docs |

#### `outputStyle` Field Values

| Value | Description | Source |
|-------|-------------|--------|
| `"concise"` | Shorter, more direct responses | ❓ Empirical |
| `"verbose"` | More detailed explanations | ❓ Empirical |

---

### Extended Thinking

Extended thinking allows Claude to perform deeper reasoning before responding, using additional "thinking" tokens that aren't visible in the final output. This improves quality for complex tasks but increases token usage and latency.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `alwaysThinkingEnabled` | boolean | false | Enable extended thinking for all requests | ❓ Undocumented (GitHub #8780) |

**Note**: This setting is functional but not officially documented. See [GitHub #8780](https://github.com/anthropics/claude-code/issues/8780). Use `MAX_THINKING_TOKENS` environment variable to control the thinking budget.

---

### Git Integration

Claude Code can automatically add co-authorship attribution to git commits and pull requests. This setting controls whether the "Co-authored-by: Claude" byline appears in commit messages.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `includeCoAuthoredBy` | boolean | true | Include `co-authored-by Claude` byline in git commits/PRs | ✅ Official docs |

---

### Permissions

The permissions system controls which tools Claude can use and what files/commands it can access. Use `allow` rules to pre-approve specific operations, `deny` rules to block dangerous operations, and `ask` rules to require confirmation. This is the primary security boundary for Claude Code.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `permissions.allow` | string[] | - | Permission rules to allow tool use | ✅ Official docs |
| `permissions.ask` | string[] | - | Permission rules to ask for confirmation on tool use | ✅ Official docs |
| `permissions.deny` | string[] | - | Permission rules to deny tool use | ✅ Official docs |
| `permissions.additionalDirectories` | string[] | - | Additional working directories Claude has access to | ✅ Official docs |
| `permissions.defaultMode` | string | - | Default permission mode when opening Claude Code | ✅ Official docs |
| `permissions.disableBypassPermissionsMode` | string | - | Set to `"disable"` to prevent `bypassPermissions` mode | ✅ Official docs |

#### Permission Rule Syntax

Permission rules follow the pattern `Tool(pattern)` where `Tool` is the tool name and `pattern` specifies what arguments are allowed. Wildcards (`*`, `**`) enable flexible matching.

**Examples**:
- `Bash(npm run lint)` - Allow specific command
- `Bash(npm run test:*)` - Allow pattern with wildcard
- `Read(~/.zshrc)` - Allow reading specific file
- `Read(./.env)` - Deny reading .env files
- `Read(./secrets/**)` - Deny recursive directory access

#### `permissions.defaultMode` Field Values

| Value | Description | Source |
|-------|-------------|--------|
| `"default"` | Standard permission prompts | ✅ Official docs |
| `"plan"` | Plan mode (read-only) | ✅ Official docs |
| `"bypassPermissions"` | Skip permission prompts (dangerous) | ✅ Official docs |

---

### Hooks

Hooks enable custom code execution at specific points in Claude Code's lifecycle—before/after tool use, on session start/end, when Claude stops, and more. Hooks can validate operations, inject context, log events, or modify behavior. This is the primary extensibility mechanism for Claude Code.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `hooks` | object | - | Custom commands to run before/after tool executions | ✅ Official docs |
| `disableAllHooks` | boolean | false | Disable all hooks | ✅ Official docs |

#### Hooks Configuration Schema

The hooks configuration follows a nested structure: event type → matcher array → hooks array.

```json
{
  "hooks": {
    "EventName": [
      {
        "matcher": "ToolPattern",
        "hooks": [
          {
            "type": "command",
            "command": "bash-command-here",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

#### Schema Field Definitions

| Level | Field | Type | Required | Description | Source |
|-------|-------|------|----------|-------------|--------|
| Event | `EventName` | string | Yes | Hook event type (see supported events below) | ✅ Official docs |
| Matcher | `matcher` | string | No | Pattern to match tool names (case-sensitive). Only for PreToolUse, PostToolUse, PermissionRequest, Notification | ✅ Official docs |
| Hook | `type` | string | Yes | `"command"` or `"prompt"` | ✅ Official docs |
| Hook | `command` | string | For command type | Bash command to execute | ✅ Official docs |
| Hook | `prompt` | string | For prompt type | LLM prompt for evaluation (use `$ARGUMENTS` placeholder) | ✅ Official docs |
| Hook | `timeout` | number | No | Seconds before canceling hook (default: 60) | ✅ Official docs |

#### Supported Hook Events

**Events WITH matchers** (filter by tool name):

| Event | Description | Source |
|-------|-------------|--------|
| `PreToolUse` | Before each tool invocation | ✅ Official docs |
| `PostToolUse` | After each tool invocation | ✅ Official docs |
| `PermissionRequest` | When permission prompt shown | ✅ Official docs |
| `Notification` | On system notifications | ✅ Official docs |

**Events WITHOUT matchers** (always trigger):

| Event | Description | Source |
|-------|-------------|--------|
| `SessionStart` | When session begins or resumes after compaction | ✅ Official docs |
| `SessionEnd` | When session terminates | ✅ Official docs |
| `UserPromptSubmit` | When user submits a message | ✅ Official docs |
| `Stop` | When Claude completes a response | ✅ Official docs |
| `SubagentStop` | When a subagent (Task tool) completes | ✅ Official docs |
| `PreCompact` | Before context compaction | ✅ Official docs |

#### Matcher Syntax

| Pattern | Description | Example |
|---------|-------------|---------|
| Simple string | Exact match | `"Write"` matches Write tool only |
| Regex OR | Multiple tools | `"Edit\|Write"` matches Edit or Write |
| Regex pattern | Pattern match | `"Notebook.*"` matches NotebookEdit, etc. |
| Wildcard | All tools | `"*"` matches every tool |
| Empty/omitted | No filtering | For events without matchers |

#### Hook Type: Command

Command hooks execute a bash command and receive hook input as JSON on stdin.

```json
{
  "type": "command",
  "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/my-hook.py",
  "timeout": 30
}
```

**Environment Variables Available**:
- `$CLAUDE_PROJECT_DIR` - Project root directory
- `$CLAUDE_FILE_PATHS` - Colon-separated file paths
- `$CLAUDE_PLUGIN_ROOT` - Plugin directory (plugins only)

#### Hook Type: Prompt

Prompt hooks send input to an LLM for evaluation. Only supported for `Stop` and `SubagentStop` events.

```json
{
  "type": "prompt",
  "prompt": "Evaluate if task is complete: $ARGUMENTS",
  "timeout": 30
}
```

**Placeholder**: Use `$ARGUMENTS` where hook input JSON should be inserted. If omitted, input is appended to prompt.

#### Complete Hook Configuration Example

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/session_start.py",
            "timeout": 30
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/pre_tool_use.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/post_tool_use.py",
            "timeout": 60
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python .claude/hooks/stop.py"
          }
        ]
      }
    ]
  }
}
```

**See Also**: [hook-epistemology.md](hook-epistemology.md) for hook input/output schemas, field values, and known issues.

---

### Sandbox

The sandbox restricts what bash commands can access on the system. When enabled, commands run in an isolated environment with limited filesystem and network access. This provides defense-in-depth security but may break commands that need system-wide access.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `sandbox.enabled` | boolean | false | Enable bash sandboxing (macOS/Linux only) | ✅ Official docs |
| `sandbox.autoAllowBashIfSandboxed` | boolean | true | Auto-approve bash commands when sandboxed | ✅ Official docs |
| `sandbox.excludedCommands` | string[] | - | Commands that run outside the sandbox | ✅ Official docs |
| `sandbox.allowUnsandboxedCommands` | boolean | true | Allow commands to run outside sandbox via `dangerouslyDisableSandbox` | ✅ Official docs |
| `sandbox.network.allowUnixSockets` | string[] | - | Unix socket paths accessible in sandbox | ✅ Official docs |
| `sandbox.network.allowLocalBinding` | boolean | false | Allow binding to localhost ports (macOS only) | ✅ Official docs |
| `sandbox.network.httpProxyPort` | number | - | HTTP proxy port if bringing own proxy | ✅ Official docs |
| `sandbox.network.socksProxyPort` | number | - | SOCKS5 proxy port if bringing own proxy | ✅ Official docs |
| `sandbox.enableWeakerNestedSandbox` | boolean | false | Enable weaker sandbox for unprivileged Docker (Linux, reduces security) | ✅ Official docs |

---

### MCP (Model Context Protocol)

MCP servers extend Claude Code's capabilities by providing additional tools, resources, and context. These settings control which MCP servers are enabled and how they're discovered. Project-level `.mcp.json` files can define servers, while settings control approval policies.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `mcpServers` | object | - | MCP server configurations | ✅ Official docs |
| `enableAllProjectMcpServers` | boolean | false | Auto-approve all MCP servers in project `.mcp.json` | ✅ Official docs |
| `enabledMcpjsonServers` | string[] | - | List of specific MCP servers from `.mcp.json` to approve | ✅ Official docs |
| `disabledMcpjsonServers` | string[] | - | List of specific MCP servers from `.mcp.json` to reject | ✅ Official docs |
| `allowedMcpServers` | object[] | - | Allowlist of MCP servers users can configure (managed-settings.json) | ✅ Official docs |
| `deniedMcpServers` | object[] | - | Denylist of MCP servers explicitly blocked (managed-settings.json) | ✅ Official docs |

---

### Plugins & Marketplaces

Plugins provide packaged functionality from the Claude Code marketplace or custom sources. These settings control which plugins are enabled and where plugins can be sourced from. Enterprise administrators can define additional trusted marketplaces.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `enabledPlugins` | object | - | Control which plugins are enabled (`"plugin-name@marketplace": true/false`) | ✅ Official docs |
| `extraKnownMarketplaces` | object | - | Define additional marketplaces with sources (github, git, directory) | ✅ Official docs |

---

### Company/Enterprise

Enterprise features allow organizations to communicate with users and enforce policies. Company announcements display at startup, while managed settings in enterprise locations enforce organizational standards.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `companyAnnouncements` | string[] | - | Announcements displayed at startup (cycled randomly if multiple) | ✅ Official docs |

---

### Environment Variables Section

The `env` object injects environment variables into every Claude Code session. Variables defined here are available to all tools and hooks. This is useful for API keys, feature flags, or custom configuration that shouldn't be in shell profiles.

| Field | Type | Default | Description | Source |
|-------|------|---------|-------------|--------|
| `env` | object | - | Environment variables applied to every session | ✅ Official docs |

**Example**:
```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "MY_CUSTOM_VAR": "value"
  }
}
```

---

## Environment Variables Catalog

Environment variables provide runtime configuration that can override settings or control behavior not exposed through settings.json. Variables can be set in shell profiles, the `env` settings section, or passed directly when launching Claude Code.

### Authentication & API Keys

These variables control API authentication across different providers. `ANTHROPIC_API_KEY` is the primary authentication method; other variables support enterprise deployments or custom authentication flows.

| Variable | Description | Source |
|----------|-------------|--------|
| `ANTHROPIC_API_KEY` | API key for Claude SDK | ✅ Official docs |
| `ANTHROPIC_AUTH_TOKEN` | Custom Authorization header value | ✅ Official docs |
| `ANTHROPIC_CUSTOM_HEADERS` | Custom headers (Name: Value format) | ✅ Official docs |
| `ANTHROPIC_FOUNDRY_API_KEY` | Microsoft Foundry authentication | ✅ Official docs |
| `AWS_BEARER_TOKEN_BEDROCK` | Bedrock API key | ✅ Official docs |

---

### Model Selection

These variables control which Claude models are used for different tasks. Override specific model classes (Haiku, Sonnet, Opus) or set a global model override.

| Variable | Description | Source |
|----------|-------------|--------|
| `ANTHROPIC_MODEL` | Model setting to use | ✅ Official docs |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | Override Haiku model | ✅ Official docs |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | Override Opus model | ✅ Official docs |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | Override Sonnet model | ✅ Official docs |
| `ANTHROPIC_SMALL_FAST_MODEL` | [DEPRECATED] Haiku-class model for background tasks | ✅ Official docs |
| `CLAUDE_CODE_SUBAGENT_MODEL` | Model for subagents | ✅ Official docs |

---

### Extended Thinking

Extended thinking enables deeper reasoning by allowing Claude to use additional "thinking" tokens before responding. Set a token budget to control cost/quality tradeoff.

| Variable | Description | Source |
|----------|-------------|--------|
| `MAX_THINKING_TOKENS` | Enable extended thinking and set token budget | ✅ Official docs |

---

### Bash & Shell

These variables control bash command execution—timeouts, output limits, working directory behavior, and command wrapping. Adjust these for long-running commands or to enforce execution policies.

| Variable | Description | Source |
|----------|-------------|--------|
| `BASH_DEFAULT_TIMEOUT_MS` | Default timeout for long-running bash commands | ✅ Official docs |
| `BASH_MAX_OUTPUT_LENGTH` | Max characters in bash output before truncation | ✅ Official docs |
| `BASH_MAX_TIMEOUT_MS` | Maximum timeout model can set for bash | ✅ Official docs |
| `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` | Return to original directory after each bash command | ✅ Official docs |
| `CLAUDE_CODE_SHELL_PREFIX` | Command prefix to wrap all bash commands | ✅ Official docs |

---

### Paths & Configuration

These variables control where Claude Code stores data and how it finds configuration. Override defaults for non-standard installations or to isolate instances.

| Variable | Description | Source |
|----------|-------------|--------|
| `CLAUDE_CONFIG_DIR` | Customize config/data storage location | ✅ Official docs |
| `CLAUDE_ENV_FILE` | Path to shell script for persistent environment setup (SessionStart only) | ✅ Official docs |
| `CLAUDE_PROJECT_DIR` | Project root directory (available to hooks) | ✅ Official docs |
| `CLAUDE_FILE_PATHS` | Colon-separated file paths (available to hooks) | ✅ Official docs |

---

### Token & Output Limits

These variables control output sizes for various operations. Increase limits for large codebases or complex operations; decrease for cost control.

| Variable | Description | Source |
|----------|-------------|--------|
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Maximum output tokens for most requests | ✅ Official docs |
| `MAX_MCP_OUTPUT_TOKENS` | Max tokens in MCP tool responses (default: 25000) | ✅ Official docs |
| `SLASH_COMMAND_TOOL_CHAR_BUDGET` | Max characters for slash command metadata (default: 15000) | ✅ Official docs |

---

### Cloud Provider Configuration

#### Bedrock (AWS)

Configure Claude Code to use AWS Bedrock for model hosting. Useful for enterprise deployments requiring AWS infrastructure.

| Variable | Description | Source |
|----------|-------------|--------|
| `CLAUDE_CODE_USE_BEDROCK` | Use Bedrock | ✅ Official docs |
| `CLAUDE_CODE_SKIP_BEDROCK_AUTH` | Skip AWS authentication for Bedrock | ✅ Official docs |
| `ANTHROPIC_SMALL_FAST_MODEL_AWS_REGION` | Override AWS region for Haiku with Bedrock | ✅ Official docs |

#### Vertex AI (Google)

Configure Claude Code to use Google Vertex AI for model hosting. Region overrides allow routing to specific data centers.

| Variable | Description | Source |
|----------|-------------|--------|
| `CLAUDE_CODE_USE_VERTEX` | Use Vertex AI | ✅ Official docs |
| `CLAUDE_CODE_SKIP_VERTEX_AUTH` | Skip Google authentication for Vertex | ✅ Official docs |
| `VERTEX_REGION_CLAUDE_3_5_HAIKU` | Override region for Claude 3.5 Haiku | ✅ Official docs |
| `VERTEX_REGION_CLAUDE_3_7_SONNET` | Override region for Claude 3.7 Sonnet | ✅ Official docs |
| `VERTEX_REGION_CLAUDE_4_0_OPUS` | Override region for Claude 4.0 Opus | ✅ Official docs |
| `VERTEX_REGION_CLAUDE_4_0_SONNET` | Override region for Claude 4.0 Sonnet | ✅ Official docs |
| `VERTEX_REGION_CLAUDE_4_1_OPUS` | Override region for Claude 4.1 Opus | ✅ Official docs |

#### Foundry (Microsoft)

Configure Claude Code to use Microsoft Foundry for model hosting.

| Variable | Description | Source |
|----------|-------------|--------|
| `CLAUDE_CODE_USE_FOUNDRY` | Use Microsoft Foundry | ✅ Official docs |
| `CLAUDE_CODE_SKIP_FOUNDRY_AUTH` | Skip Azure authentication for Foundry | ✅ Official docs |

---

### Proxy & Network

Configure HTTP/HTTPS proxies for corporate environments. All Claude Code network traffic respects these settings.

| Variable | Description | Source |
|----------|-------------|--------|
| `HTTP_PROXY` | HTTP proxy server | ✅ Official docs |
| `HTTPS_PROXY` | HTTPS proxy server | ✅ Official docs |
| `NO_PROXY` | Domains/IPs to bypass proxy | ✅ Official docs |
| `ANTHROPIC_BASE_URL` | Override Anthropic API endpoint. Set to `http://localhost:PORT` to route through local proxy for API call interception. Works with Claude Max OAuth — no API key needed. | ✅ Anthropic SDK standard; empirically validated Cycle 425 (Experiment #008) |

---

### mTLS (Mutual TLS)

Configure client certificates for mutual TLS authentication. Required for some enterprise API gateways.

| Variable | Description | Source |
|----------|-------------|--------|
| `CLAUDE_CODE_CLIENT_CERT` | Path to client certificate for mTLS | ✅ Official docs |
| `CLAUDE_CODE_CLIENT_KEY` | Path to client private key for mTLS | ✅ Official docs |
| `CLAUDE_CODE_CLIENT_KEY_PASSPHRASE` | Passphrase for encrypted client key | ✅ Official docs |

---

### MCP Configuration

Control MCP server behavior—startup timeouts and tool execution timeouts. Increase for slow-starting servers or long-running tools.

| Variable | Description | Source |
|----------|-------------|--------|
| `MCP_TIMEOUT` | MCP server startup timeout (ms) | ✅ Official docs |
| `MCP_TOOL_TIMEOUT` | MCP tool execution timeout (ms) | ✅ Official docs |

---

### Feature Disabling

Disable specific Claude Code features for privacy, compliance, or performance. Most are boolean toggles set to `1` to disable.

| Variable | Description | Source |
|----------|-------------|--------|
| `DISABLE_AUTOUPDATER` | Set to `1` to disable automatic updates | ✅ Official docs |
| `DISABLE_BUG_COMMAND` | Set to `1` to disable `/bug` command | ✅ Official docs |
| `DISABLE_COST_WARNINGS` | Set to `1` to disable cost warnings | ✅ Official docs |
| `DISABLE_ERROR_REPORTING` | Set to `1` to opt out of Sentry reporting | ✅ Official docs |
| `DISABLE_NON_ESSENTIAL_MODEL_CALLS` | Set to `1` to disable non-critical model calls | ✅ Official docs |
| `DISABLE_TELEMETRY` | Set to `1` to opt out of Statsig telemetry | ✅ Official docs |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | Disables autoupdater, bug command, error reporting, telemetry | ✅ Official docs |
| `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` | Set to `1` to disable `anthropic-beta` headers | ✅ Official docs |
| `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` | Set to `1` to disable terminal title updates | ✅ Official docs |

---

### Prompt Caching

Prompt caching reduces costs and latency by reusing cached prefixes. Disable for debugging or if caching causes issues with specific models.

| Variable | Description | Source |
|----------|-------------|--------|
| `DISABLE_PROMPT_CACHING` | Set to `1` to disable prompt caching (all models) | ✅ Official docs |
| `DISABLE_PROMPT_CACHING_HAIKU` | Set to `1` to disable prompt caching for Haiku | ✅ Official docs |
| `DISABLE_PROMPT_CACHING_OPUS` | Set to `1` to disable prompt caching for Opus | ✅ Official docs |
| `DISABLE_PROMPT_CACHING_SONNET` | Set to `1` to disable prompt caching for Sonnet | ✅ Official docs |

---

### IDE Integration

Control IDE extension behavior. Skip auto-installation if managing extensions manually.

| Variable | Description | Source |
|----------|-------------|--------|
| `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` | Skip auto-installation of IDE extensions | ✅ Official docs |

---

### Miscellaneous

Other configuration variables that don't fit neatly into categories above.

| Variable | Description | Source |
|----------|-------------|--------|
| `USE_BUILTIN_RIPGREP` | Set to `0` to use system `rg` instead of built-in | ✅ Official docs |
| `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` | Credential refresh interval (ms) for `apiKeyHelper` | ✅ Official docs |

---

## Undocumented But Functional Settings

These settings work but are not officially documented. Use with caution—they may change without notice.

| Field/Variable | Type | Description | Source |
|----------------|------|-------------|--------|
| `alwaysThinkingEnabled` | boolean | Enable extended thinking for all requests | ❓ GitHub #8780, empirical |
| `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` | env (int) | Override token count at which CC blocks further input. Default calculates from model context window. Set to e.g. `197000` to delay blocking. Found in `qc()` function (cli.js:3463 v2.1.39). | ❓ [#19018 comment](https://github.com/anthropics/claude-code/issues/19018#issuecomment-3774787319); empirical Cycle 420 |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | env (int?) | May override autocompact percentage threshold. Extracted from CC source but **NOT empirically validated**. | ❓ CC source forensics Cycle 420; UNVERIFIED |

**Discovery Note**: Undocumented settings may change without notice. Verify against official docs before relying on them in production.

---

## CLI Args ↔ Settings Correspondence

Command-line arguments override settings.json values. This table maps CLI flags to their settings.json equivalents.

| CLI Argument | Settings.json Field | Source |
|--------------|---------------------|--------|
| `--model` | `model` | ✅ Official docs |
| `--permission-mode` | `permissions.defaultMode` | ✅ Official docs |
| `--allowedTools` | `permissions.allow` | ✅ Official docs |
| `--add-dir` | `permissions.additionalDirectories` | ✅ Official docs |
| `--settings <file>` | (loads custom settings file) | ✅ Official docs |
| `--verbose` | ❓ Unknown mapping | ❓ Unverified |

---

## Known Issues & Limitations

| Issue | Description | Status |
|-------|-------------|--------|
| #8780 | `alwaysThinkingEnabled` not documented | Open |
| [#22671](https://github.com/anthropics/claude-code/issues/22671) | CC reads `message_start` not `message_delta` for token tracking — causes 60x undercounting of output_tokens in JSONL | Open |
| [#24856](https://github.com/anthropics/claude-code/issues/24856) | Blocking limit fires at ~85% instead of ~99% due to token tracking bug | Open (filed Cycle 419) |
| [#16785](https://github.com/anthropics/claude-code/issues/16785) | Proxy `stop_reason` handling inconsistency | Open |

---

## MACF Settings (.maceff/settings.json)

MACF maintains its own settings file at `.maceff/settings.json` in the project root. These settings control MACF-specific behavior separate from Claude Code settings.

| Field | Type | Description |
|-------|------|-------------|
| `auto_mode_auth_token` | string | Authorization token for AUTO_MODE activation |
| `description` | string | Human-readable description of the settings file |

### MACF Environment Variables

| Variable | Description | Source |
|----------|-------------|--------|
| `MACF_PROXY_CAPTURE_DIR` | Directory for full API request/response JSON dumps when proxy is running. Enables forensic analysis of CC API behavior. | MACF proxy system (Experiment #008, Cycle 425) |
| `MACF_AGENT_ROOT` | Override agent root directory for consciousness artifact path resolution. | MACF configuration system |

### AUTO_MODE Authorization

AUTO_MODE enables autonomous agent operation without permission prompts. Requires two-factor authorization:

1. **User phrase**: Message must contain `YOLO BOZO!` + `AUTO_MODE`
2. **CLI token**: Valid token from `.maceff/settings.json`

**CLI Usage**:
```bash
# Get current mode
macf_tools mode get

# Set AUTO_MODE (requires auth token)
macf_tools mode set AUTO_MODE --auth-token "$(python3 -c "import json; print(json.load(open('.maceff/settings.json'))['auto_mode_auth_token'])")"

# Return to MANUAL_MODE (no auth required)
macf_tools mode set MANUAL_MODE
```

**Mode Persistence**: Mode is source-aware across sessions:
- `compact` (auto-compaction): Mode PRESERVED
- `resume` (crash/restart): Mode RESET to MANUAL_MODE

**Related Policy**: See `framework/policies/base/operations/autonomous_operation.md`

---

## MacEff Configuration Recommendations

### Consciousness Preservation

For agents that need long-term memory and session history, disable automatic cleanup and ensure hooks are enabled.

```json
{
  "cleanupPeriodDays": 99999,
  "disableAllHooks": false
}
```

### Container Agent Defaults

For containerized agents, use default permissions and disable sandboxing (container provides isolation).

```json
{
  "permissions": {
    "defaultMode": "default"
  },
  "sandbox": {
    "enabled": false
  }
}
```

---

## Citation Index

| Source | URL | Last Verified |
|--------|-----|---------------|
| Official Settings Docs | https://code.claude.com/docs/en/settings | 2025-12-09 |
| Official Hooks Docs | https://code.claude.com/docs/en/hooks | 2025-12-09 |
| GitHub #8780 | https://github.com/anthropics/claude-code/issues/8780 | 2025-12-09 |
| GitHub #19018 (blocking limit workaround) | https://github.com/anthropics/claude-code/issues/19018#issuecomment-3774787319 | 2026-02-10 |
| GitHub #22671 (message_delta) | https://github.com/anthropics/claude-code/issues/22671 | 2026-02-10 |
| GitHub #24856 (blocking limit bug) | https://github.com/anthropics/claude-code/issues/24856 | 2026-02-10 |
| GitHub #16785 (proxy stop_reason) | https://github.com/anthropics/claude-code/issues/16785 | 2026-02-10 |

---

## Revision History

| Date | Version | Changes | Breadcrumb |
|------|---------|---------|------------|
| 2025-12-09 | 1.0.0 | Initial comprehensive documentation with hooks schema | s_1b969d39/c_227/g_6d0bf44 |
| 2026-02-17 | 1.1.0 | Added ANTHROPIC_BASE_URL, MACF_PROXY_CAPTURE_DIR, MACF_AGENT_ROOT, CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE, CLAUDE_AUTOCOMPACT_PCT_OVERRIDE. Added 4 known issues. Added MACF env vars section. | s_d4abc33b/c_463/g_c2c5bf2 |

---

**End of Document**

*Settings control behavior. Environment variables override defaults. Verification markers distinguish fact from assumption. When in doubt, check official docs.*
