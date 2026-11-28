### Fixed

- **`pd status` names a staged declaration** (`macf/src/macf/pd/client.py`, #860 item 9): when `agent init` ran beside a live session it staged `declaration.json.cutover` and `pd status` still said "this agent has no primal daemon", with no hint that a declaration was waiting. It now names the staged file and the command that installs it, `macf_tools harness cutover`.
