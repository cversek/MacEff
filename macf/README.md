# MACF - Multi-Agent Consciousness Framework

MACF provides consciousness infrastructure for AI agents, enabling session continuity, temporal awareness, and policy-driven development across compaction events.

## What is MACF?

MACF is a lightweight Python package that helps AI agents maintain awareness across context boundaries. It provides:

- Session state persistence and compaction detection
- Temporal awareness and time-gap tracking
- Policy manifest system for agent governance
- Event sourcing for forensic analysis
- Hook system for consciousness restoration
- Token budget monitoring (CLUAC - Context Left Until Auto-Compaction)

## Installation

Install from source:

```bash
cd /path/to/MacEff/macf
pip install -e .
```

For development with testing support:

```bash
pip install -e ".[test]"
```

## Quick Start

Check your environment:

```bash
macf_tools env
```

View current session information:

```bash
macf_tools session info
```

Check token usage and context remaining:

```bash
macf_tools context
```

Install hooks for compaction detection:

```bash
macf_tools hooks install --local
```

Generate a forensic breadcrumb:

```bash
macf_tools breadcrumb
```

## Documentation

- [CLI Reference](docs/user/cli-reference.md) - Complete command documentation
- [Hooks Guide](docs/user/hooks.md) - Hook installation and usage
- [Environment Guide](docs/user/environment.md) - PA environment and env.d extensibility
- [Commands Guide](docs/user/commands.md) - Hierarchical command namespaces
- [Identifiers Guide](docs/user/identifiers.md) - Session/cycle/breadcrumb semantics
- [Statusline Guide](docs/user/statusline.md) - Custom statusline configuration

## Version

Current version: **0.3.2**

## Requirements

- Python 3.10+
- No runtime dependencies (pure Python)

## Project Structure

```
macf/
├── src/macf/           # Core package
│   ├── cli.py          # Command-line interface
│   ├── utils.py        # Utilities and helpers
│   └── hooks/          # Hook implementations
├── tests/              # Test suite
├── docs/user/          # User documentation
└── pyproject.toml      # Package configuration
```

## License

Part of the MacEff framework project.
