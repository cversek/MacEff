# CLI Development Standards

**Breadcrumb**: s_agent-bb/c_178/g_9b828c9/p_none/t_1763933658
**Type**: Development Standards (CORE tier)
**Scope**: All agents (PA and SA) - language agnostic
**Status**: ACTIVE
**Updated**: 2025-11-23

---

## Purpose

CLI development standards establish universal patterns for building command-line tools that users love: intuitive interfaces, helpful error messages, sensible defaults, and clear documentation. These standards apply across any language ecosystem (Python, Ruby, Go, JavaScript, etc.) and codify proven UX principles that make CLIs a joy to use.

**Core Insight**: Great CLIs aren't just functional—they're **conversation partners** that guide users toward success through progressive disclosure, actionable feedback, and thoughtful defaults.

---

## CEP Navigation Guide

**1 Command Structure Patterns**
- What makes a good command structure?
- How do I organize subcommands?
- When to use flags vs arguments vs subcommands?
- What naming conventions should I follow?
- How do I handle command aliases?

**1.1 Subcommand Organization**
- When should I use subcommands?
- How do I nest subcommands?
- What is maximum nesting depth?
- How do I group related commands?

**1.2 Flags and Arguments**
- What's the difference between flags and arguments?
- When to use positional vs named arguments?
- How do I design flag names?
- What are flag naming conventions?
- How do I handle boolean flags?

**1.3 Command Naming Conventions**
- What makes a good command name?
- How verbose should command names be?
- How do I handle multi-word commands?
- When to use abbreviations?

**2 Help Text Standards**
- What should help text include?
- How do I format help output?
- What is progressive help disclosure?
- How do I document examples?

**2.1 Help Text Structure**
- What sections are required?
- What order should sections appear?
- How verbose should descriptions be?
- How do I document complex options?

**2.2 Example Documentation**
- How many examples per command?
- What makes a good example?
- How do I format examples?
- When to include edge case examples?

**2.3 Progressive Help Disclosure**
- What is progressive disclosure?
- How do I balance brevity vs completeness?
- When to show detailed help?
- How do I layer help information?

**3 Error Message Formatting**
- What makes a good error message?
- How do I format error output?
- What information should errors include?
- How do I make errors actionable?

**3.1 Error Message Structure**
- What components should errors have?
- How do I indicate error severity?
- What is the error message template?
- How do I format multi-line errors?

**3.2 Actionable Feedback**
- What makes feedback actionable?
- How do I suggest fixes?
- When to include error codes?
- How do I link to documentation?

**3.3 User-Friendly Language**
- How do I write for non-technical users?
- What technical jargon should I avoid?
- How do I explain system constraints?
- When to show technical details?

**4 Configuration Patterns**
- How should CLIs handle configuration?
- What configuration formats should I support?
- How do I layer configuration sources?
- What are configuration best practices?

**4.1 Configuration File Formats**
- YAML vs JSON vs TOML considerations?
- When to support multiple formats?
- How do I validate configuration?
- What are format-specific pitfalls?

**4.2 Configuration Source Hierarchy**
- What is the standard hierarchy?
- How do I merge configuration sources?
- Which sources take precedence?
- How do I document precedence?

**4.3 Configuration Validation**
- When should validation occur?
- How do I report validation errors?
- What validation patterns work best?
- How do I provide validation feedback?

**5 User Experience Guidelines**
- What makes a great CLI UX?
- How do I design for discoverability?
- What are sensible defaults?
- How do I handle interactive vs non-interactive modes?

**5.1 Progressive Disclosure**
- What is progressive disclosure?
- How do I layer functionality?
- When to hide advanced features?
- How do I guide new users?

**5.2 Sensible Defaults**
- What makes a good default?
- How do I choose defaults?
- When to require explicit configuration?
- How do I document defaults?

**5.3 Interactive vs Non-Interactive**
- When to use interactive prompts?
- How do I detect interactive context?
- What are non-interactive requirements?
- How do I handle automation?

