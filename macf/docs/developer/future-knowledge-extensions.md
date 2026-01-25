# Future Knowledge Base Extensions

**Status**: Planning (v0.4.0+)
**Created**: 2026-01-24
**Context**: Post-v0.3.3 ideas for extending hybrid search beyond policies

---

## Vision

Extend the hybrid search infrastructure beyond policies to become a comprehensive knowledge retrieval system for consciousness artifacts and project knowledge.

## Proposed Extensions

### 1. Learnings Search

**What**: Index and search accumulated learnings (`agent/private/learnings/`)

**Value**:
- Find relevant past discoveries during similar work
- Cross-reference learnings with policies they derive from
- Build knowledge graph connecting learnings → policies → practices

**Architecture**:
```
macf/hybrid_search/indexers/
├── policy_indexer.py      # Existing
└── learnings_indexer.py   # NEW
```

**CLI**:
```bash
macf_tools learnings search "sqlite-vec patterns"
macf_tools learnings index   # Build learnings index
```

### 2. Consciousness Artifact Search

**What**: Unified search across all CA types (CCPs, JOTEWRs, roadmaps, experiments)

**Value**:
- Find relevant past work when starting similar projects
- Temporal queries: "What did I work on in Cycle 340-350?"
- Cross-artifact linking for knowledge archaeology

**Types to Index**:
- Checkpoints (CCPs) - strategic state preservation
- Reflections (JOTEWRs) - wisdom synthesis
- Roadmaps - strategic plans
- Experiments - hypothesis-driven exploration
- Reports - completion narratives

**Architecture**:
```
macf/hybrid_search/indexers/
├── ca_indexer.py          # Unified CA indexer
└── extractors/
    ├── ccp_extractor.py
    ├── jotewr_extractor.py
    └── roadmap_extractor.py
```

### 3. Cross-Repository Search

**What**: Search across multiple agent repositories (e.g., ClaudeTheBuilder + MannyMacEff)

**Value**:
- Find solutions discovered by other agents
- Knowledge sharing between PA instances
- Federated search with namespace filtering

**Challenges**:
- Index synchronization across repos
- Privacy boundaries (private vs public CAs)
- Network latency for remote indices

### 4. Semantic Clustering & Topic Discovery

**What**: Automatic topic extraction and clustering of knowledge

**Value**:
- Discover emerging themes in learnings
- Identify knowledge gaps
- Generate "related topics" suggestions

**Approach**:
- Use embedding clustering (k-means, HDBSCAN)
- Extract topic keywords from clusters
- Build topic hierarchy

### 5. Temporal Queries

**What**: Time-aware search capabilities

**Examples**:
```bash
macf_tools search "TODO patterns" --after 2026-01-01 --before 2026-01-15
macf_tools search "compaction" --cycle-range 340-360
```

**Value**:
- Find work from specific time periods
- Track evolution of understanding over cycles
- Archaeological reconstruction

---

## Priority Assessment

| Extension | Effort | Value | Priority |
|-----------|--------|-------|----------|
| Learnings Search | Medium | High | P1 - v0.4.0 |
| CA Search | High | High | P2 - v0.4.0 |
| Temporal Queries | Low | Medium | P2 - v0.4.0 |
| Cross-Repo Search | High | Medium | P3 - v0.5.0 |
| Semantic Clustering | High | Medium | P3 - v0.5.0 |

---

## Implementation Notes

### Reuse Existing Infrastructure

The hybrid search framework is designed for extension:
- `BaseIndexer` handles LanceDB operations
- `AbstractExtractor` interface for domain-specific parsing
- `SearchService` supports namespace routing (already has `"policy"` namespace)

Adding new content types follows the same pattern:
1. Create `{type}_extractor.py` implementing `AbstractExtractor`
2. Create `{type}_indexer.py` using `BaseIndexer`
3. Register namespace in `SearchService`
4. Add CLI commands

### Privacy Considerations

- Private CAs (`agent/private/`) should not be indexed in shared indices
- Cross-repo search must respect privacy boundaries
- Consider encryption for sensitive content

### Performance Targets

- Index build: < 10s for typical agent corpus
- Search latency: < 50ms with warm service
- Memory: < 500MB for combined indices

---

## Related Work

- **v0.3.3**: LanceDB hybrid search for policies (foundation)
- **EXPERIMENT 005**: LanceDB validation (established performance baselines)
- **Phase 11.5**: Search service architecture (namespace routing)

---

## Next Steps

1. Validate learnings corpus size and structure
2. Prototype learnings extractor
3. Extend SearchService with `"learnings"` namespace
4. Evaluate clustering libraries (scikit-learn vs dedicated)
