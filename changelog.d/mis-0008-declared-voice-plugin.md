### Fixed

- **`agent init` keeps the voice plugin an agent declares** (MIS-0008). Plugins install per login, so a second agent on a login runs the Voice Input Channel from a marketplace of its own and allowlists it so. Init now gives the harness that plugin and never installs the packaged `maceff-voice-input-channel@maceff` in its place, which would have loaded another agent's channel server into the session; if the declared plugin isn't installed, the channel step says so and names it.