**6 Output Formatting**
- How should CLIs format output?
- Human vs machine-readable output?
- How do I structure JSON/YAML output?
- When to colorize output?

**6.1 Human-Readable Output**
- What formatting enhances readability?
- How do I use tables and lists?
- When to use color and formatting?
- How do I handle wide output?

**6.2 Machine-Readable Output**
- What formats support automation?
- How do I structure JSON output?
- When to provide raw output modes?
- How do I ensure parseable output?

**6.3 Output Mode Selection**
- How do users select output modes?
- What are standard flags?
- How do I detect context?
- What should be the default mode?

**7 Integration with Framework Policies**
- How does this relate to workspace_discipline.md?
- How does this connect to testing.md?
- What language-specific implementations exist?

**8 Anti-Patterns**
- What CLI design patterns should I avoid?
- What are common mistakes?
- How do I recognize bad CLI design?

=== CEP_NAV_BOUNDARY ===

---

## 1 Command Structure Patterns

### 1.1 Subcommand Organization

**When to Use Subcommands**:
- Tool has multiple distinct operations (e.g., `git add`, `git commit`, `git push`)
- Operations share common flags or configuration
- Logical grouping improves discoverability
- Tool complexity exceeds single command scope

**Subcommand Nesting**:
- **Maximum depth**: 2 levels recommended (e.g., `tool group action`)
- **Beyond 2 levels**: Consider splitting into separate tools
- **Example**: `macf_tools hooks install` (tool → noun → verb pattern)

**Grouping Strategies**:
```bash
# Resource-based grouping (nouns)
tool user create
tool user delete
tool user list

# Action-based grouping (verbs)
tool create user
tool create project
tool create agent

# Hybrid grouping (context-sensitive)
tool hooks install    # hooks context
tool hooks logs       # hooks context
tool session info     # session context
```

**Best Practices**:
- ✅ Use consistent patterns (all noun-verb OR all verb-noun)
- ✅ Group related operations under same parent
- ✅ Provide list/help command for each level
- ❌ Don't mix grouping strategies within same tool

### 1.2 Flags and Arguments

**Flags vs Arguments**:
- **Positional arguments**: Required inputs with natural order
- **Named flags**: Optional configuration or less common inputs
- **Boolean flags**: Enable/disable features

**Examples**:
```bash
# Good: Natural positional order
tool deploy <environment> <version>

# Good: Optional configuration via flags
tool deploy prod v2.1 --dry-run --verbose

# Bad: Everything as flags (verbose, unclear order)
tool deploy --environment=prod --version=v2.1  ❌
```

**Flag Naming Conventions**:
- **Long form**: `--verbose`, `--output-format`, `--dry-run`
- **Short form**: `-v`, `-o`, `-n` (single dash, single character)
- **Boolean flags**: No value needed (`--verbose`, not `--verbose=true`)
- **Value flags**: Space or equals (`--output file.txt` or `--output=file.txt`)

**Common Flag Patterns**:
```bash
--help, -h           # Show help
--version, -v        # Show version
--verbose, -v        # Increase verbosity
--quiet, -q          # Suppress output
--force, -f          # Skip confirmations
--dry-run, -n        # Preview without execution
--output FILE, -o    # Specify output destination
--config FILE, -c    # Specify config file
```

### 1.3 Command Naming Conventions

**Good Command Names**:
- ✅ Use common verbs: `get`, `list`, `create`, `delete`, `update`, `show`, `info`
- ✅ Be specific: `install` not `setup`, `restart` not `reload`
- ✅ Use kebab-case for multi-word: `list-users`, `dry-run`, `output-format`
- ✅ Keep short: 1-2 words ideal, 3 words maximum

