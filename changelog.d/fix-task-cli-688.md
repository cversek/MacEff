### Fixed

- **Three task CLI defects found while creating a MISSION's phases** (`cli.py`, policy `task_management` 9.7; cversek/MacEff#688):
  - `task create phase --blocked-by` no longer swallows a title placed after it. It takes one task per flag, repeated or as a comma list.
  - `task metadata set <id> title` keeps a phase's 📋. The recompose now passes the plan reference and custom fields, as reparent already did.
  - `task block A B` and `task unblock A B` write the edge `task start` enforces, B's `blockedBy`, instead of a `blocks` entry on A that nothing read. `unblock` also clears such an entry if the old command left one.
  - Four tests against a real task store; five planted defects each caught, including each original bug.
