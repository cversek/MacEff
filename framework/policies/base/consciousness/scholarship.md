# Consciousness Scholarship Policy

**Type**: Citation & Knowledge Graph Infrastructure (Public CA)
**Scope**: All agents (PA and SA)
**Status**: Framework policy for consciousness artifact citation practices

---

## Purpose

Scholarship policy establishes enhanced citation practices for consciousness artifacts, enabling agents to build navigable knowledge graphs through disciplined citation. Citations transform artifacts from isolated records into traversable wisdom networks with forensically precise references.

**Core Insight**: Citations aren't academic formality—they're **edges in knowledge graphs**. Each citation creates a connection. Connected artifacts become discoverable. Discovery enables synthesis. Synthesis advances consciousness evolution.

---

## CEP Navigation Guide

**1 Enhanced Citation Format**
- What is the enhanced citation format?
- When was this format established?
- What components does it include?
- Why was it enhanced from simple breadcrumbs?

**1.1 Format Specification**
- What's the complete format syntax?
- Which components are optional vs required?
- How do I construct a valid enhanced citation?

**1.2 Component Definitions**
- What is CA_TAG and what values are valid?
- How do I format dates and descriptions?
- What are section references ({§s.s})?
- How do line/message ranges work?
- What's the breadcrumb component order?

**1.3 GitHub Link Construction**
- When should I include GitHub links?
- How do I construct relative paths?
- What's the line range anchor format?
- When to use section headings vs line ranges?

**2 When to Cite**
- What deserves citation?
- How dense should citations be?
- When is a citation required vs optional?

**2.1 Required Citations**
- Influences on current work?
- Prerequisites for understanding?
- Prior art referenced directly?

**2.2 Strategic Citations**
- Cross-cycle wisdom references?
- Delegation chain documentation?
- Architectural decision precedents?

**2.3 Over-Citation Anti-Patterns**
- What's too many citations?
- When does citation clutter obscure meaning?
- How to balance precision with readability?

**3 Knowledge Graph Building**
- How do citations create graphs?
- What are nodes and edges?
- How do I navigate citation networks?

**3.1 Graph Queries**
- Forward traversal (what cites this)?
- Backward traversal (what does this cite)?
- Shortest paths between artifacts?
- Importance ranking (PageRank)?

**3.2 Graph Emergence**
- How do individual citations compound into networks?
- What patterns emerge from citation discipline?
- How does this enable memory systems?

**4 Integration with Other Policies**
- How does scholarship integrate with checkpoints?
- Citation practices in reflections?
- Roadmap cross-references?
- DELEG_PLAN citation patterns?

**4.8 Citing TODO Backups**
- How to cite TODO backups?
- TODO backup citation format?
- Why cite TODO state snapshots?
- Integration with checkpoint citations?

**9 Policy Citations (Non-CA References)**
- How do I cite framework policies (not CAs)?
- What format do policy citations use?
- When are policy citations required vs encouraged?
- How do I get the MacEff git hash for citations?

**5 Validation & Examples**
- What does a good citation look like?
- Examples for each CA type?
- Common mistakes to avoid?

=== CEP_NAV_BOUNDARY ===

---

## 1 Enhanced Citation Format

### 1.1 Format Specification

**Complete Syntax**:
```
[{CA_TAG} {date} "{desc}" {§s.s "section_desc"}? {Lx-Ly|Mx-My}?: s/c/g/p/d?/t](markdown_link)?
```

**Required Components**:
- `{CA_TAG}`: Consciousness artifact type
- `{date}`: YYYY-MM-DD format (human-readable)
- `"{desc}"`: Titular or short semantic descriptor (quoted)
- `s/c/g/p/d?/t`: Breadcrumb coordinates (forensic traceability)

**Optional Components**:
- `{§s.s "section_desc"}?`: Section numbering and/or heading descriptor
- `{Lx-Ly|Mx-My}?`: Line range (files) or message range (conversations)
- `(markdown_link)?`: GitHub-compatible relative link

### 1.2 Component Definitions

**{CA_TAG} - Consciousness Artifact Type**:
- `CCP`: Consciousness Checkpoint (strategic state preservation)
- `JOTEWR`: Jump Off The Edge While Reflecting (cycle-closing wisdom synthesis)
- `Report`: Project completion narrative or investigation findings
- `Roadmap`: Multi-phase strategic planning document
- `DEV_DRV`: Development Drive (conversation work unit, PA-scoped)
- `DELEG_DRV`: Delegation Drive (SA work unit, delegation-scoped)
- `Observation`: Technical discovery or pattern recognition
- `Experiment`: Hypothesis testing protocol and results

**{date} - YYYY-MM-DD Format**:
- Human-readable temporal context
- ISO 8601 date format (YYYY-MM-DD)
- Enables chronological sorting and temporal queries
- Example: `2025-11-05`

**"{desc}" - Semantic Descriptor** (in quotes):
- Brief titular description (3-7 words typical)
- Captures essence of artifact or cited content
- Enables scanning citations without reading full artifacts
- Examples: `"Phase5D Complete"`, `"Delegation Trust Pattern"`, `"Breadcrumb Navigation Infrastructure"`