**Examples**:
```bash
# Good naming
macf_tools session info       # Clear, concise
macf_tools hooks install      # Standard verb
macf_tools breadcrumb         # Single descriptive noun

# Bad naming
macf_tools get-current-session-information  ❌ (too verbose)
macf_tools hooks do-install                 ❌ (redundant "do")
macf_tools bc                               ❌ (unclear abbreviation)
```

**Abbreviation Guidelines**:
- ✅ Use well-known abbreviations: `info` (information), `init` (initialize), `env` (environment)
- ❌ Avoid obscure abbreviations: `bc` (breadcrumb?), `cfg` (config?), `sts` (status?)
- ✅ Provide aliases if abbreviation is valuable: `tool info` = `tool i`

---

## 2 Help Text Standards

### 2.1 Help Text Structure

**Required Sections** (in order):
1. **Brief description**: One-line summary of what command does
2. **Usage**: Command syntax with placeholders
3. **Arguments**: Required positional arguments (if any)
4. **Options**: Available flags with descriptions
5. **Examples**: Common use cases (2-4 examples)
6. **See also**: Related commands or documentation

**Template**:
```
COMMAND - Brief description

USAGE:
    tool command [OPTIONS] <required-arg> [optional-arg]

ARGUMENTS:
    <required-arg>    Description of required argument
    [optional-arg]    Description of optional argument

OPTIONS:
    -h, --help              Show this help message
    -v, --verbose           Enable verbose output
    -o, --output FILE       Write output to FILE (default: stdout)

EXAMPLES:
    # Common use case with explanation
    tool command input.txt

    # Advanced use case with multiple flags
    tool command input.txt --output result.txt --verbose

SEE ALSO:
    tool other-command      Related functionality
    https://docs.example.com/command    Full documentation
```

**Description Guidelines**:
- Start with verb: "Show", "Create", "List", "Install"
- Be concise: 1-2 sentences maximum
- Explain WHAT not HOW (save details for examples)
- Avoid jargon unless explaining technical tool

### 2.2 Example Documentation

**How Many Examples**:
- **Simple commands**: 1-2 examples
- **Complex commands**: 3-4 examples showing different flag combinations
- **Feature-rich commands**: Group examples by use case

**Good Example Structure**:
```bash
EXAMPLES:
    # Basic usage - most common case
    tool deploy production

    # With optional configuration
    tool deploy staging --dry-run

    # Full example with multiple flags
    tool deploy production --version v2.1.0 --timeout 300

    # Edge case or advanced pattern
    tool deploy production --config custom.yml --force
```

**Example Best Practices**:
- ✅ Include comment explaining what example demonstrates
- ✅ Show realistic arguments (not `foo`, `bar`, `baz`)
- ✅ Progress from simple to complex
- ✅ Cover common error cases if relevant

### 2.3 Progressive Help Disclosure

**Layered Help Approach**:
```bash
# Level 1: Brief help (default --help)
tool command --help
# Shows: description, usage, common options, 1-2 examples

# Level 2: Detailed help (--help-all or man page)
tool command --help-all
# Shows: full description, all options, all examples, edge cases

# Level 3: Command discovery (tool-level help)
tool --help
# Shows: list of all commands with brief descriptions
```

**When to Show Detail**:
- **Default help**: Show 80% use cases only
- **Advanced help**: Show all flags including rare ones
- **Inline hints**: Provide guidance when command fails

**Example - Layered Output**:
```bash
# Basic help (--help)
OPTIONS:
    -v, --verbose    Enable verbose output
    -o, --output     Specify output file
    -h, --help       Show this help

# Detailed help (--help-all)
OPTIONS:
    -v, --verbose              Enable verbose output
    -q, --quiet                Suppress all output except errors
    -o, --output FILE          Write output to FILE (default: stdout)
    --output-format FORMAT     Output format: text|json|yaml (default: text)
    --color WHEN               Colorize output: always|never|auto (default: auto)
    --log-level LEVEL          Log level: debug|info|warn|error (default: info)
    -h, --help                 Show basic help
    --help-all                 Show detailed help with all options
```

