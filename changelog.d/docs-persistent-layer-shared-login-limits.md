### Changed

- **Policy `persistent_layer` §10.6 states what a shared login means for all three entry controls** (MIS-0002-R136): the ask rule on adding, revocation and the check-template rule each stop a confused agent, not a compromised one, on a login the agent shares with the operator, and are held where the agent can't write on its own account. The section's DRAFT banner is gone, since the scheduler's trial build it described is on `main`.
