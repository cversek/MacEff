### Fixed

- **The broker's pending count includes agent mail, and says how long the oldest has waited** (`amail/broker.py`, `cli.py`, MIS-0004 R32): `status` counted only internet mail (`*.eml`) in a pickup box, so agent bundles (`*.amsg`) waiting for their recipient never counted, and a container experiment read two waiting bundles as zero. It now counts both, and adds `oldest_pending_s`, the age of the oldest waiting message, kept out of the audited count total like the budget. `amail status` shows the age beside the count. An entry the recipient set aside as `.refused` is not pending.
