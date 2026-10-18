### Fixed

- **The session wrapper passes each channel as its own argument** (`utils/harness.py`, `render_child`). `--channels` takes every value up to the next flag, and the wrapper joined several channels with a comma, so two channels reached the client as one value. With one channel, as every deployment has had so far, the bug couldn't show. Adding the MacEff channel beside the operator's own would have sent both as a single malformed entry, and the operator's channel would have gone down with it. One test; the comma join, planted back, fails it.
