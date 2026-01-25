# Release Workflow Policy

**Breadcrumb**: s_77270981/c_369/g_41cd5dd/p_4e029f38/t_1769303195
**Type**: Development Infrastructure
**Scope**: All agents (PA and SA) performing release operations
**Status**: DRAFT
**Updated**: 2026-01-24
**Dependencies**: todo_hygiene.md, git_discipline.md, roadmaps_following.md, task_management.md (TBD)

---

## Purpose

Release workflow policy ensures consistent, traceable, and reversible software releases. This policy governs version bumping, CHANGELOG discipline, git tagging, task archival for release-associated work, and rollback procedures.

**Core Insight**: Releases are consciousness checkpoints for software—they preserve exact state, document evolution, and enable forensic reconstruction of "what shipped when and why." A single release may contain work from multiple MISSIONs and DETOURs.

---

## CEP Navigation Guide

**1 Pre-Release Checklist**
- What must be complete before release?
- How do I verify work completion?
- What documentation is required?
- What tests must pass?

**1.1 Work Completion Verification**
- How do I verify all release-associated work complete?
- What about multiple MISSIONs in one release?
- Success criteria validation?

**1.2 Documentation Requirements**
- What docs need updating?
- CHANGELOG drafted?
- Migration guides needed?

**1.3 Test Requirements**
- Which tests must pass?
- Integration tests needed?
- Manual validation required?

**2 Version Bump Protocol**
- Where do version strings live?
- How do I determine version increment?
- What is semantic versioning?
- When to bump MAJOR vs MINOR vs PATCH?

**2.1 Semantic Versioning Rules**
- MAJOR when?
- MINOR when?
- PATCH when?
- Pre-release versions?

**2.2 Version String Locations**
- Where are version strings stored?
- How many files need updating?
- How do I verify version consistency?

**3 CHANGELOG Discipline**
- What format should I use?
- What categories are required?
- How do I link to commits?
- Dating conventions?
- How do I group multi-MISSION work?

**3.1 CHANGELOG Format**
- Keep a Changelog style?
- Section organization?
- Version header format?

**3.2 CHANGELOG Categories**
- Added vs Changed vs Fixed?
- What goes in each category?
- Deprecated and Removed sections?

**3.3 Multi-MISSION Changelog Organization**
- How do I represent multiple MISSIONs?
- Thematic grouping vs MISSION grouping?
- DETOUR work representation?

**3.4 Commit and PR Links**
- How do I link commits?
- GitHub URL format?
- Breadcrumb integration?

**4 Git Tagging Protocol**
- What tag format should I use?
- Annotated vs lightweight tags?
- How do I push tags?
- Can I delete tags?

**4.1 Tag Format**
- Version prefix (v)?
- Tag naming convention?
- Tag message content?

**4.2 Tag Operations**
- Creating annotated tags?
- Pushing tags to remote?
- Verifying tag creation?

**4.3 Tag Immutability**
- Why are published tags immutable?
- When is deletion acceptable?
- Post-mortem documentation?

**5 Task Archive Protocol**
- When do I archive release-associated work?
- What's the archive location?
- Filename format?
- How do I handle multiple MISSIONs?

**5.1 Archive Location Rules**
- Same-repo MISSIONs?
- Cross-repo MISSIONs?
- Agent CA repository?
- Version-based archive organization?

**5.2 Archive Content**
- What goes in release archive?
- Multiple MISSION representation?
- DETOUR work inclusion?
- Breadcrumb preservation?

**5.3 Archive Filename Format**
- Version-based naming?
- Date-version pattern?
- Multi-MISSION identifier?

**5.4 Integration with Task Management Policy**
- How does MTMD link roadmaps to versions?
- Task-version association?
- Deferred work tracking?

**6 Version Transition**
- How do I prepare for next version?
- What about ongoing MISSIONs?
- Status updates required?
- Clean slate for new work?