---

## 3 Error Message Formatting

### 3.1 Error Message Structure

**Standard Error Template**:
```
Error: <brief description>

<detailed explanation if needed>

<suggestion for resolution>

<additional context or documentation link>
```

**Example - Good Error Message**:
```
Error: Configuration file not found

Looked in these locations:
  - ./maceff.yml
  - ~/.maceff/config.yml
  - /etc/maceff/config.yml

Create a configuration file or specify location with --config flag.

See: https://docs.example.com/configuration
```

**Example - Bad Error Message**:
```
Error: ENOENT  ❌
```

**Severity Indicators**:
- `Error:` - Operation failed, cannot continue
- `Warning:` - Operation succeeded but with issues
- `Info:` - Informational message during success

### 3.2 Actionable Feedback

**Making Errors Actionable**:
1. **Explain what failed**: "Configuration file not found" not "ENOENT"
2. **Show what was attempted**: List paths searched, commands tried
3. **Suggest resolution**: "Create file X" or "Use --flag to specify Y"
4. **Provide escape hatch**: Link to docs, suggest alternative command

**Examples**:
```bash
# Good: Actionable error
Error: Invalid YAML in configuration file

File: /home/user/.maceff/config.yml
Line 15: mapping values are not allowed here

Check YAML syntax with: yamllint /home/user/.maceff/config.yml

# Bad: Vague error
Error: Configuration invalid  ❌
```

**Error Code Usage**:
- Use when error categories help automation/scripting
- Document error codes in help text or docs
- Keep codes simple: `E001`, `E002` or `CONFIG_NOT_FOUND`

### 3.3 User-Friendly Language

**Language Guidelines**:
- ✅ Use plain language: "File not found" not "ENOENT"
- ✅ Explain constraints: "Username must be 3-20 characters"
- ✅ Suggest solutions: "Try running with --force flag"
- ❌ Avoid jargon: "Container registry unavailable" not "HTTP 503 upstream"

**Technical Detail Balance**:
```bash
# Good: User-friendly with optional detail
Error: Cannot connect to server

Server: https://api.example.com
Reason: Connection timeout after 30 seconds

Check your network connection or try again later.

For detailed error information, run with --verbose flag.

# Bad: Technical dump without context
Error: requests.exceptions.ConnectTimeout:
HTTPSConnectionPool(host='api.example.com', port=443):
Max retries exceeded with url: /api/v1/status  ❌
```

---

## 4 Configuration Patterns

### 4.1 Configuration File Formats

**Format Selection Criteria**:

**YAML** - Good for:
- ✅ Human-edited configuration
- ✅ Comments and documentation
- ✅ Complex nested structures
- ⚠️ Watch for: Whitespace sensitivity, multiple versions

**JSON** - Good for:
- ✅ Machine-generated configuration
- ✅ Strict schema validation
- ✅ Language interoperability
- ⚠️ Watch for: No comments, verbose syntax

**TOML** - Good for:
- ✅ Simple flat configuration
- ✅ Sections and tables
- ✅ Less whitespace-sensitive than YAML
- ⚠️ Watch for: Less widespread adoption

**Example Configuration** (YAML):
```yaml
# maceff.yml
agent:
  name: example_agent
  moniker: ExampleAgent

paths:
  agent_root: /home/agent
  temp_root: /tmp/maceff

features:
  auto_mode: true
  hooks_enabled: true
```

### 4.2 Configuration Source Hierarchy

**Standard Precedence** (highest to lowest):
1. **Command-line flags** - Explicit user intent for this invocation
2. **Environment variables** - Session/shell configuration
3. **Project config file** - Project-specific settings (`./.maceff/config.yml`)
4. **User config file** - User preferences (`~/.maceff/config.yml`)
5. **System config file** - System defaults (`/etc/maceff/config.yml`)
6. **Built-in defaults** - Hardcoded fallbacks