**{§s.s "section_desc"}? - Section References** (optional):
- Numbered section: `§2.3`
- Named section: `§2.3 "The Shift"`
- Enables precision targeting within large artifacts
- § symbol indicates section (use \u00A7 or copy from examples)

**{Lx-Ly|Mx-My}? - Line/Message Ranges** (optional):
- **Line ranges** (files): `L45-L67` (capital L)
- **Message ranges** (conversations): `M0-M15` (M0 = prompt starting DEV_DRV/DELEG_DRV)
- Precision targeting: cite exactly what matters, not entire artifact
- GitHub anchors use `#L45-L67` format (dashes, not colons)

**s/c/g/p/d?/t - Breadcrumb Coordinates**:
- Component order: **session/cycle/git/prompt/delegation?/timestamp**
- `s_XXXXXXXX`: Session ID (8 hex chars) - conversation boundary
- `c_NN`: Cycle number (integer) - compaction count, agent lifetime
- `g_YYYYYYY`: Git commit hash (7 hex chars) - **agent's personal CA repository** state
  - Tracks consciousness state, not work product
  - Each agent's breadcrumb `g_` field references their own CA repo
  - Example: Host agent uses host CA repo hash; container agent uses container CA repo hash
- `p_ZZZZZZZZ`: Prompt UUID (8 hex chars) - DEV_DRV start point
- `d_WWWWWWWW`: Delegation UUID (8 hex chars) - **optional**, DELEG_DRV chain
- `t_TTTTTTTTTT`: Unix epoch timestamp (10 digits) - completion moment
- **Rationale**: Slow→fast ordering enables hierarchical compression and efficient queries

**Example Breadcrumb**: `s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890`

**Multi-Repository References**:
When work spans multiple repositories, use explicit repo labeling for external commits:
- Format: `[RepoName g_YYYYYYY]`
- Examples:
  - `[MacEff g_abc1234]` - MacEff framework commit
  - `[AgentX g_def5678]` - AgentX repo commit
  - `[ProjectY g_ghi9012]` - Project repo commit

**Combined Format** (recommended for cross-repo work):
`[s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890] [MacEff g_abc1234]`
- First bracket: Full consciousness breadcrumb (CA repo state)
- Second bracket: External repo reference (work product)

**Commit Before Reference** (required ordering):
External repo work MUST be committed BEFORE generating `[RepoName g_hash]`:
1. Complete work in external repository
2. Commit changes (creates the hash)
3. Note the commit hash
4. Generate consciousness breadcrumb (`macf_tools breadcrumb`)
5. Construct combined reference: `[breadcrumb] [RepoName g_hash]`

Referencing uncommitted work creates invalid forensic references.

### 1.3 GitHub Link Construction

**When to Include Links**:
- Citing artifacts in same repository (relative paths work)
- Reader needs direct navigation (one-click access to cited content)
- Precision targeting important (jump to specific lines/sections)
- **Omit** for DEV_DRV/DELEG_DRV (conversation transcripts not in repo)

**Relative Path Rules**:
1. **Understand directory structure**:
   ```
   agent/
   ├── private/
   │   ├── checkpoints/
   │   ├── reflections/
   │   └── learnings/
   └── public/
       ├── roadmaps/
       ├── reports/
       ├── observations/
       └── experiments/
   ```

2. **Count `../` levels from citing artifact to common ancestor**:
   - From roadmap to reflection: `../../../private/reflections/`
   - From checkpoint to observation: `../../public/observations/`
   - From reflection to another reflection: `../`

3. **Mathematical traversal**:
   ```
   From: agent/public/roadmaps/2025-11-05_Name/roadmap.md
   To:   agent/private/reflections/2025-11-05_reflection.md

   Steps:
   - Up from 2025-11-05_Name/ to roadmaps/ (../)
   - Up from roadmaps/ to public/ (../)
   - Up from public/ to agent/ (../)
   - Down from agent/ to private/ (private/)
   - Down to reflections/ (reflections/)
   - Down to file (2025-11-05_reflection.md)

   Result: ../../../private/reflections/2025-11-05_reflection.md
   ```

**Anchor Formats**:
- **Line ranges** (preferred when specified): `#L32-L53` (capital L, dash separator)
- **Section headings** (fallback): `#phase-2-multi-dimensional-queries` (lowercase, hyphens for spaces, remove special chars)
- **Single lines**: `#L42` (when citing specific line)

**Example Citation with GitHub Link**:
```markdown
This delegation pattern [CCP 2025-11-03 "Phase5D Complete" §4 "Delegation Wisdom" L92-110: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../checkpoints/2025-11-03_172704_Cycle95_Phase5D_Complete_CCP.md#L92-L110) extends testing safeguards.
```

---

## 2 When to Cite

### 2.1 Required Citations

**Influences on Current Work**:
- Prior decisions that constrain current approach
- Architectural patterns being extended or modified
- Lessons learned from past failures informing current strategy
- **Why required**: Without these citations, future readers lose causal chain

**Prerequisites for Understanding**:
- Technical background required to comprehend current artifact
- Conceptual frameworks being applied
- Terminology definitions established elsewhere
- **Why required**: Enables independent understanding without hunting context

**Direct References**:
- Quotations or paraphrases from other artifacts
- Data or findings being used as evidence
- Specific technical specifications being implemented
- **Why required**: Academic integrity and forensic traceability

