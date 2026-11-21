### Fixed

- **A container's default session carries the deployment's `container_env`** (`docker/scripts/start.py`, `pd`): a session the daemon starts now sees the variables login shells already did. A `container_env` PATH adds its directories, and a malformed entry is left out with a warning (#895, #982).
