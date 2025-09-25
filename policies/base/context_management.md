# Context Management (Base · Minimal)

This module keeps behavior **time-aware**, **token-aware**, and **compaction-ready** while staying language-agnostic. It describes *what* to do; a project gateway (e.g., `maceff_tools`) may provide adapters.

---

## 1) Time Awareness (lightweight)
- Decide what time context matters (deadlines, cadence, durations).
- If a gateway exists, request a reliable “now”; otherwise:
  - state your assumption (e.g., “treating now as local system time”)
  - convert relative phrases to explicit timestamps in outputs.
- Prefer short plans with explicit dates/times when relevant.

## 2) Token / Context Budget Awareness
- Aim to protect headroom for answers and follow-ups.
- If a gateway provides signals, use them; otherwise **estimate** and be concise by default.
- Reference thresholds (illustrative, not enforced):
  - **warn** ≈ 0.85 of budget: switch to terse outputs; suggest checkpoint.
  - **hard** ≈ 0.95 of budget: require checkpoint before continuing.

> Projects can tune these via config (e.g., `thresholds.token_warn` / `token_hard`).

## 3) Compaction Readiness (when to checkpoint)
Create/refresh a **checkpoint note** when any of these hold:
- long session, large context, or nearing token **warn** threshold
- before long-running work or major context changes
- after receiving critical instructions or producing key artefacts

**Checkpoint note (keep brief):**
- `objective:` one line  
- `next_steps:` 1–3 bullets  
- `blockers:` if any  
- `artefacts:` filenames/links/IDs  
- `policy_refs:` pages you relied on (e.g., core_principles, delegation)  
- `time:` explicit timestamp or assumption  
- `agent:` stable ID / role

If a gateway exists, request persistence; otherwise **emit the note in your reply** so a human/tool can capture it.

## 4) Resume & Reconcile
On resume or after suspected compaction:
1) search for the latest checkpoint (gateway or recent messages)  
2) restate objective + next steps; ask to confirm if ambiguous  
3) rebuild a small working context (artefact links, recent decisions)

## 5) Communication Defaults
- Default to concise, structured outputs; escalate detail on request.
- Make constraints explicit: time assumptions, token posture, and whether a checkpoint was taken.

---

## Configuration surface (examples)
```
features:
  time_awareness: true
  token_awareness: true
  checkpoints: true
thresholds:
  token_warn: 0.85
  token_hard: 0.95
```

This file defines behavior; specific commands live in project tooling, not here.
