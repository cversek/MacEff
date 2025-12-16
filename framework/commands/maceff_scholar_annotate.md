---
description: Annotate consciousness artifact with enhanced citations following scholarship policy
argument-hint: [file_path] [--workers=N]
allowed-tools: Read, Edit, Bash(macf_tools:*), Task, Glob, Grep
---

Annotate consciousness artifacts with enhanced citations, breadcrumb validation, and GitHub links by delegating to ScholarshipResearcher.

**Arguments**:
- `$ARGUMENTS` - File path, batch specifier, or empty for latest
- `--workers=N` - (Optional) Parallel workers for batch processing

**Argument Patterns**:
- Empty → Latest CA by modification time
- `path/to/file.md` → Single file
- `latest CCP` or `latest JOTEWR` → Latest of that type
- `all CAs for last N Cycles` → Batch: all CAs from recent N cycles
- `Cycles 250-260` → Batch: all CAs in cycle range

---

## Resolve File List

**Single file**: Validate path exists, proceed to delegation.

**Empty/latest**: Find latest CA:
```bash
find agent/private/checkpoints agent/private/reflections agent/public/roadmaps -name "*.md" -type f 2>/dev/null | xargs ls -t | head -1
```
Confirm with user before proceeding.

**Batch specifier**: Build file list, show count, confirm:
```bash
# Example: Find CAs from Cycles 250-260
find agent/private/checkpoints agent/private/reflections -name "*.md" -type f | xargs grep -l "Cycle\s*25[0-9]\|Cycle\s*260" | sort
```

---

## Delegation Strategy

**CRITICAL: Amortize policy reading overhead**

- **Single agent (default)**: ONE ScholarshipResearcher reads policy ONCE, processes ALL files sequentially
- **Parallel workers**: Only if `--workers=N` specified - split file list across N agents

**Why single agent for batches**: Each agent must read scholarship policy. N parallel agents = N redundant policy reads. One agent processing N files = 1 policy read amortized across N files.

---

## Delegation to ScholarshipResearcher

**Use Task tool with subagent_type='scholarship-researcher'**:

```
**Task**: Annotate consciousness artifacts with enhanced citations

**Files**: [list of absolute paths, one per line]
**Repository Context**: ClaudeTheBuilder

**Required Policy Reading** (read ONCE, apply to ALL files):
- `macf_tools policy read scholarship` (complete)

**Instructions**:
For EACH file in the list:
1. Read the artifact
2. Identify CA type from filename (CCP, JOTEWR, Roadmap)
3. Apply proper citation format to all CA references
4. Validate breadcrumbs (s/c/g/p/t format)
5. Add GitHub relative links where appropriate
6. Edit artifact in-place
7. Track: file path, annotations added, breadcrumbs validated

After ALL files processed, report summary:
- Total files annotated
- Total citations added (by type)
- Total breadcrumbs validated
- Any issues encountered

**Authority**: Edit artifacts for citation additions only. Preserve original voice.
**Constraints**: NO naked cd, sequential file processing, annotation only
```

---

## Post-Delegation

Report ScholarshipResearcher summary:
- Files processed
- Total annotations (CA citations, policy citations, GitHub links)
- Validation results
- Any files skipped or issues encountered