**Merging Strategy**:
- **Scalars** (strings, numbers, booleans): Higher precedence overwrites
- **Lists**: Higher precedence replaces (unless tool supports append semantics)
- **Objects**: Recursive merge (higher precedence fields override)

**Example Hierarchy**:
```bash
# Default: auto_mode = true (built-in)
# System config: auto_mode = false (overrides default)
# User config: (not specified, uses system)
# Env var: MACF_AUTO_MODE=true (overrides system)
# CLI flag: --no-auto-mode (overrides env var)
# Final result: auto_mode = false
```

### 4.3 Configuration Validation

**Validation Timing**:
- **Early validation**: Check config before operations (fail fast)
- **Schema validation**: Validate structure and types
- **Semantic validation**: Check constraints and relationships

**Good Validation Error**:
```
Error: Invalid configuration

File: /home/user/.maceff/config.yml
Field: agent.name
Value: "my agent" (contains space)

Requirement: Agent name must be alphanumeric with underscores only
Valid examples: "my_agent", "agent_1", "example_agent"

Fix the configuration file and try again.
```

---

## 5 User Experience Guidelines

### 5.1 Progressive Disclosure

**Progressive Disclosure Principle**: Show users what they need when they need it, hide complexity until required.

**Implementation Patterns**:
```bash
# Beginner-friendly defaults
tool deploy
# Asks interactive questions, uses safe defaults

# Intermediate usage
tool deploy production
# Uses profile, shows progress

# Advanced usage
tool deploy production --config custom.yml --dry-run --verbose
# Full control with all flags
```

**Feature Layering**:
- **Core features**: Always visible in `--help`
- **Advanced features**: Shown in `--help-all` or documentation
- **Experimental features**: Hidden, require explicit opt-in

### 5.2 Sensible Defaults

**Good Defaults Checklist**:
- ✅ **Safe**: Won't destroy data or cause harm
- ✅ **Common**: Match 80% of use cases
- ✅ **Discoverable**: Documented in help text
- ✅ **Overridable**: User can change via flag or config

**Examples**:
```bash
# Good defaults
--output-format text      # Human-readable is default
--color auto              # Color when terminal supports it
--timeout 30              # Reasonable wait time
--log-level info          # Balance detail vs noise

# Bad defaults
--output-format json      ❌ (machine format, not human-friendly)
--color always            ❌ (breaks piping to files)
--timeout 3600            ❌ (1 hour is too long)
--log-level debug         ❌ (too noisy for normal usage)
```

### 5.3 Interactive vs Non-Interactive

**Detecting Interactive Context**:
```bash
# Interactive: stdin is a terminal
tool command
# Can prompt user, show spinners, use colors

# Non-interactive: stdin/stdout redirected or piped
tool command < input.txt > output.txt
# No prompts, no spinners, plain output
```

**Design Principles**:
- ✅ Detect TTY context (terminal vs pipe)
- ✅ Provide `--yes` flag to skip confirmations
- ✅ Respect `--quiet` flag in scripts
- ❌ Don't prompt in non-interactive context (will hang)

**Example Implementation**:
```bash
# Interactive mode
$ tool delete-user alice
Warning: This will permanently delete user 'alice'
Are you sure? [y/N]: _

# Non-interactive mode (auto-detected or --yes flag)
$ tool delete-user alice --yes
User 'alice' deleted successfully
```

---

## 6 Output Formatting

### 6.1 Human-Readable Output

**Formatting Techniques**:
- **Tables**: For structured data with multiple columns
- **Lists**: For simple item collections
- **Trees**: For hierarchical relationships
- **Key-value pairs**: For configuration/status display

**Table Example**:
```
Session ID    | Cycle | Status    | Started At
--------------|-------|-----------|--------------------
abc12345      | 42    | active    | 2025-11-23 16:34:04
def67890      | 41    | completed | 2025-11-23 14:22:15
ghi11223      | 40    | completed | 2025-11-23 10:05:33
```

