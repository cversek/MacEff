### Changed

- **A unit that runs a MacEff wrapper is refused at load if its stop grace is too short** (`pd/interface.py`, policy `persistent_layer` §3.2): a unit whose command runs `-m macf.pd.watched_unit` or `-m macf.pd.broker_unit` needs `stop_grace_s` of at least `WRAPPER_UNIT_STOP_GRACE_S` (15 s), or the daemon kills the wrapper before it can stop its program (#1001, #1002).
  **Upgrade note:** a declaration that names such a unit by hand at the default 10 s, a broker unit written into an agent's own declaration included, now stops the daemon from starting. Before upgrading, set `stop_grace_s: 15` on each; the refusal names the unit and the fix.
