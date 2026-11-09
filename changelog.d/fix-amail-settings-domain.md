### Fixed

- **A container agent's mail settings name the deployment's domain** (`docker/scripts/start.py`, MIS-0004 R45). Start-up wrote only `handoff` and `agent` into each agent's `.maceff/amail.json`, so the receiver never knew which broker's record of acceptance it could trust, and a signature by a key since retired could not verify mail accepted inside its window. It now also writes the addressing's `domain`.