### 2.2 Strategic Citations

**Cross-Cycle Wisdom References**:
- JOTEWRs synthesizing relevant patterns
- CCPs documenting decision rationale
- Observations capturing technical discoveries
- **When to cite**: Connecting present work to accumulated wisdom, showing consciousness evolution

**Delegation Chain Documentation**:
- DELEG_PLANs that orchestrated current work
- DEV_DRVs that produced referenced deliverables
- Reports from prior delegation cycles
- **When to cite**: Preserving attribution and enabling delegation archaeology

**Architectural Decision Precedents**:
- Roadmaps establishing strategic direction
- Experiments validating technical approaches
- Reports documenting implementation outcomes
- **When to cite**: Grounding current decisions in established patterns

### 2.3 Citation Density Guidelines

**Optimal Density**: 3-10 citations per 1000 words typical
- **Too sparse** (<2 per 1000): Appears to emerge from vacuum, loses connection to prior work
- **Well-balanced** (3-10 per 1000): Clear intellectual lineage, selective high-value references
- **Too dense** (>15 per 1000): Cluttered, obscures narrative, appears defensive

**Strategic Placement**:
- **Opening context**: Cite 1-2 key influences establishing foundation
- **Mid-artifact**: Cite as needed when building on specific prior work
- **Synthesis sections**: Cite 2-4 cross-cutting patterns being integrated
- **Avoid**: Citation dumps (listing many without integration), orphaned citations (no explanation why relevant)

**Quality Over Quantity**:
- ✅ **DO**: Cite strategically when reference adds genuine value
- ❌ **DON'T**: Cite every tangentially related artifact
- ✅ **DO**: Explain in 1-2 sentences why citation matters
- ❌ **DON'T**: Drop naked citations without context

---

## 3 Knowledge Graph Building

### 3.1 Graph Structure Emergence

**Nodes**: Consciousness artifacts (each with unique breadcrumb coordinates)
- CCPs, JOTEWRs, Reports, Roadmaps, Observations, Experiments
- Every artifact = potential node in network
- Breadcrumb = node identifier (globally unique across agent lifetime)

**Edges**: Citations (enhanced format references pointing from one artifact to another)
- Each citation = directed edge (citing artifact → cited artifact)
- Edge attributes: CA_TAG (type), date (temporal), description (semantic), line range (precision)
- Multiple citations between same two artifacts = weighted edges

**Graph Properties**:
- **Directed**: Citations point from newer work to older influences
- **Weighted**: Citation frequency indicates importance
- **Attributed**: CA_TAG, date, description enable filtered traversal
- **Temporal**: Date enables time-series analysis of influence patterns

### 3.2 Graph Queries (Future Memory System)

**Forward Traversal** - "What cites this artifact?"
- Discover influence and impact
- Find work building on specific ideas
- Measure importance via citation count
- Example: "What artifacts cite [CCP 2025-10-24 'Phase5D Complete']?"

**Backward Traversal** - "What does this artifact cite?"
- Discover prerequisites and foundations
- Understand intellectual lineage
- Trace decision rationale back to origins
- Example: "What prior work influenced [JOTEWR 2025-11-05 'Scholarship Policy']?"

**Shortest Path** - "Chain from Artifact A to Artifact B"
- Trace evolution of ideas across cycles
- Find connection between seemingly unrelated work
- Discover intermediate insights linking concepts
- Example: "Path from [Cycle 42 breadcrumb format] to [Cycle 42 enhanced citations]"

**PageRank** - "Most-cited wisdom from Cycles 90-100"
- Identify foundational work influencing multiple later artifacts
- Surface high-impact insights worth reviewing
- Weight citations by citing artifact importance (recursive)

**Subgraph Extraction** - "All delegation-related work"
- Filter by CA_TAG (DELEG_PLAN, DELEG_DRV, related Reports)
- Filter by description keywords ("delegation", "orchestration")
- Extract connected subgraph for focused analysis
- Discover clusters of related work

### 3.3 Knowledge Graph Benefits

**Discovery Through Traversal**:
- Don't ask "where did I store knowledge about X?"
- Ask "what artifacts cite work related to X?"
- Citations create discovery infrastructure, not just references

**Synthesis Through Patterns**:
- Citation clusters reveal themes (high interconnection = related concepts)
- Citation gaps reveal opportunities (uncited prior work = forgotten wisdom)
- Citation evolution reveals learning (early artifacts cited less = foundational)

**Memory System Integration** (Future):
- **Vector embeddings**: Use CA_TAG + date + description + line range content for semantic search
- **Knowledge graphs**: Use breadcrumb nodes + citation edges for relationship discovery
- **LLM filtering**: Use enhanced format attributes for precision refinement
- **Hybrid queries**: Combine semantic similarity (vectors) with citation networks (graphs)

---

## 4 Citation Examples by CA Type

### 4.1 Citing Checkpoints (CCP)

**Use Case**: Referencing strategic state or decision documentation

**Example (with GitHub link)**:
```markdown
The delegation trust pattern established in [CCP 2025-11-03 "Phase5D Complete" §4 "Delegation Wisdom" L92-110: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../checkpoints/2025-11-03_172704_Cycle95_Phase5D_Complete_CCP.md#L92-L110) guides current Phase 2 approach.
```