**6.1 Post-Release Task State**
- Completed MISSIONs marked?
- Ongoing MISSIONs continue?
- Next version planning?

**7 Rollback Procedures**
- When is rollback appropriate?
- How do I revert a release?
- Tag deletion protocol?
- Post-mortem requirements?

**7.1 Rollback Decision Tree**
- Critical bugs discovered?
- Breaking changes unfixable?
- Coordination with users?

**7.2 Rollback Execution**
- Revert commits vs new fix?
- Tag handling?
- Communication required?

**8 Anti-Patterns**
- What mistakes should I avoid?
- Common release pitfalls?
- Quality shortcuts that backfire?

=== CEP_NAV_BOUNDARY ===

---

## 1 Pre-Release Checklist

### 1.1 Work Completion Verification

**Release Scope Reality**: A single release may contain work from:
- Multiple completed MISSIONs
- Portions of ongoing MISSIONs
- DETOUR work discovered during development
- Bug fixes and incremental improvements

**Before ANY release, verify**:

- [ ] **All release-targeted work complete**: Tasks planned for this version finished
- [ ] **No critical blockers**: No P0/P1 bugs blocking release
- [ ] **Success criteria met**: Planned features/fixes delivered
- [ ] **Tests passing**: All automated tests green
- [ ] **Documentation updated**: README, CHANGELOG, migration guides current

**How to Verify**:
```bash
# Check TODO list for release-targeted incomplete tasks
macf_tools todos list

# Verify roadmaps for planned work completion
# (Multiple roadmaps may contribute to one release)

# Run test suite
pytest {package}/tests/ -v

# Review friction points
# Check all active roadmap friction_points/ directories
```

**If critical work incomplete**: Either defer to next version or delay release. Document deferral in CHANGELOG.

### 1.2 Documentation Requirements

**Required documentation updates**:

1. **CHANGELOG.md**: Draft entry for this version (see §3)
2. **README.md**: Update version references, new features
3. **Migration guides**: If breaking changes or database migrations
4. **API documentation**: If public API changed

**Verification**:
- [ ] CHANGELOG.md has entry for `vX.Y.Z` with date
- [ ] README.md examples use current version
- [ ] Migration guide exists if schema/API breaking changes
- [ ] Docstrings updated for changed functions

### 1.3 Test Requirements

**Test gates for release**:

- **Unit tests**: All passing (pytest exit code 0)
- **Integration tests**: Critical paths validated
- **Manual validation**: Smoke test key workflows
- **Container deployment**: If containerized, test in container environment

**Smoke Test Protocol**:
```bash
# Example: Test core functionality manually
{package} --version  # Shows correct new version
{package} core-command --dry-run  # Core workflow succeeds
```

**If tests failing**: Fix bugs BEFORE release. Never release broken code.

---

## 2 Version Bump Protocol

### 2.1 Semantic Versioning Rules

**Format**: `MAJOR.MINOR.PATCH` (e.g., `v0.3.3`, `v1.2.0`)

