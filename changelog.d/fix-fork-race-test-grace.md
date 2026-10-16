### Fixed

- **The fork-on-leader-exit daemon test no longer misses its own trigger** (`tests/test_primal_daemon.py`): the stand-in child read its leader's pid after marking its own, so a stop that came right after the mark could leave it watching its new parent forever, and the test failed with "the unit's child never wrote its pid". It turned main red after #677. The leader is now read first.