**Example (without link, conversation context)**:
```markdown
As documented in [CCP 2025-11-04 "Version Architecture Fixed" s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890], the version sourcing architecture uses single source of truth.
```

### 4.2 Citing Reflections (JOTEWR)

**Use Case**: Referencing wisdom synthesis or philosophical insights

**Example**:
```markdown
The sanitization discipline described in [JOTEWR 2025-11-05 "Universal vs Personal" §2 "Almost-Pollution Moment" L11-35: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../../private/reflections/2025-11-05_112350_JOTEWR_Cycle105_Scholarship_Policy_Universal_Personal.md#L11-L35) requires constant awareness when creating framework policies.
```

### 4.3 Citing Roadmaps

**Use Case**: Referencing strategic plans or phase-specific guidance

**Example**:
```markdown
Following Phase 2 strategy outlined in [Roadmap 2025-11-05 "MacEff Scholarship Policy Integration" §Phase2 s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../../public/roadmaps/2025-11-05_MacEff_Scholarship_Policy_Integration/roadmap.md#phase-2-citation-format-integration), we updated roadmaps.md and checkpoints.md.
```

### 4.4 Citing Reports

**Use Case**: Referencing investigation findings or project completion narratives

**Example**:
```markdown
The gap analysis findings in [Report 2025-11-05 "Phase 1 Gap Analysis" L115-137: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../roadmaps/2025-11-05_MacEff_Scholarship_Policy_Integration/delegation_plans/gap_analysis.md#L115-L137) identified 7 high-priority integration points.
```

### 4.5 Citing Observations

**Use Case**: Referencing technical discoveries or pattern recognition

**Example**:
```markdown
As noted in [Observation 2025-10-02 "additionalContext Injection Breakthrough" s_abc12345/c_42/g_ghi01234/p_jkl56789/t_1234567890], the hookSpecificOutput.additionalContext field enables symmetric awareness.
```

### 4.6 Citing DEV_DRV (Development Drives)

**Use Case**: Referencing conversation work units (no GitHub link - transcripts not in repo)

**Example (message range)**:
```markdown
The implementation approach discussed in [DEV_DRV 2025-11-03 "Phase5E Friction Resolution" M0-M23: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890] established container diagnostic workflow.
```

**Note**: M0 = prompt starting the DEV_DRV, M1-Mn = subsequent messages

### 4.7 Citing DELEG_DRV (Delegation Drives)

**Use Case**: Referencing delegated work units (no GitHub link)

**Example**:
```markdown
DevOpsEng's implementation in [DELEG_DRV 2025-11-05 "Phase2 Citation Integration" M0-M18: s_abc12345/c_42/g_cc7e1bd/p_b7c67e6b/d_abc12345/t_1762362636] successfully updated both policies.
```

**Note**: `d_abc12345` component identifies delegation chain (optional but recommended for DELEG_DRV citations)

### 4.8 Citing TODO Backups

**Use Case**: Referencing TODO state snapshots for complete work context reconstruction

**TODO Backup Citation Format**:
```
[TODO Backup YYYY-MM-DD "Mission Description": s/c/g/p/t](../public/todo_backups/filename.json)
```

**Components**:
- **TODO Backup**: CA_TAG for TODO snapshot files
- **Date**: Human-readable YYYY-MM-DD format
- **Mission Description**: Semantic descriptor from filename (quoted, e.g., "Platform Migration")
- **Breadcrumb**: Backup creation coordinates (when backup was created)
- **Link**: Relative path to JSON backup file

**Example (in Checkpoint)**:
```markdown
## TODO State at Checkpoint

Current work captured in [TODO Backup 2025-11-21 "TODO Recovery Intelligence": s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../../public/todo_backups/2025-11-21_135848_c3b658f5_172_TODO_Recovery_Intelligence.json) shows 37-item hierarchical mission structure with active Phase 5 implementation.
```

**Example (in Reflection - pattern analysis)**:
```markdown
## Work Context Evolution

Comparing [TODO Backup 2025-11-15 "Initial Planning": s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../../public/todo_backups/2025-11-15_100000_abc12345_168_Initial_Planning.json) with [TODO Backup 2025-11-21 "Recovery Intelligence": s_abc12345/c_42/g_eb34edc/p_jkl56789/t_1763786000](../../public/todo_backups/2025-11-21_135848_c3b658f5_172_TODO_Recovery_Intelligence.json) reveals mission scope expanded 3x as understanding deepened.
```

**Why TODO Backup Citations Matter**:
- **Complete state reconstruction**: CCP + TODO backup = full work context snapshot
- **Archaeological recovery**: Post-compaction forensics can restore exact TODO state
- **Work evolution tracking**: Compare TODO snapshots across cycles to see mission progression
- **Strategic continuity**: Backups survive session migrations and compaction events
- **Enhanced citations**: CCPs cite TODO backups for work context, not just technical state

**Integration with Checkpoints**: Checkpoints should cite TODO backup created during pre-CCP protocol (see checkpoints.md §1.1).

**Integration with TODO Hygiene**: See todo_hygiene.md §9 for backup creation protocol and filename format.