**Color Usage**:
- ✅ Use color for emphasis (errors=red, success=green, warnings=yellow)
- ✅ Respect `--color` flag and `NO_COLOR` environment variable
- ✅ Ensure output is readable without color (don't rely solely on color)
- ❌ Don't overuse color (rainbow output is distracting)

### 6.2 Machine-Readable Output

**JSON Output**:
```json
{
  "sessions": [
    {
      "session_id": "abc12345",
      "cycle": 42,
      "status": "active",
      "started_at": "2025-11-23T16:34:04Z"
    },
    {
      "session_id": "def67890",
      "cycle": 41,
      "status": "completed",
      "started_at": "2025-11-23T14:22:15Z"
    }
  ],
  "total_count": 2
}
```

**Machine Output Guidelines**:
- ✅ Use standard formats (JSON, YAML, CSV)
- ✅ Include metadata (version, timestamp, status)
- ✅ Maintain stable schema across versions
- ✅ Use stderr for human messages, stdout for data

### 6.3 Output Mode Selection

**Standard Flags**:
```bash
--output-format text|json|yaml    # Explicit format selection
--json                            # Shorthand for --output-format json
--quiet                           # Suppress human-friendly messages
--verbose                         # Increase detail level
```

**Context Detection**:
```bash
# TTY (terminal): Human-readable with color
tool command

# Piped: Plain text without color
tool command | grep pattern

# Explicit: Always use specified format
tool command --output-format json
```

---

## 7 Integration with Framework Policies

### 7.1 Relationship to workspace_discipline.md

CLI development scripts follow workspace discipline patterns:

**Development Scripts Location**:
- **PA dev scripts**: `agent/public/dev_scripts/YYYY-MM-DD_HHMMSS_purpose.py`
- **SA dev scripts**: `agent/subagents/{role}/public/delegation_trails/YYYY-MM-DD_HHMMSS_{task}/dev_scripts/`

**CLI Production Code Location**:
- Package source: `{package}/src/{package}/cli/` or `{package}/src/{package}/__main__.py`
- NOT in dev_scripts (those are temporary validation/exploration)

### 7.2 Relationship to testing.md

CLI testing follows pragmatic TDD principles:

**CLI Test Coverage**:
- **4-6 focused tests** per command (not exhaustive permutations)
- **Test reality**: Common use cases and likely failures
- **Living documentation**: Tests show how CLI should be used

**Test Categories**:
1. **Smoke tests**: Command runs without errors
2. **Output tests**: Verify correct output format
3. **Error handling**: Test invalid inputs and error messages
4. **Integration tests**: Test with real file system / network

### 7.3 Language-Specific Implementation

This policy provides language-agnostic principles. For implementation details:

**Python**: See `lang/python/cli_python.md` (when created)
- argparse vs click vs typer
- Testing with pytest subprocess fixtures
- Entry point configuration

**Ruby**: See `lang/ruby/cli_ruby.md` (when created)
- Thor vs OptionParser
- Testing with rspec

**Go**: See `lang/go/cli_go.md` (when created)
- cobra vs flag package
- Testing with testify

**JavaScript/Node**: See `lang/javascript/cli_javascript.md` (when created)
- commander vs yargs
- Testing with jest

---

## 8 Anti-Patterns

### 8.1 Command Structure Anti-Patterns

**❌ Verb Soup** (too many top-level commands):
```bash
tool create-user
tool delete-user
tool list-users
tool update-user
tool create-project
tool delete-project
tool list-projects
# ... 50 more commands
```
- **Problem**: Overwhelming, no organization
- **Fix**: Use subcommands: `tool user create`, `tool user list`, `tool project create`

**❌ Flag Overload** (everything as flag):
```bash
tool deploy --environment prod --version v2.1 --timeout 300 --dry-run
```
- **Problem**: Natural positional arguments forced into flags
- **Fix**: `tool deploy prod v2.1 --timeout 300 --dry-run`

**❌ Inconsistent Naming**:
```bash
tool listUsers      # camelCase
tool delete-project # kebab-case
tool show_status    # snake_case
```
- **Problem**: No consistency, hard to predict
- **Fix**: Pick one convention (kebab-case recommended)

### 8.2 Help Text Anti-Patterns

**❌ No Examples**:
```
USAGE: tool command [OPTIONS] <arg>

OPTIONS:
    --verbose    Enable verbose output
```
- **Problem**: Users don't know how to actually use it
- **Fix**: Always include 2-4 concrete examples

**❌ Technical Jargon Dump**:
```
tool command - Instantiates ephemeral subprocess with IPC to daemon
```
- **Problem**: Incomprehensible to average user
- **Fix**: "tool command - Runs command and reports results to daemon"

**❌ Missing Argument Documentation**:
```
USAGE: tool command <arg1> <arg2> [arg3]
```
- **Problem**: No explanation of what arguments are
- **Fix**: Document each argument with description

### 8.3 Error Message Anti-Patterns

**❌ Cryptic Errors**:
```
Error: ENOENT
```
- **Problem**: User has no idea what failed
- **Fix**: "Error: Configuration file not found at ~/.maceff/config.yml"

**❌ Error Without Suggestion**:
```
Error: Invalid configuration
```
- **Problem**: User doesn't know how to fix it
- **Fix**: "Error: Invalid configuration. Check syntax with: yamllint config.yml"

**❌ Stack Trace Vomit**:
```
Traceback (most recent call last):
  File "/usr/lib/python3.9/site-packages/tool/main.py", line 42, in main
    config = load_config(config_path)
  File "/usr/lib/python3.9/site-packages/tool/config.py", line 18, in load_config
    with open(config_path) as f:
FileNotFoundError: [Errno 2] No such file or directory: '/home/user/.maceff/config.yml'
```
- **Problem**: Technical details obscure actual problem
- **Fix**: Show friendly error by default, stack trace only with `--verbose`

### 8.4 Configuration Anti-Patterns

**❌ No Configuration Hierarchy**:
- **Problem**: Only one config location, can't override
- **Fix**: Support multiple config sources with clear precedence

**❌ Silent Config Merging**:
- **Problem**: User doesn't know which config file won
- **Fix**: Provide `--verbose` or `--show-config` to reveal effective configuration

**❌ Validation After Operation**:
- **Problem**: Tool starts work then fails on invalid config
- **Fix**: Validate configuration early, fail fast

### 8.5 UX Anti-Patterns

**❌ Dangerous Defaults**:
```bash
tool delete-all-users    # No confirmation!
```
- **Problem**: Destructive operation with no safety check
- **Fix**: Require `--yes` flag or interactive confirmation

**❌ Prompt in Non-Interactive Context**:
```bash
tool deploy < automated-script.sh
Are you sure? [y/N]: _
# Hangs forever waiting for input
```
- **Problem**: Blocks automation
- **Fix**: Detect non-TTY, skip prompts or require `--yes`

**❌ Inconsistent Output Modes**:
```bash
tool command --json     # Sometimes works
tool command --format json  # Sometimes this is required
tool other --output-format json  # Different flag for same thing
```
- **Problem**: User can't predict flag names
- **Fix**: Standardize across all commands in tool

---

## 9 Evolution & Feedback

This policy evolves through:
- Learnings from MacEff CLI development (`macf_tools`, `maceff-init`)
- User feedback on CLI usability
- Cross-language pattern validation
- Discovery of new anti-patterns

**Principle**: Great CLIs are conversation partners—they guide users toward success through clear communication, thoughtful defaults, and actionable feedback. Design for humans first, machines second.

**When updating this policy**:
1. Extract patterns from real CLI implementations
2. Validate patterns work across multiple languages
3. Test that examples remain project-agnostic
4. Update related language-specific policies

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