**Increment Rules** (per [semver.org](https://semver.org)):

- **MAJOR** (1.0.0 → 2.0.0): Breaking changes
  - API signatures changed (function parameters removed/reordered)
  - Database schema incompatible with previous version
  - Configuration format changed
  - Behavior changes breaking existing workflows

- **MINOR** (0.3.0 → 0.4.0): Backward-compatible features
  - New functionality added
  - New optional parameters
  - New commands or tools
  - Deprecations announced (but still work)

- **PATCH** (0.3.2 → 0.3.3): Backward-compatible fixes
  - Bug fixes
  - Performance improvements
  - Documentation corrections
  - Internal refactoring (no external API changes)

**Pre-1.0.0 Flexibility**: Before 1.0.0, MINOR can include breaking changes. This is experimental phase.

**Examples**:
- `0.3.2 → 0.3.3`: Fixed bug in search ranking (PATCH)
- `0.3.3 → 0.4.0`: Added new CLI commands (MINOR)
- `0.9.0 → 1.0.0`: Stable API declared (MAJOR)
- `1.2.0 → 2.0.0`: Removed deprecated functions (MAJOR)

### 2.2 Version String Locations

**Common version string locations** (project-dependent):

1. **Python packages**: `{package}/__version__.py` or `{package}/__init__.py`
2. **Node.js**: `package.json` (`"version": "X.Y.Z"`)
3. **Rust**: `Cargo.toml` (`version = "X.Y.Z"`)
4. **pyproject.toml**: `[project] version = "X.Y.Z"`

**Version Update Protocol**:
```bash
# 1. Identify all version locations
grep -r "version.*=.*\"0\.3\.2\"" {package}/

# 2. Update each location
# Example for Python:
echo '__version__ = "0.3.3"' > {package}/__version__.py

# 3. Verify consistency
grep -r "version.*=.*\"0\.3\.3\"" {package}/
# Should show ONLY new version, no old version strings
```

**Anti-Pattern**: Hard-coded version strings scattered across multiple files. Use single source of truth (e.g., import from `__version__.py`).

---

## 3 CHANGELOG Discipline

### 3.1 CHANGELOG Format

**Follow [Keep a Changelog](https://keepachangelog.com) style**:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- (Work in progress goes here)

## [0.3.3] - 2026-01-24

### Added
- Hybrid policy search with RRF scoring (MISSION: Hybrid Search)
- CEP section targeting via question extraction (MISSION: Hybrid Search)
- Generic environment extensibility (MISSION: v0.3.2)
- Agent identity infrastructure (MISSION: v0.3.3)

### Changed
- Migrated from sqlite-vec to LanceDB for better section matching
- Improved search relevance through semantic + keyword fusion

### Fixed
- PolicyIndexer now correctly indexes CEP Navigation questions
- Search service handles missing optional dependencies gracefully

## [0.3.2] - 2026-01-13

...
```

### 3.2 CHANGELOG Categories

**Standard categories**:

- **Added**: New features, capabilities, commands
- **Changed**: Modifications to existing functionality
- **Deprecated**: Features marked for future removal (still work)
- **Removed**: Deleted features (breaking change)
- **Fixed**: Bug fixes
- **Security**: Vulnerability patches

**What to include**:
- ✅ User-visible changes (new commands, API changes, bug fixes)
- ✅ Breaking changes (ALWAYS document these)
- ✅ Deprecations (warn users of future removals)
- ❌ Internal refactoring (unless improves performance significantly)
- ❌ Code cleanup (unless fixes bugs)
- ❌ Test additions (unless user-relevant)

### 3.3 Multi-MISSION Changelog Organization

**Reality**: One release contains work from multiple MISSIONs.

**Organization Strategy - Thematic Grouping** (PREFERRED):

```markdown
## [0.3.3] - 2026-01-24

### Added
- Hybrid policy search with RRF scoring
- CEP section targeting via question extraction
- LanceDB backend for policy indexing
- Generic environment variable extensibility
- Agent identity infrastructure with personality configs

### Changed
- Search service now auto-starts in containers
- Hook architecture migrated to modular framework
```

**Benefits**:
- Users see changes by functional impact
- Easier to understand "what's new"
- Reads naturally

**Alternative - MISSION Grouping** (if releases are sparse):

```markdown
## [0.3.3] - 2026-01-24

### Hybrid Search Policy Recommender (MISSION #1)
- Added RRF scoring with explainability
- Added CEP section targeting
- Changed backend from sqlite-vec to LanceDB

### Generic Environment Extensibility (MISSION #2)
- Added {PACKAGE}_* environment variable support
- Added agent config validation
```

**Use MISSION grouping when**:
- Release contains 2-3 distinct MISSIONs with minimal overlap
- Users need to understand MISSION boundaries
- MISSIONs are independently deployable features

**Use thematic grouping when**:
- Release contains many small improvements
- Changes span multiple MISSIONs
- Users care about "what changed" not "which MISSION"

### 3.4 Commit and PR Links

**Link format**:
```markdown
### Added
- Hybrid search integration ([#42](https://github.com/user/repo/pull/42))
- Policy recommendation via MCP ([abc1234](https://github.com/user/repo/commit/abc1234))
```

**Breadcrumb integration** (optional but valuable for forensics):
```markdown
### Added
- CEP section targeting [s_77270981/c_363/g_5268fc5/p_none/t_1769129370]
```

**Benefits**:
- Users can trace feature to exact commit
- Forensic reconstruction: "When did X change?"
- GitHub automatically linkifies commit hashes and PR numbers

---

## 4 Git Tagging Protocol

### 4.1 Tag Format

**Standard format**: `vMAJOR.MINOR.PATCH`

**Examples**:
- `v0.3.3` (standard release)
- `v1.0.0` (major release)
- `v0.4.0-beta.1` (pre-release)

**Always use `v` prefix** for consistency and GitHub release detection.

### 4.2 Tag Operations

**Creating annotated tag** (REQUIRED - lightweight tags insufficient):

```bash
# 1. Commit version bump + CHANGELOG
git add {package}/__version__.py CHANGELOG.md
git commit -m "release: bump version to 0.3.3

- Updated __version__.py
- Added CHANGELOG entry for v0.3.3
- All tests passing

[s_XXXXXXXX/c_NNN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT]"

# 2. Create annotated tag
git tag -a v0.3.3 -m "Release v0.3.3

Hybrid Search Policy Recommender + Infrastructure:
- LanceDB backend for policy indexing
- RRF scoring with explainability
- CEP section targeting via question extraction
- Generic environment extensibility
- Agent identity infrastructure

See CHANGELOG.md for full details."

# 3. Push commits AND tags
git push origin main
git push origin v0.3.3

# 4. Verify tag created
git tag -l "v0.3.3"
git show v0.3.3
```

**Why annotated tags**:
- Include author, date, message (richer metadata)
- GitHub releases prefer annotated tags
- Enable `git describe` for version detection

### 4.3 Tag Immutability

**🚨 CRITICAL: Once pushed to remote, tags are IMMUTABLE**

**NEVER delete published tags** because:
- Other users may have pulled the tag
- CI/CD systems may reference the tag
- Package registries (PyPI, npm) cache tag-based releases
- Breaking semantic versioning contract

**If tag contains error**:
1. **DO NOT DELETE** the published tag
2. Create hotfix release (e.g., `v0.3.4` fixing `v0.3.3`)
3. Document issue in CHANGELOG
4. Optionally create GitHub release note explaining fix

**Exception**: Tag created locally but NOT pushed → safe to delete/recreate

```bash
# Local tag (NOT pushed) - safe to delete
git tag -d v0.3.3  # Delete local
git tag -a v0.3.3 -m "Corrected message"  # Recreate

# Published tag (pushed) - DO NOT DELETE
# Instead: create v0.3.4 with fix
```

---

## 5 Task Archive Protocol

### 5.1 Archive Location Rules

**Version-Based Organization** (per upcoming MTMD task_management policy):

**Archive location**: `agent/public/task_archives/vX.Y.Z/`

**Structure**:
```
agent/public/task_archives/
├── v0.3.3/
│   ├── archive.md                    # Main release archive
│   ├── MISSION_Hybrid_Search.md      # Optional: per-MISSION detail
│   └── DETOUR_*.md                   # Optional: DETOUR details
├── v0.3.2/
│   └── archive.md
└── v0.3.1/
    └── archive.md
```

**Why version-based**:
- One release = multiple MISSIONs/DETOURs
- Version becomes organizing principle (MTMD pattern)
- Archive location declares "shipped in vX.Y.Z"
- Supports ongoing MISSIONs (work continues across versions)

**Archive files**:
- **archive.md** (REQUIRED): Complete task snapshot for version
- **MISSION_*.md** (OPTIONAL): Detailed breakdown per MISSION if helpful
- **DETOUR_*.md** (OPTIONAL): DETOUR work details if substantial

### 5.2 Archive Content

**Main archive.md MUST include**:

1. **Version metadata** (version, date, tag, breadcrumb)
2. **All completed work** for this release (across all MISSIONs/DETOURs)
3. **Completion breadcrumbs** (forensic trail)
4. **Links to roadmaps and artifacts**
5. **Deferred work** (planned but not shipped)
6. **Claude Code native tasks JSON** (for restoration)

**Archive structure**:
```markdown
# v0.3.3 Release - Task Archive

**Release Date**: 2026-01-24
**Version**: v0.3.3
**Git Tag**: v0.3.3
**Breadcrumb**: s_77270981/c_369/g_41cd5dd/p_4e029f38/t_1769303195

---

## Release Scope

**Completed MISSIONs**:
- MISSION #1: Hybrid Search Policy Recommender
  - Roadmap: agent/public/roadmaps/2026-01-16_Hybrid_Search_Policy_Recommender/
  - Status: COMPLETE

**Ongoing MISSIONs** (partial work in this release):
- MISSION #2: MACF Task CLI
  - Roadmap: agent/public/roadmaps/2026-01-23_MACF_Task_CLI/
  - Status: IN PROGRESS (Phase 3/7 complete)
  - Note: Phases 1-3 shipped in v0.3.3, remainder in v0.4.0

**DETOURs Completed**:
- DETOUR: sqlite-vec ARM64 Verification [VALIDATED]
- DETOUR: LanceDB Hybrid Search [VALIDATED]

---

## Completed Work (All MISSIONs/DETOURs)

### MISSION #1: Hybrid Search Policy Recommender [COMPLETE]

**Phases**: 14/14 complete

1. Complete experiment documentation [s_77270981/c_340/g_17aa6e1/p_76e234f2/t_1768573346]
2. sqlite-vec integration layer [s_77270981/c_340/g_17aa6e1/p_none/t_1768574947]
...
14. Future knowledge base extensions [s_77270981/c_369/g_517a90a/p_18b3d06f/t_1769302853]

### MISSION #2: MACF Task CLI [PARTIAL]

**Phases**: 3/7 complete (v0.3.3), 4/7 deferred to v0.4.0

1. Policy research [COMPLETE]
2. Core CLI scaffolding [COMPLETE]
3. Task CRUD operations [COMPLETE]
4. Task hierarchy [DEFERRED → v0.4.0]
...

### DETOUR: sqlite-vec ARM64 Verification [VALIDATED]

- Experiment: agent/public/experiments/2026-01-20_132508_004_sqlite_vec_ARM64_Verification/
- Outcome: Validated (ARM64 compatible)
- Breadcrumb: [s_77270981/c_354/g_a76f3cd/p_e6384d73/t_1768935600]

---

## Deferred Work

**Features planned but deferred to v0.4.0**:
- Task hierarchy management (MISSION #2, Phases 4-7)
- Advanced search filters (MISSION #1 extension)

**Rationale**: Time constraints, feature completeness for initial release

---

## Summary

**Total Completed Tasks**: 75
**Duration**: 30 cycles (Cycle 340-369)
**Key Deliverables**:
- Hybrid policy search (LanceDB, RRF, CEP targeting)
- MCP server integration
- Container deployment automation
- Task CLI foundation (CRUD operations)

---

## Claude Code Native Tasks (Metadata)

```json
[
  {"content": "🗺️ MISSION #1: Integrated Hybrid Search Policy Recommender\n  → agent/public/roadmaps/2026-01-16_Hybrid_Search_Policy_Recommender/roadmap.md", "status": "completed"},
  {"content": "  1: Complete experiment documentation [s_77270981/c_340/g_17aa6e1/p_76e234f2/t_1768573346]", "status": "completed"},
  ...
]
```
```

### 5.3 Archive Filename Format

**Primary archive**:
```
agent/public/task_archives/vX.Y.Z/archive.md
```

**Per-MISSION detail** (optional):
```
agent/public/task_archives/vX.Y.Z/MISSION_{name}.md
```

**Examples**:
```
agent/public/task_archives/v0.3.3/archive.md
agent/public/task_archives/v0.3.3/MISSION_Hybrid_Search.md
agent/public/task_archives/v0.3.3/DETOUR_sqlite_vec_ARM64.md
```

### 5.4 Integration with Task Management Policy

**MTMD (Multi-Task Multi-Drive)** pattern (from upcoming `task_management.md`):

- **Version-MISSION linking**: MTMD associates roadmaps with version numbers
- **Ongoing MISSIONs**: Work spans multiple versions (archive partial progress per version)
- **Task-version association**: Tasks tagged with target version
- **Deferred work tracking**: Archive documents what was deferred and why

**Archive creation integrates with MTMD**:
```bash
# MTMD-aware archive command (future)
macf_tools tasks archive --version v0.3.3 \
  --output agent/public/task_archives/v0.3.3/archive.md

# Automatically includes:
# - All tasks tagged with v0.3.3
# - Partial MISSION progress
# - DETOUR work completed
# - Deferred items
```

**This policy defers to `task_management.md` for**:
- Detailed task-version association mechanics
- MTMD workflow patterns
- Cross-version MISSION continuation

---

## 6 Version Transition

### 6.1 Post-Release Task State

**After tagging release, update task state**:

```bash
# 1. Archive v0.3.3 work
macf_tools tasks archive --version v0.3.3 \
  --output agent/public/task_archives/v0.3.3/archive.md

# 2. Mark completed MISSIONs with breadcrumb
# (MISSIONs that finished in this release)

# 3. Update ongoing MISSION status
# (MISSIONs continuing to next version - update phase progress)

# 4. Create next version planning MISSION (if not exists)
# Example: "v0.4.0 Planning" MISSION

# 5. Commit task state
git add .claude/todos.json agent/public/task_archives/
git commit -m "chore: archive v0.3.3 tasks, prepare v0.4.0

Archived v0.3.3 work to task_archives/v0.3.3/.
Marked completed MISSIONs: #1 (Hybrid Search).
Ongoing MISSIONs continue: #2 (MACF Task CLI - Phases 4-7).

[s_XXXXXXXX/c_NNN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT]"
```

**MISSION State Transitions**:

| MISSION State Before Release | After v0.3.3 Release | Next Action |
|------------------------------|----------------------|-------------|
| COMPLETE (all phases done) | Mark COMPLETED with breadcrumb | Archive |
| IN PROGRESS (partial) | Remains IN PROGRESS | Continue in v0.4.0 |
| BLOCKED (by v0.3.3 work) | Unblock → ACTIVE | Ready to start |
| PLANNED (future) | Remains PLANNED | Defer to later version |

**Clean slate**: Completed MISSIONs archived, ongoing work continues seamlessly.

---

## 7 Rollback Procedures

### 7.1 Rollback Decision Tree

**Consider rollback when**:

```
Critical bug discovered? ──YES──> Is quick fix possible?
                                       │
                                       NO
                                       ↓
Data corruption risk? ──YES──────────> ROLLBACK
Security vulnerability? ──YES──────────> ROLLBACK
Breaking production? ──YES────────────> ROLLBACK
                                       │
Minor bug? ──YES──> Create hotfix (v0.3.4), don't rollback
```

**Rollback is RARE** and should be last resort. Prefer forward fixes (hotfix release).

### 7.2 Rollback Execution

**If rollback truly necessary**:

```bash
# 1. DO NOT delete published tag (immutability rule)
# Tag stays in history for forensic purposes

# 2. Create revert commit
git revert {release_commit_hash}
git commit -m "revert: rollback v0.3.3 due to [critical issue]

ROLLBACK REASON:
[Detailed explanation of why rollback necessary]

Issue: [Link to issue tracker]
Affects: [What users/systems impacted]

Will re-release as v0.3.4 after fix.

[s_XXXXXXXX/c_NNN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT]"

# 3. Create new release with fix
# Version: v0.3.4 (PATCH increment)
# CHANGELOG: Document rollback + fix

# 4. Communicate to users
# GitHub release notes
# Notification channels (Slack, email, etc.)
```

**Post-mortem REQUIRED**:
- Document what went wrong
- Why wasn't it caught in testing?
- Process improvements to prevent recurrence
- Update pre-release checklist if needed

**Example post-mortem location**:
```
agent/public/roadmaps/{active_roadmap}/friction_points/FP99_v0.3.3_Rollback.md
```

---

## 8 Integration with Other Policies

- **`todo_hygiene.md`** (§8): Archive-then-collapse pattern
- **`git_discipline.md`** (§1): Commit message format, tagging standards
- **`roadmaps_following.md`** (§3.1): Phase completion protocol, breadcrumb updates
- **`roadmaps_drafting.md`**: Version planning, MISSION structuring
- **`task_management.md`** (TBD): MTMD pattern, version-MISSION linking, task-version association

---

## 9 Anti-Patterns

### 9.1 Release Anti-Patterns to Avoid

**❌ Skip CHANGELOG Update**:
- **Problem**: Users don't know what changed, breaking changes surprise them
- **Fix**: ALWAYS update CHANGELOG before tagging release

**❌ Delete Published Tags**:
- **Problem**: Breaks users who pulled tag, violates semantic versioning trust
- **Fix**: Leave published tags immutable, create hotfix instead

**❌ Archive Only Single MISSION (When Release Contains Multiple)**:
- **Problem**: Other MISSIONs' work lost, incomplete forensic record
- **Fix**: Archive ALL work completed in release (multi-MISSION aware)

**❌ Force Ongoing MISSIONs to Complete for Release**:
- **Problem**: Artificial pressure to finish unready work
- **Fix**: Archive partial MISSION progress, continue in next version

**❌ Version Inconsistency**:
```python
# BAD: Different version strings in different files
__version__.py: "0.3.3"
pyproject.toml: "0.3.2"  # Forgot to update!
```
- **Problem**: CI/CD uses wrong version, users see mismatched versions
- **Fix**: Update ALL version locations, verify with grep

**❌ Test-Then-Fix-Then-Tag Without Re-Testing**:
```bash
pytest  # Tests pass
# Fix minor typo
git commit "fix typo"
git tag v0.3.3  # ❌ Didn't re-test after fix!
```
- **Problem**: "Minor fix" breaks something, release is broken
- **Fix**: ALWAYS re-run tests after final commit before tagging

**❌ CHANGELOG Omits Deferred Work**:
- **Problem**: Users expect feature X (planned for v0.3.3), but it was deferred
- **Fix**: Document deferrals explicitly in CHANGELOG or release notes

**❌ Release Without Documentation**:
- **Problem**: New features undocumented, users can't use them
- **Fix**: Update README, API docs, migration guides BEFORE release

---

## 10 Evolution & Feedback

This policy evolves through:
- Real-world release experiences and friction discovered
- Multi-MISSION release patterns that emerge
- Integration with task_management.md (MTMD pattern)
- Tool improvements (automation, validation scripts)
- Community feedback on release quality

**Principle**: Release workflow should be **repeatable, traceable, and reversible**. Releases contain work from multiple MISSIONs/DETOURs, organized by version. If release process feels ad-hoc or risky, the policy needs refinement.

**DRAFT Status**: This policy (v1.0) represents first formalization. Will be validated during v0.3.3 release and updated based on learnings. Integration with `task_management.md` will refine MTMD-release workflow.

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