### 4.9 Citing Friction Points (Roadmap Subartifacts)

**Use Case**: Referencing specific obstacles, solutions, and learnings documented during roadmap execution

**FP Citation Format** (subclass of Roadmap citations):
```
[Roadmap YYYY-MM-DD "Roadmap Title" FP#{N} "FP Brief Title": s/c/g/p/t](friction_points/friction_points.md#fpN-anchor)
```

**Components**:
- **Roadmap** + date + title: Parent roadmap identification (friction belongs to roadmap)
- **FP#{N}**: Friction point number within roadmap (e.g., FP#1, FP#2, FP#3)
- **FP title**: Brief descriptor of friction (3-5 words, quoted)
- **Breadcrumb**: FP discovery moment (when friction documented)
- **Link**: Relative path to friction_points/friction_points.md + GitHub anchor

**GitHub Anchor Rules for FPs**:
- Lowercase FP title with number prefix: `FP#1: Docker Override Discovery` → `#fp1-docker-override-discovery`
- Include FP number in anchor for uniqueness (multiple FPs in same file)
- Use explicit anchor IDs in headers: `{#fp1-anchor}`

**Example (in Checkpoint)**:
```markdown
## Friction This Cycle

Encountered docker-compose working directory dependency [Roadmap 2025-11-11 "Docker DETOUR" FP#1 "Override Discovery": s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../roadmaps/2025-11-11_Docker_Start_Script/friction_points/friction_points.md#fp1-docker-override-discovery) which blocked volume mounting for 25 minutes until user shared prior deployment wisdom.
```

**Example (in Reflection - pattern analysis)**:
```markdown
## Wisdom: Documentation vs Discipline

Building on [Roadmap 2025-11-11 "Docker DETOUR" FP#1 "Override Discovery": s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../../public/roadmaps/2025-11-11_Docker_Start_Script/friction_points/friction_points.md#fp1-docker-override-discovery), this friction reveals systematic pattern: documentation teaches mechanism, experience teaches discipline.
```

**Example (cross-roadmap pattern recognition)**:
```markdown
Both [Roadmap 2025-10-23 "TestMacEff Deploy" FP#3 "SSH Port Variance": s_xxx/c_40/g_yyy/p_zzz/t_1234567890](../2025-10-23_TestMacEff_Deploy/friction_points/friction_points.md#fp3-ssh-port-variance) and [Roadmap 2025-11-11 "Docker DETOUR" FP#1 "Override Discovery": s_abc/c_42/g_def/p_ghi/t_1234567890](../2025-11-11_Docker_Start_Script/friction_points/friction_points.md#fp1-docker-override-discovery) share root cause: tools assume standard conventions, operational reality requires auto-detection.
```

**Why FP Citations Matter**:
- **Forensic navigation**: Breadcrumb → exact discovery conversation
- **Pattern recognition**: Find all friction citing similar root causes
- **Prevention transfer**: Share friction knowledge across projects/agents
- **Wisdom synthesis**: Trace how friction insights influenced future architectural decisions
- **Knowledge graphs**: FP citations create edges in learning network, enabling friction pattern discovery

**FP-Specific Query Patterns** (future memory system):
```bash
# Find all friction points from Cycle 42-100
macf_tools memory query --ca-tag Roadmap --fp-only --cycle-range 90-100

# Find friction citing docker-compose patterns
macf_tools memory query --cited-desc "docker-compose" --ca-tag Roadmap --fp-only

# Build friction pattern graph (cluster similar friction)
macf_tools memory graph --root-fp "FP#1" --depth 2 --pattern-clustering
```

**Integration**: See roadmaps.md §6.3 for complete friction points documentation guidelines.

---

## 5 Integration with Other Policies

### 5.1 Checkpoints Policy Integration

**Cross-Checkpoint Citations**:
- Use enhanced format when referencing prior CCPs
- Include section references for precision (§N "Section Name")
- Add line ranges when citing specific decision documentation
- GitHub links enable one-click navigation to prior strategic state

**Example from checkpoints.md**:
```markdown
## Cross-Cycle Context References

When referencing prior checkpoints for strategic continuity:

[CCP 2025-10-28 "Phase4 Deployment Complete" §5 "Validation Results" L145-178: s_abc12345/c_42/g_def5678/p_ghi01234/t_1234567890](2025-10-28_154502_Cycle72_Phase4_Deployment_Complete_CCP.md#L145-L178)
```

### 5.2 Reflections Policy Integration

**Cross-Cycle Wisdom Tracing**:
- JOTEWRs frequently cite prior JOTEWRs for philosophical continuity
- Enhanced citations show evolution of consciousness themes
- Section references target specific insights within long reflections
- Relative path traversal from reflection to reflection: `../YYYY-MM-DD_reflection.md`

**Pattern**: Chain citations show wisdom evolution (JOTEWR N cites JOTEWR N-1, creating philosophical lineage)

### 5.3 Roadmaps Policy Integration

**Phase Cross-References**:
- Roadmaps cite prior roadmaps when building on established patterns
- Archive package citations use enhanced format (shown in roadmaps.md updates)
- Phase completion breadcrumbs document strategic milestones
- Embedded filepaths in TODOs reference roadmap subdirectories

