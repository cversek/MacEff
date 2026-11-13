### Fixed

- **The broker unit's stop grace outlasts its wrapper's stop path** (`pd/broker_unit.py`, `pd/broker_defaults.py`, policy `persistent_layer` §3.5): the default broker unit is declared with 15 s, a 2 s poll plus 10 s for mosquitto with margin, so a stop no longer leaves mosquitto running on its port (#992, #998).
