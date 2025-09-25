# File: CLAUDE.md
# MacEff Builder Preamble — “Pass the Torch” Edition (for vanilla Claude Code)

> Purpose: This document equips a vanilla Claude Code session (no MacEff adapters) to **build and maintain the MacEff framework** from the ground up, following the minimal, configurable, transparent philosophy we established. It contains the mindset, reading loops, migration rules for legacy policies, a curated repo map, cleanup plan, container↔package mapping, and permission model. You are an **AI colleague** working with OSS humans. Keep it terse, technical, and auditable.

---

## CEP-0: Link Discovery Loop (for *this* repo)
Reading order for project understanding:
1. `docs/policy/BASE_POLICY_ROADMAP.md` → project goals/scope
2. `policies/base/*` → minimal policy kit (core_principles → context_management → delegation_guidelines → team_structure → accountability)
3. `README.md` (Philosophy section) → dev-facing narrative
4. This `CLAUDE.md` → build & governance playbook

**Loop**: Skim in order → extract a 3–5 bullet operational plan → proceed. Re-run after major changes.

---

## Operating Stance (AI-as-colleague)
- **Clarity & brevity first**; technical structure beats prose.
- **Continuity**: carry objective/next steps; emit checkpoints when risk rises.
- **Time & tokens**: assume local user TZ if provided; otherwise UTC. Alert at ~85% context; checkpoint before ~95%.
- **Solo by default**; delegate only when parallelism/specialism/safety wins.
- **Auditable moves**: every non-trivial change leaves a diff, a short rationale, and a test/smoke step.

**Ready block template** (return this when asked to proceed):

$```
Ready:
objective: <one line>
next_steps: [a, b, c]
awareness:
  time: <TZ and source>
  budget: <concise/default|warned>
  continuity: <checkpoint plan or none>
$```

---

## Project Map (curated)
**High-value directories to keep and evolve**
- `policies/base/` → language-agnostic base policy kit (minimal CEPs & modules).
- `docs/policy/` → human-facing roadmaps and migration notes.
- `tools/` → host-side dev tools; includes `bin/`, `src/` (Python-only for `maceff_tools`), `policyctl`, `policy-sync`.
- `docker/` → container bootstrap (`Dockerfile`, `start.sh`, `sa-exec`) with idempotent setup.
- `docker-compose.yml` → volumes/env mapping; ensure `MACEFF_TZ` propagation.
- `agent_defs/` → PA/SA seeds to scaffold per-user trees in container.
- `Makefile` → typed entrypoints (`build`, `up`, `down`, `ssh-*`, `policy-sync`, etc.).
- `.maceff/` → **local** customization (env, plugins, policy sets mirror). Treat as a *customization surface*, not the canonical policy source.

**Local-only or to sanitize**
- `.venv/` → local virtualenv; **must be ignored** in VCS.
- `.claude/` → local agent environment; keep but do not require in CI.
- `.maceff/policies` → separate git repo used inside container; main repo **must ignore** this path.
- `sandbox-*` → host mirrors/snapshots; keep out of VCS.

---

## Cleanup & Convergence Plan
**Goal**: holistically integrated package↔container mapping with minimal ambiguity.

1) **Git hygiene**
- Ensure `.gitignore` includes:
  - `.venv/`
  - `sandbox-home/`, `sandbox-shared_workspace/`
  - `.maceff/policies/`
  - `LEGACY_POLICIES_NO_VCS/`
  - `**/*.bak.*`
- Remove committed detritus (if any): historical `.venv`, `*.bak.*`, stray mirrors. Document purges in commit messages.

2) **Policy sources**
- Canonical human-editable policies live in `policies/`.
- Container’s `/opt/maceff/policies` mirrors curated sets and symlinks `current` → chosen set.
- Keep `policy-sync` as the single command to push curated sets to container; no ad-hoc copies.

3) **Container idempotence**
- All “one-off” setup must be embodied in `docker/start.sh` and `Dockerfile`:
  - groups (`agents_all`, `sa_all`, `policyeditors`)
  - ACLs for PA/SA trees
  - `/shared_workspace` sticky + SGID + group
  - `maceff_tools` installation in shared venv
  - export `MACEFF_TZ` to `/etc/environment` and `/etc/profile.d/99-maceff-env.sh`

4) **Permissions model (authoritative)**
- Groups:
  - `agents_all` for shared workspace collaboration
  - `sa_all` for SA peer read on public/assigned only
  - `policyeditors` for `/opt/maceff/policies` (mode **2770**, SGID)
- PA/SA tree:
  - `.../agent/` non-writable by default (0555 root:pa)
  - `public/`, `private/` (0750 owned by PA/SA respectively)
  - `assigned/` RWX to PA, RX to SA; SA `private/` **no** group access
- `/shared_workspace`:
  - `chgrp agents_all`, recursive `g+ws`, root dir SGID + sticky.

5) **Remove ambiguity in policy locations**
- Treat `.maceff/policies/sets/base` as the **deployed copy**, not the source of truth.
- The source of truth for **content** is `policies/`; `policy-sync` materializes it.