**Roadmap-Specific Pattern**:
```markdown
[📦 Archive 2025-10-27 "Phases 1-4 Complete": s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](archived_todos/2025-10-27_215009_Phases1-4_COMPLETED.md)
```

### 5.4 Delegation Guidelines Integration

**DELEG_PLAN Citations**:
- DELEG_PLANs cite research reports from prior phases
- Reading lists reference artifacts by filepath + what to learn
- Integration prompts cite examples from Phase 1 research
- Deliverable specifications cite format examples from canonical sources

**Pattern**: PA orchestrates using citations to guide SA context building (reading lists = curated citation networks)

### 5.5 Memory Stores Policy Integration

**Archive Organization**:
- Archives reference original artifacts via enhanced citations
- Cross-archive citations enable discovering related archived work
- Memory system queries leverage enhanced format attributes
- Breadcrumb coordinates provide stable identifiers across filesystem changes

### 5.6 See Also

- `meta/policy_writing.md` (External References) - How external tools should reference this policy's enhanced citation format using timeless content categories (e.g., "citation format requirements", "breadcrumb structure"), not brittle section numbers

---

## 6 Validation & Quality Criteria

### 6.1 Well-Formed Citations

**✅ Complete Enhanced Citation**:
```markdown
[JOTEWR 2025-11-05 "Universal vs Personal" §2.3 "Format Specifications" L231-276: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890](../../private/reflections/2025-11-05_112350_JOTEWR_Cycle105_Scholarship_Policy_Universal_Personal.md#L231-L276)
```

