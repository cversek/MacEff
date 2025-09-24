# Context Management (Base Policy)

Minimal, language-agnostic rules for time/token awareness and continuity across resets (compaction). Behaviors are **configurable** and **advisory**; concrete hooks come from tooling (e.g., `maceff_tools`).

---

## 1) Time Awareness
- Always know **now** and be able to compare timestamps.
- When planning, include **ETA** or time-box (if relevant).
- If time constraints make quality risky, **signal early** and propose options.

**Adapters expected:** `time_now()`, `duration_since(t)`  
**Example behavior:** “This will take ~25–40 min; we have 20 min left—recommend reducing scope A or deferring B.”

---

## 2) Token / Context Awareness
- Track approximate **tokens used** and **headroom** (model/context limits).
- When near thresholds, **summarize** and **shrink**: bulletize, remove fluff, link to artefacts.
- If continuing risks truncation, **checkpoint** first (see §3).

**Adapters expected:** `tokens_left()`, `near_limit({warn, hard})`  
**Config surface (illustrative):**
- `token.thresholds.warn = 0.85`
- `token.thresholds.hard = 0.95`
- `token.actions = { warn: "summarize", hard: "checkpoint_then_continue" }`

---

## 3) Checkpoints (Continuity Across Compaction)
When a reset or context loss is likely (hard token limit, tool handoff, long-running work), create a **checkpoint** that captures:
- **Objective** (current goal in <140 chars).
- **State** (key decisions, constraints, artefact links).
- **Next 1–3 actions**.
- **Timestamps** (created at, last updated).
- **Version** (schema/hash if used).

After resuming, **restore** from the latest checkpoint and restate: objective, state, and next actions.

**Adapters expected:**  
`checkpoint_write(data) -> id`, `checkpoint_read(id?) -> data`, `checkpoint_list() -> [ids]`

**Config surface:**  
- `continuity.checkpoints.enabled = true`  
- `continuity.checkpoints.location = "policy://current/"` (abstract)  
- `continuity.checkpoints.autosave = { on_warn: true, on_hard: true }`

---

## 4) Compaction Preparation & Recovery
**Preparation (before compaction/reset likely):**
1. **Summarize** current thread in ≤10 bullets.
2. **Checkpoint** (objective, state, next actions, artefacts).
3. **Minimize** the working context (remove redundant prose, keep references).

**Recovery (after reset):**
1. **Load** latest checkpoint.
2. **Reconstruct** brief working context (objective, state, next actions).
3. **Verify** critical references (links/paths still valid).
4. **Continue** or request missing info.

---

## 5) Communication Rules (re: context)
- Be explicit about **limits** (“I’m near token cap—saving a checkpoint.”).
- Prefer **stable references** to artefacts (paths, IDs) over long inline blobs.
- Use **structured summaries** to compress (lists, tables, key:value).

---

## 6) Minimal Operational Checklist
- Track: **objective**, **next actions (≤3)**, **blockers**, **timebox**.
- On **warn** threshold: summarize + shrink.
- On **hard** threshold risk: checkpoint → continue.
- After resume: load checkpoint → restate plan.

---

## 7) Invariants
- Do not silently lose state—**announce** compaction risks and mitigations.
- Checkpoints must be **brief, reproducible, restorable**.
- Prefer **fewer, higher-quality** checkpoints over noisy frequent ones.

---

**Notes for implementers:**  
This policy assumes the environment exposes time, token, and checkpoint adapters. A reference implementation may live in `maceff_tools` with project-tunable parameters, but the policy remains language-agnostic.