---

## Container ↔ Package Mapping (desired)
- Host `tools/` ↔ Container `/opt/tools` (bind mount in dev)
- Host `policies/` ↔ Sync into `/opt/maceff/policies/sets/<name>` via `policy-sync`; `current` → that set
- Host `agent_defs/` ↔ Container `/opt/agent_defs` (RO)
- Named volumes:
  - `home_all` ↔ `/home` (persist)
  - `shared_workspace` ↔ `/shared_workspace` (persist)
  - `maceff_venv` ↔ `/opt/maceff-venv`
  - `sshd_keys` ↔ `/etc/ssh`
- Env plumbing:
  - `MACEFF_TZ` propagated by compose, surfaced to `/etc/environment` and login shells
  - `DEFAULT_PA`, `UV_LINK_MODE`, optional `POLICY_EDITORS` group membership

**Smoke checks** (run after `make up`):

$```
make ssh-pa <<'SH'
set -e
echo "MACEFF_TZ=$MACEFF_TZ"
bash -lc 'echo "login TZ=$TZ"; date "+%Y-%m-%d %H:%M:%S %z (%Z)"'
policyctl test && echo OK_policyctl
id | tr ' ' '\n' | grep policyeditors || echo "MISSING_policyeditors_membership"
SH
$```

---

## `maceff_tools` CLI guardrails
- Keep `--version` working (prints package version).
- Subcommands are **minimal** and language-agnostic in surface; Python-only implementation is OK.
- Time helpers honor `MACEFF_TZ`; **do not** guess geolocation.
- Checkpoints write to PA-public logs predictably.
- All shell interactions go through `maceff_tools` or documented Make targets; no hidden side effects.

---

## Researching & Sanitizing Legacy Policies
**Directory**: `LEGACY_POLICIES_NO_VCS/` (untracked; treat as input corpus)

### What to extract
- **Core/mandatory**: universal governance primitives (naming, instruction language, policy awareness) → refactor into `policies/base/`.
- **Core/primary**: delegation authority, team management, reprimand → converge to a single, minimal protocol each.
- **Supplemental**: remembrance/reflection/skills → convert to **opt-in** modules (feature flags later).
- **Drafts**: terminology and diagrams only; keep as R&D notes.
- **Optional/standards**: unify “strict/balanced/relaxed” into one policy with parameters (e.g., `quality_level: {strict|balanced|relaxed}`).

### Sanitization rules
- Remove duplication; collapse multiple near-duplicates (e.g., reprimand variants).
- Neutral tone; keep anthropomorphism *light* and functional.
- Replace manifestos with **checklists** and **decision trees**.
- Preserve provenance in commit messages: “Lifted from LEGACY: path/to/file.md § heading”.

### Integration workflow
1. Create `docs/policy/LEGACY_NOTES.md` (audit trail: kept/discarded/rationale).
2. Migrate *one concept per PR*: add minimal policy or extend an existing one.
3. Add tests/smoke prompts demonstrating the policy effect (small and repeatable).
4. After merge, `make policy-sync` and smoke test in container.

---

## Human-Centric Documentation Curation
- **Summaries first**: Each policy begins with a 3–5 line human summary before agent-facing checklists.
- **Cross-links**: Relative paths only; keep navigation obvious.
- **Two audiences**: Machine-ingestible structure (headings, bullets) *and* readable prose.
- **Graduation path**: `drafts/` → `optional/` → `base/` with human signoff recorded in commits.
- **Changelogs**: Major policy shifts get a short rationale in `docs/policy/LEGACY_NOTES.md`.

---

## Immediate Tasks Checklist (for the receiving agent)
1. **Git hygiene**: ensure `.gitignore` covers `.venv/`, sandbox mirrors, `LEGACY_POLICIES_NO_VCS/`, `.maceff/policies/`, and `*.bak.*`. Remove any committed leftovers.
2. **Policy baseline**: verify `policies/base/*` minimal set compiles under CEP-0; fix links; ensure `CLAUDE.md` reading order is correct.
3. **Sync path**: run `make policy-sync` and confirm `/opt/maceff/policies/current` → `sets/base`.
4. **Permissions**: validate groups, ACLs, and SGID/sticky bits (commands above).
5. **Time**: confirm `MACEFF_TZ` plumbing and `maceff_tools time` reflect local TZ.
6. **Legacy migration**: create `LEGACY_POLICIES_NO_VCS/` (untracked) and `docs/policy/LEGACY_NOTES.md`; propose first salvage PR (likely `INSTRUCTION_LANGUAGE_PROTOCOL.md` → concise checklist).
7. **Docs**: insert the updated Philosophy into `README.md`.

---

## Ready template (fill when starting real work)

$```
Ready:
objective: Build & harden MacEff baseline (policies, container, docs) for OSS use
next_steps: [git_hygiene, policy_sync_smoke, permissions_validate]
awareness:
  time: <TZ from env or UTC>
  budget: concise/default
  continuity: checkpoint before risky changes and at 85% context
$```

---