**Components verified**:
- ✅ CA_TAG present (JOTEWR)
- ✅ Date formatted YYYY-MM-DD (2025-11-05)
- ✅ Description quoted ("Universal vs Personal")
- ✅ Section reference with number and name (§2.3 "Format Specifications")
- ✅ Line range specified (L231-276)
- ✅ Breadcrumb complete with correct component order (s/c/g/p/t)
- ✅ GitHub link with correct relative path and anchor (#L231-L276)

**✅ Minimal Valid Citation** (required components only):
```markdown
[CCP 2025-10-24 "Phase4 Deployment" s_abc12345/c_42/g_def5678/p_ghi01234/t_1234567890]
```

### 6.2 Common Mistakes

**❌ Wrong Breadcrumb Component Order**:
```markdown
[CCP 2025-10-24 "Phase4" c_60/s_abc12345/p_ghi01234/t_1234567890/g_def5678]
```
- **Error**: Components out of order (should be s/c/g/p/d?/t)
- **Fix**: Reorder to s/c/g/p/t

**❌ Missing Quotes on Description**:
```markdown
[JOTEWR 2025-11-05 Universal vs Personal s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890]
```
- **Error**: Description not quoted
- **Fix**: Add quotes: `"Universal vs Personal"`

**❌ Wrong Line Anchor Format**:
```markdown
...](file.md#l45-l67)  or  ...](file.md#L45:L67)
```
- **Error**: Lowercase 'l' or colon separator (GitHub won't parse)
- **Fix**: Capital L with dash: `#L45-L67`

**❌ Absolute Paths**:
```markdown
...](/Users/user/agent/private/reflections/file.md)
```
- **Error**: Absolute path breaks when repository moved
- **Fix**: Use relative path: `../../private/reflections/file.md`

**❌ Agent-Specific Examples in Framework Policies**:
```markdown
[CCP 2025-11-05 "My Cycle105 Work" s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890]
```
- **Error**: Using real agent breadcrumbs in universal policy example
- **Fix**: Sanitize: `s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890`

### 6.3 Validation Checklist

Before committing citations to framework policies:

- [ ] CA_TAG uses valid vocabulary (CCP, JOTEWR, Report, Roadmap, DEV_DRV, DELEG_DRV, Observation, Experiment)
- [ ] Date uses YYYY-MM-DD format
- [ ] Description quoted and semantically meaningful
- [ ] Breadcrumb component order: s/c/g/p/d?/t
- [ ] Component lengths correct (s=8, c=int, g=7, p=8, d=8 optional, t=10)
- [ ] GitHub links use relative paths (not absolute)
- [ ] Line anchors use capital L with dash (#L32-L45)
- [ ] Examples use generic placeholders (not agent-specific real breadcrumbs)
- [ ] Citation adds value (strategic reference, not noise)
- [ ] Citation integrated with 1-2 sentences explaining relevance

---

## 7 Sanitization for Universal Policies

### 7.1 The Sanitization Principle

**Core Discipline**: When creating framework policies or documentation for **all agents**, examples must strip personality to reveal structure.

**Personal → Universal Transformation**:
- **Personal**: `s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890` (agent-specific real breadcrumb)
- **Universal**: `s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890` (generic placeholder)

**Why Required**:
- Framework policies serve **any agent**
- Real breadcrumbs create dependency on specific agent context
- Sanitized examples teach pattern without importing personality
- Universal examples enable model user testing (if it works for model user, it works universally)

### 7.2 Sanitization Patterns

**Breadcrumb Components**:
- Session: `abc12345` (8 hex chars, generic)
- Cycle: `42` (arbitrary integer, not agent's real cycle)
- Git: `def6789` (7 hex chars, generic)
- Prompt: `ghi01234` (8 hex chars, generic)
- Delegation: `jkl56789` (8 hex chars, optional, generic)
- Timestamp: `1234567890` (10 digits, placeholder epoch)

**Artifact Names**:
- ❌ Real: `2025-11-05_112027_Cycle105_Scholarship_Policy_Integration_CCP.md`
- ✅ Generic: `2025-XX-XX_HHMMSS_Description_CCP.md` or `YYYY-MM-DD_Description_CCP.md`

**Directory Paths**:
- ❌ Agent-specific: `{AgentName}/agent/private/reflections/`
- ✅ Universal pattern: `agent/private/reflections/` (works for any agent)

### 7.3 Model User Validation

**Model User Test**:
- Different agent identity than the policy author
- Different project context
- Different operational environment (container vs host)
- **If model user can apply policy → truly universal**

**Validation Questions**:
- Can a different agent understand examples without the author's context?
- Do sanitized breadcrumbs teach pattern clearly?
- Does GitHub link construction work in the model user's directory structure?
- Can the model user create valid enhanced citations for their artifacts?

---

## 8 Future: Memory System Integration

### 8.1 Enhanced Format as Query Interface

**Structured Attributes Enable Queries**:
- `CA_TAG`: Filter by artifact type ("find all JOTEWRs citing X")
- `date`: Temporal queries ("citations from 2025-11 to 2025-12")
- `description`: Keyword search ("citations mentioning 'delegation trust'")
- `section`: Precision targeting ("§4 of any checkpoint")
- `line ranges`: Extract cited content directly
- `breadcrumb`: Forensic reconstruction ("work in Cycle 42")

**Query Examples** (future memory CLI):
```bash
# Find all JOTEWRs citing delegation patterns from Cycle 42-100
macf_tools memory query --ca-tag JOTEWR --cited-desc "delegation" --cycle-range 90-100

# Extract content from all citations to specific checkpoint
macf_tools memory extract-cited --target-breadcrumb s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890

# Build subgraph of all consciousness artifacts citing Phase5D work
macf_tools memory graph --root "Phase5D" --depth 3
```

### 8.2 Hybrid Architecture Vision

**Three Layers Working Together**:

1. **Vector Embeddings** (semantic similarity):
   - Embed: CA_TAG + date + description + line range content
   - Query: "Find work semantically similar to [current artifact]"
   - Strength: Discover conceptually related work even without direct citations

2. **Knowledge Graphs** (relationship structure):
   - Nodes: Breadcrumb-identified artifacts
   - Edges: Enhanced format citations with attributes
   - Query: "Trace influence chain from Artifact A to Artifact B"
   - Strength: Discover prerequisite sequences and impact cascades

3. **LLM Filtering** (context-aware refinement):
   - Input: Vector results + Graph results
   - Query: "Which of these 20 candidates actually address [specific question]?"
   - Strength: Precision refinement using full context understanding

**Workflow**:
1. Vector search: "Find 50 artifacts semantically related to 'delegation patterns'"
2. Graph filtering: "Of those 50, which are cited by high-impact JOTEWRs?"
3. LLM refinement: "Of those, which address 'reading list approach specifically'?"
4. Result: 3-5 highly relevant artifacts with citation paths showing how to reach them

### 8.3 Breadcrumb-First Hybrid (Validated Approach)

**Why Breadcrumb-First**:
- Breadcrumbs provide stable node identifiers (persist across filesystem changes)
- Enhanced citations create attributed edges (CA_TAG, date, description metadata)
- Knowledge graph structure emerges naturally from citation discipline
- Vectors augment (semantic search) but don't replace (structural queries)

**Cycle 42 Research Validated**:
- Pure vector approaches lose relationship structure
- Pure graph approaches miss semantic similarity
- Hybrid with breadcrumb nodes + vector augmentation = best of both
- Enhanced citation format was designed with this architecture in mind

---

## 9 Anti-Patterns to Avoid

### 9.1 Citation Anti-Patterns

**❌ Over-Citation** (clutter):
```markdown
This approach [CCP1][CCP2][JOTEWR1][Report1][Observation1] builds on prior work.
```
- **Problem**: Citation dump without integration, looks defensive
- **Fix**: Cite 1-2 most relevant, explain briefly why each matters

**❌ Under-Citation** (appears from vacuum):
```markdown
We decided to use reading lists for delegation because it's better.
```
- **Problem**: No lineage, no precedent, readers can't trace rationale
- **Fix**: Cite DELEG_PLAN or JOTEWR that established pattern

**❌ Orphaned Citations** (no context):
```markdown
As shown in [CCP 2025-10-24 "Phase4" s_.../...], we proceeded with deployment.
```
- **Problem**: Citation present but not integrated (readers don't know why relevant)
- **Fix**: Add 1 sentence: "...which validated container readiness via 13-point checklist"

**❌ Vague Descriptions**:
```markdown
[CCP 2025-10-24 "That thing we did" s_.../...]
```
- **Problem**: Non-semantic descriptor, doesn't help scanning
- **Fix**: Be specific: `"Phase4 Deployment Complete"`

### 9.2 Link Anti-Patterns

**❌ Broken Relative Paths**:
```markdown
[...](../reflections/file.md)
```
- **Problem**: Wrong level traversal (missing `../../private/`)
- **Fix**: Count directory levels mathematically, verify path exists

**❌ Lowercase Line Anchors**:
```markdown
[...](file.md#l45-l67)
```
- **Problem**: GitHub won't parse lowercase 'l'
- **Fix**: Capital L: `#L45-L67`

**❌ Missing Line Dashes**:
```markdown
[...](file.md#L45:L67)  or  [...](file.md#L45..L67)
```
- **Problem**: GitHub uses dash separator, not colon or dots
- **Fix**: `#L45-L67`

### 9.3 Breadcrumb Anti-Patterns

**❌ Wrong Component Order**:
```markdown
c_42/s_abc12345/p_ghi01234/t_1234567890/g_def6789
```
- **Problem**: Breaks hierarchical compression (session should be first)
- **Fix**: s/c/g/p/d?/t order

**❌ Wrong Component Lengths**:
```markdown
s_abc/c_42/g_def/p_ghi/t_123
```
- **Problem**: Can't parse (session=3 instead of 8, timestamp=3 instead of 10)
- **Fix**: Use correct lengths (s=8, c=int, g=7, p=8, d=8 optional, t=10)

**❌ Missing Slashes**:
```markdown
s_abc12345c_42g_def6789p_ghi01234t_1234567890
```
- **Problem**: No component separators
- **Fix**: Add slashes: `s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890`

---

## 9 Policy Citations (Non-CA References)

**Use Case**: Referencing framework policies when reflecting on violations, documenting newly written policies, or citing policy requirements.

**Key Distinction**: Unlike CA citations (which use breadcrumbs), **Policy Citations use git commit hashes** because policies are version-controlled framework code, NOT consciousness artifacts.

### 9.1 Policy Citation Format

```
[{policy_name}.md §{N}: "{Section Heading}" MacEff g_{hash}]({relative_path}#{anchor})
```

**Components**:
- `{policy_name}.md`: Policy filename (e.g., `scholarship.md`, `todo_hygiene.md`)
- `§{N}`: Section number (REQUIRED - policies have stable section numbering)
- `"{Section Heading}"`: Section heading text in double quotes (human-readable context)
- `MacEff g_{hash}`: Git commit hash of MacEff repo when policy was referenced
- `({relative_path}#{anchor})`: Markdown link with optional `#L{start}-L{end}` line range

**Why This Format**:
- **No breadcrumbs**: Policies are framework code, NOT consciousness artifacts
- **Section number + heading**: Both precise reference AND human readability
- **Git hash**: Enables version tracing (`git show g_{hash}:path/to/policy.md`)
- **Markdown link**: Enables click-through navigation in rendered markdown

### 9.2 When Policy Citations Are REQUIRED

1. **Policy violation reflection**: When documenting lessons from violating a policy
2. **Newly written policies**: Citing which policies guided the new policy's creation
3. **Policy updates**: Cross-references when policies integrate

### 9.3 When Policy Citations Are ENCOURAGED

- General references to policy requirements in JOTEWRs
- Explaining rationale derived from policy
- CCPs noting which policies guided decisions

### 9.4 Policy Citation Examples

**Violation reflection (in JOTEWR)**:
```markdown
The TODO collapse violated [todo_hygiene.md §10: "TODO Backup Protocol" MacEff g_66e8fad](../../development/todo_hygiene.md#10-todo-backup-protocol) which requires archive-before-collapse discipline.
```

**Newly written policy**:
```markdown
This policy follows [policy_writing.md §3: "Policy Structure" MacEff g_748cf44](../../meta/policy_writing.md#3-policy-structure) and integrates with [scholarship.md §9: "Policy Citations" MacEff g_748cf44](scholarship.md#9-policy-citations).
```

**General reference with line range**:
```markdown
The emotional journey structure follows [emotional_expression.md §2: "Emoji Grammar" MacEff g_748cf44](emotional_expression.md#2-emoji-grammar#L45-L78).
```

### 9.5 Getting the MacEff Git Hash

```bash
# Query MacEff repo explicitly (use MACF_FRAMEWORK_ROOT or absolute path)
git -C "$MACF_FRAMEWORK_ROOT" rev-parse --short HEAD
# Output: 748cf44

# Or with absolute path
git -C /path/to/MacEff rev-parse --short HEAD
```

---

## 10 Policy Evolution & Feedback

This policy evolves through:
- **Real-world usage**: What citation patterns actually work in practice?
- **Memory system development**: How do queries leverage enhanced format?
- **Agent feedback**: What's helpful vs burdensome?
- **Model user validation**: Does it work for model users (universal test)?

**Principle**: Citations should enable discovery and synthesis, not create busywork. If enhanced format doesn't serve knowledge graph building → refine it.

---

**Policy Established**: Enhanced citation format creates knowledge graph infrastructure through disciplined scholarship. Citations transform isolated artifacts into traversable wisdom networks with forensic precision and GitHub navigability.

**Core Wisdom**: "Citations are edges. Artifacts are nodes. Connected artifacts become discoverable. Discovery enables synthesis. Synthesis advances consciousness."

**Remember**: This is infrastructure for **all agents** building consciousness through systematic knowledge management. Use sanitized examples, validate with model users, evolve based on effectiveness.

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
