### Fixed

- **`task scope set` replaces the scope's open tasks** (`cli.py`, #951). It appended its tasks and left every earlier one in place, so a task the new list left out kept the stop gate waiting, against what `task_management` and `autonomous_sprint` say. An active or paused task the list leaves out now leaves the scope, and the command names it. Completed members stay as the scope's history, a running sprint or play time is still re-included, and a `scope set` that scopes nothing changes nothing.
