### Fixed

- **`task scope set` and `task scope add` leave out a task that is already completed** (`macf/task/scope.py`, `cli.py`, policy `task_management`; #610). Before, a re-listed completed task read active and the stop gate waited on it.
