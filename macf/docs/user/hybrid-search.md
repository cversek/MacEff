# Hybrid Search Policy Recommendations

End-to-end guide for using MACF's hybrid search system to get intelligent policy recommendations.

## Overview

MACF provides a hybrid search system combining:
- **Full-text search (FTS)** - Fast keyword matching on policy content
- **Semantic embeddings** - Meaning-based similarity using sentence-transformers
- **CEP question matching** - Matches queries to policy navigation guide questions

LanceDB's native hybrid search combines these retrieval methods, returning results ranked by semantic distance.

## Quick Start

### 1. Install Dependencies

```bash
pip install lancedb sentence-transformers
```

**Note:** These are optional dependencies. MACF core functionality works without them, but hybrid search requires both packages.

### 2. Build the Policy Index

```bash
macf_tools policy build_index
```

This creates a LanceDB index at `~/.maceff/policy_index.lance/` containing:
- Policy document embeddings
- CEP question embeddings

**Output:**
```
✅ Policy index built:
   Documents: 24
   Questions: 156
   Total time: 3.45s
   Database: /Users/user/.maceff/policy_index.lance/
```

### 3. Start the Search Service (Recommended)

For fast responses (~20ms vs ~8s):

```bash
macf_tools search-service start --daemon
```

The service keeps the embedding model loaded in memory, eliminating startup overhead.

### 4. Search for Policies

```bash
macf_tools policy recommend "How do I backup my TODO list?"
```

**Output:**
```
📚 Policy Recommendations:
🥇 📋 TODO_HYGIENE (0.327)
   → §10 "What is the TODO backup protocol?"
🥈 📋 CHECKPOINTS (0.503)
🥉 📋 CONTEXT_RECOVERY (0.576)
```

## Usage Patterns

### CLI Search

**Basic search:**
```bash
macf_tools policy recommend "How do I create a checkpoint?"
```

**With explanation breakdown:**
```bash
macf_tools policy recommend "How do I create a checkpoint?" --explain
```

**JSON output for scripting:**
```bash
macf_tools policy recommend "delegation patterns" --json --limit 3
```

### Hook Integration

Policy recommendations are automatically injected via the `UserPromptSubmit` hook. You'll see recommendations in the MACF system-reminder:

```
📚 Policy Recommendations:
🥇 📋 TODO_HYGIENE (0.327)
   → §10 "What is the TODO backup protocol?"
```

This is "ambient procedural awareness" - relevant policies surface automatically based on your query context.

### MCP Tool Integration

If using MCP (Model Context Protocol), three tools are available:

```
mcp__policy-search__search    - Search with hybrid scoring
mcp__policy-search__context   - Get CEP navigation for a policy
mcp__policy-search__details   - Get full policy content
```

## Understanding Output

### Distance Score

The number in parentheses (e.g., `0.327`) is the **semantic distance**:
- **Lower = more relevant** (closer in embedding space)
- **< 0.30** - Very strong match (CRITICAL tier)
- **0.30 - 0.45** - Good match (HIGH tier)
- **0.45 - 0.70** - Moderate match (MEDIUM tier)
- **> 0.70** - Weak match (shown but lower confidence)

### Confidence Tiers

Results are categorized by semantic similarity (1 - distance):
- **CRITICAL** (🔴): similarity ≥ 0.70 - Very high confidence
- **HIGH** (🟡): similarity ≥ 0.55 - Good confidence
- **MEDIUM** (📋): similarity < 0.55 - Moderate confidence

### Section Targeting (→ §N)

When you see `→ §5 "What is the backup protocol?"`, it means:
- The query matched a specific CEP Navigation Guide question
- Section 5 of that policy answers your question
- You can read just that section: `macf_tools policy read todo_hygiene --section 5`

This enables precise navigation to the relevant policy section.

## Troubleshooting

### "Search service unavailable, using direct search"

The warm search service isn't running. Either:
1. Start it: `macf_tools search-service start --daemon`
2. Or wait ~8s for direct search to complete (acceptable for occasional queries)

### "Policy recommend requires optional dependencies"

Install the required packages:
```bash
pip install lancedb sentence-transformers
```

### No recommendations found

Try:
- More specific keywords
- Use policy-related terms (TODO, backup, checkpoint, delegation, etc.)
- Ensure minimum 10 characters in query

### Stale results after policy changes

Rebuild the index:
```bash
macf_tools policy build_index
```

Then restart the search service if running:
```bash
macf_tools search-service stop
macf_tools search-service start --daemon
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Query Input                            │
│            "How do I backup my TODO list?"                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Search Service                           │
│              (warm daemon, ~20ms response)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 LanceDB Hybrid Search                       │
│         Combines vector + full-text retrieval               │
│                                                             │
│   ┌─────────────────┐    ┌─────────────────┐               │
│   │ Vector Search   │    │  FTS Search     │               │
│   │ (MiniLM-L6-v2)  │    │  (Keywords)     │               │
│   └────────┬────────┘    └────────┬────────┘               │
│            └──────────┬───────────┘                        │
│                       ▼                                     │
│              Unified Distance Score                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                CEP Question Matching                        │
│    Finds relevant sections via question similarity          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Ranked Results                            │
│    TODO_HYGIENE (0.327) → §10 "backup protocol"            │
└─────────────────────────────────────────────────────────────┘
```

## Performance

| Scenario | Latency | Notes |
|----------|---------|-------|
| With warm service | ~20-45ms | Recommended for interactive use |
| First query (cold) | ~8s | Model loading overhead |
| Index build | ~3-5s | One-time cost per rebuild |

## Related Commands

- `macf_tools policy list` - List available policies
- `macf_tools policy navigate <name>` - Show CEP navigation guide
- `macf_tools policy read <name>` - Read full policy content
- `macf_tools policy read <name> --section N` - Read specific section
- `macf_tools search-service start` - Start warm search service
- `macf_tools search-service status` - Check service status

## Version History

- **v0.3.3** - LanceDB backend, CEP question matching, search service
- **v0.3.2** - Initial hybrid search with sqlite-vec (deprecated due to ARM64 issues)
