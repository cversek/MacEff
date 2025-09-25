# Base Policy Refactor Roadmap (MacEff)

## Goals
- **AI-as-colleague** interaction model (persistent identity, roles).
- **Modular “superpowers”**: time awareness, token/context awareness, continuity across compaction, introspection, delegation.
- **Language-agnostic** policy text (only the *implementation* hooks live in `macf_tools`).
- **Minimal, configurable** defaults; designed for open-source collaborators.

## Design Principles (distilled)
- **Continuity across resets**: detect context loss; checkpoint critical state; restore gracefully.
- **Time & token awareness**: track wall clock + token headroom; warn and adapt.
- **Delegation & authority**: primary delegates thoughtfully; specialists may hold blocking authority in their domain.
- **Introspection & improvement**: brief reflections after tasks; lightweight accountability log for significant errors.
- **Team structure**: stable agent IDs/roles; soft caps on active agents; archive rather than delete history.
- **Transparency**: short docs, clear rationale, public readability.

## Migration Plan (what to keep / sanitize)
- **CLAUDE.md** → keep cognitive layering & compaction-recovery *concepts*; drop Anthropic-specific language, env paths, and dramatized phrasing.
- **COMPACTION_PREPARATION.md** → keep phased prep, checkpoints, post-reset verification; generalize thresholds & commands.
- **DELEGATION_AUTHORITY.md** → keep decision criteria, authority levels, packaging results, reflection; remove trigger keyword lists & tool-specific mechanics.
- **TEAM_MANAGEMENT.md** → keep stable IDs, roles, lifecycle; make team-size a guideline; remove gamified extras and fixed paths.
- **REPRIMAND_PROTOCOL.md** → keep learning-focused accountability (log significant deviations); drop detailed violation taxonomies and git-hook machinery.

## Proposed Base Layout (markdown)
```bash
policies/base/
README.md # overview & how to use
core_principles.md # mindset + cognitive architecture
context_management.md # token/time awareness, compaction continuity, checkpoints
delegation_guidelines.md # when/how to delegate, authority, reintegration, reflection
team_structure.md # roles, IDs, lifecycle, roster
accountability.md # logging deviations, improvement loop
```

## Authoring & Validation (assistant-led)
1. **Outline & scope** (agree on file list + boundaries).
2. **Extract bullets** from the old docs into a scratch pad per file.
3. **Draft modules** (assistant writes; human trims for brevity).
4. **Neutrality pass** (purge tech-specific bits; add placeholders for `macf_tools` hooks).
5. **Clarity pass** (shorten, add 1–2 examples where needed).
6. **Scenario tests**:
   - Near-compaction dry run (warn → checkpoint → reset → restore).
   - Delegation dry run (decide → brief → integrate → reflect).
   - Accountability dry run (record a significant deviation).
7. **Iterate** (fix gaps surfaced by tests).
8. **Finalize base** + note how to build specialized packs (e.g., Python assistant policy).

## Implementation Hooks (for `macf_tools`)
- `time_now()` / `duration_since(t)`.
- `tokens_left()`, `near_limit(thresholds)`.
- `checkpoint_write(data)` / `checkpoint_read()`.
- `policy_entrypoint()` → resolves `/opt/maceff/policies/current/CLAUDE.md` (or configured path).
- `delegate(task_spec, role)` (abstract; backend decides how to run).
- `account_log(entry)` minimal structured log.

> The base policy **describes behavior**; `macf_tools` **provides adapters**. All thresholds/paths are project-configurable.