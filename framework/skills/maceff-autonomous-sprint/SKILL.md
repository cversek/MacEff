---
name: maceff-autonomous-sprint
description: "DEPRECATED — split into maceff-sprint (workload-defined) and maceff-play-time (time-bounded). Use the appropriate sibling skill based on whether you are launching scope-completion work (sprint) or time-bounded exploration (play_time)."
allowed-tools: Bash, Read, Grep, Glob
---

**DEPRECATED** — This skill has been split into two narrower siblings:

- **`maceff-sprint`** — 🏃‍♂️ Workload-defined autonomous work. Use when the user names a task set to complete ("finish this MISSION", "run this pipeline"). No timer. Scope completion gate. Markov recommender disabled.
- **`maceff-play-time`** — ⏲️ Time-bounded autonomous exploration. Use when the user specifies a time allotment ("explore for an hour", "work for 2 hours"). Mandatory timer. Predetermined work-mode chain. Markov recommender after chain exhaustion.

Use the appropriate sibling skill based on the nature of the work. This directory is preserved for backward compatibility with agent definitions that reference the old skill name.

**See policies:** `autonomous_sprint.md` (SPRINT semantics), `play_time.md` (PLAY_TIME semantics)
