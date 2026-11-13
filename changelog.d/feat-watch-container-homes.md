### Added

- **The outside watch reads the agent seats inside running containers** (`pd/watch.py`, policy `persistent_layer`): a container seat whose session stops beating is reported like a host agent, not missed (#979, #981).
