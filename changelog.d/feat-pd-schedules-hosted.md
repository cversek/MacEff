### Added

- **A vanilla account that declares a primal daemon is refused when `agents.yaml` loads** (`models/agent_spec.py`, policy `persistent_layer` 10.1; MIS-0002-R11). A vanilla account gets no MacEff footprint, so its declared units and schedules would have no daemon to run them; CI loads every deployment's `agents.yaml`, so it fails there. `test_schedules_hosted` also checks that a daemon builds a scheduler for exactly the schedules its declaration holds. Planting the defect (the refusal removed) fails the test.
