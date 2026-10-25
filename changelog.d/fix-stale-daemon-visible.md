### Fixed

- **A primal daemon older than its CLI now says so** (`macf/src/macf/pd/build.py`, `client.py`, `daemon.py`, `cli.py`; MacEff #816). A daemon keeps the code it started with until its unit restarts, and nothing said when it drifted behind the checkout. Two hosts found theirs days behind on the same day.
  - The daemon reports its build in every status reply.
  - `pd status` prints it beside the command's own build, and warns when they differ or when the daemon is too old to say.
  - A verb the daemon doesn't know is refused as "this daemon is older than this command", with the update step, instead of the request parser's message.
  - `persistent_layer` says how to keep the daemon current: install, then restart its unit. The session is carried across the restart.
  - Tested through a real daemon and the real client. Planting each defect fails its test.
