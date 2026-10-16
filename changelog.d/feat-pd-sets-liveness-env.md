### Changed

- **The daemon tells each unit which unit it is and how often it beats** (`pd/core.py`, `pd/interface.py`, policy `persistent_layer` §11.2): `MACF_PD_UNIT`, `MACF_PD_LIVENESS_S` and `MACEFF_AGENT_HOME_DIR` are added to a unit's environment from the unit's own name, interval and agent home. They no longer have to be typed into every declaration, where a missing or mistyped value silently stopped the unit's liveness. A declared value that disagrees with the unit is refused at load.
