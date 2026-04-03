---
name: box-drawing
description: Produce clean Unicode box-drawing character diagrams for architecture docs, READMEs, and technical documentation. Invoke when asked to draw diagrams, flowcharts, tables, or architectural layouts.
allowed-tools: Bash, Write
---

Create clean Unicode box-drawing diagrams and tables for documentation.

## Tooling

A Python helper `box_table.py` is available for programmatic table generation and alignment validation. Use it when building tables with many rows/columns to guarantee alignment.

```bash
# Generate a table programmatically
python3 -c "
from box_table import BoxTable
t = BoxTable(['Col1', 'Col2', 'Col3'])
t.add_row(['short', 'medium length', 'a much longer description'])
t.add_row(['x', 'y', 'z'])
print(t.render())
"

# Validate alignment with span analysis
python3 -c "
from box_table import BoxTable
t = BoxTable(['Col1', 'Col2'])
t.add_row(['test', 'data'])
print(t.annotate_spans())
"
```

**Styles**: `single` (default ┌─┐), `double` (╔═╗), `rounded` (╭─╮)

**Location**: The script should be at `agent/public/dev_scripts/box_table.py` or `/tmp/box_table.py`.

## Unicode Box-Drawing Character Reference

### Borders and connectors
```
Single:   ┌ ─ ┬ ─ ┐    Double:  ╔ ═ ╦ ═ ╗    Rounded: ╭ ─ ╮
          │   │   │              ║   ║   ║             │   │
          ├ ─ ┼ ─ ┤              ╠ ═ ╬ ═ ╣             ├ ─ ┤
          │   │   │              ║   ║   ║             │   │
          └ ─ ┴ ─ ┘              ╚ ═ ╩ ═ ╝             ╰ ─ ╯
```

### Arrows and tree connectors
```
→ ← ↑ ↓ ─▶ ◀─    Flow arrows
├── └──            Tree branches
│   ├── item       Tree continuation
│   └── last       Tree terminator
```

## Diagram Patterns

### Architecture box with flow
```
╭─────────────────╮
│   Component A   │
╰────────┬────────╯
         │
         ▼
╭─────────────────╮
│   Component B   │
╰─────────────────╯
```

### Side-by-side connection
```
┌──────────┐     ┌──────────┐
│ Module A │────▶│ Module B │
└──────────┘     └──────────┘
```

### Layered stack
```
┌─────────────────────────────┐
│         User Interface      │
├─────────────────────────────┤
│       Business Logic        │
├─────────────────────────────┤
│        Data Access          │
└─────────────────────────────┘
```

### Pipeline
```
input ─▶ stage1 ─▶ stage2 ─▶ stage3 ─▶ output
```

## Guidelines

1. **Use the tool for tables** — hand-alignment is error-prone beyond 3 columns
2. **Run span analysis** to validate alignment before committing
3. **Monospace only** — wrap in code blocks (triple backtick) in markdown
4. **Consistent width** — pad content to equal widths within a diagram
5. **Keep simple** — if >30 lines, split into multiple diagrams
6. **Rounded corners** (╭╮╰╯) for components, **square** (┌┐└┘) for data/containers
7. **Arrows**: ─▶ for data flow, ──── for associations
