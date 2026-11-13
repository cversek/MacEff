# Framework Skills and Commands

The framework's invocable workflows are skills. Each is a folder under `framework/skills/`, named `maceff-<name>`, holding a `SKILL.md`, and `macf_tools framework install` links each folder into `.claude/skills/`. Type `/maceff-` to list them, or let the model invoke one when its description fits the situation.

Until #975 most of these were slash commands under one `maceff` namespace, nested by folder (`/maceff:task:start`). Remote Control doesn't list commands reached through a symlink, and the install linked the whole commands folder, so none of them appeared there. Skills installed as linked folders do appear, so the commands moved.

## The skills that were commands

| Skill | Was | Purpose |
|-------|-----|---------|
| `/maceff-task-start <task>` | `/maceff:task:start` | Start work on a task, restoring its context |
| `/maceff-task-archive` | `/maceff:task:archive` | Hide completed tasks from the task scanner |
| `/maceff-task-create-mission` | `/maceff:task:create_mission` | Create a MISSION task and its roadmap folder |
| `/maceff-task-create-experiment` | `/maceff:task:create_experiment` | Create an EXPERIMENT task and its protocol folder |
| `/maceff-task-create-phase` | `/maceff:task:create_phase` | Create a phase under a MISSION or DETOUR |
| `/maceff-task-create-detour` | `/maceff:task:create_detour` | Create a DETOUR task and its roadmap folder |
| `/maceff-roadmap-draft` | `/maceff:roadmap:draft` | Draft a roadmap after the pre-draft ceremony |
| `/maceff-roadmap-convert-from-experiment` | `/maceff:roadmap:convert_from_experiment` | Turn a validated experiment into a MISSION roadmap |
| `/maceff-experiment-draft` | `/maceff:experiment:draft` | Draft an experiment protocol |
| `/maceff-ccp` | `/maceff:ccp` | Write a consciousness checkpoint |
| `/maceff-jotewr` | `/maceff:jotewr` | Write the cycle-closing reflection |
| `/maceff-learnings-curate` | `/maceff:learnings:curate` | Curate learnings into the knowledge web |
| `/maceff-scholar-annotate` | `/maceff:scholar_annotate` | Bring an artifact's citations up to the scholarship policy |
| `/maceff-distill-wisdom` | `/maceff:distill_wisdom` | Distill artifacts into an agent definition |
| `/maceff-agent-bootstrap` | `/maceff:agent_bootstrap` | Bootstrap a new agent through policy engagement |

The old command files stay for one release as pointers: each still runs in the terminal and names the skill to use instead. They go in the next release.

## An agent's own commands

`.claude/commands/` remains the place for an agent's own commands, as real files. Keep them out of symlinks if they should appear in Remote Control.

## Older names

The flat names of v0.3.1 (`/maceff_ccp`, `/maceff_todos_start`) and the `:todos:` namespace of v0.3.2 map to the skills above: `/maceff-ccp`, and `/maceff-task-start <task_id>`.
