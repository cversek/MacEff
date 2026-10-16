### Changed

- **A unit's declared agent home must be the agent's own** (`pd/core.py`, policy `persistent_layer` §11.2): a `MACEFF_AGENT_HOME_DIR` that resolves elsewhere is refused at load, since the unit would write its events where the daemon never reads. `harness cutover` no longer checks a session unit's liveness variables, which the daemon now sets itself.
