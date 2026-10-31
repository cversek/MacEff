### Fixed

- **The scope gate's idle-stop failsafe counts down for every agent in a shared container** (`task/scope_gate_failsafe.py`): the counter moves from a bare `/tmp/macf/` to this user's private runtime directory (`utils.paths.user_runtime_dir`). The first account to create `/tmp/macf/` owned it, so every other agent's write failed in silence, its counter read 5 on every Stop, and the failsafe meant to end an idle-stop loop after five stops never fired. A counter that cannot be saved now raises a warning instead of passing unseen.
