### Changed

- **A session that can't log in waits on a person instead of reading failed** (`pd/core.py`, `pd/interface.py`, `pd/watch.py`, `pd/cli.py`, `utils/attach.py`, `transcript_monitor/daemon.py`, `pd/login.py`; MIS-0010 amends MIS-0002-R19 and adds R205 to R207; policy `persistent_layer` §4 and §5.1, #1161):
  - A login failure now puts the session in `waiting_on_a_person`, with `waiting_on: login` in its state record and in the daemon's status, or `credential` when the client rejected an API key, where the remedy is a new key rather than `/login`. The session stays running, so a person can attach and fix it. "Failed" sent people to the host when the session was waiting for them.
  - The outside watch reads AUTH-FAILED from that field at its first pass, with no allowance (R205), and a prompt wait never reads as one.
  - Nothing in the layer types into the session while it waits (R206). The keystroke fallback holds on the core's word, and on a login screen without it.
  - The wait ends when the stored credential is renewed, read from its two expiry dates at most once a minute (R207). A login in one session therefore returns every session that shares the credential, not only the one where it was typed.
  - A login-waiting session whose beat stops is still caught as dead. A daemon adopts a wait recorded as `failed` by an earlier build, so a seat whose wait spans the upgrade isn't started twice.
  - Eleven new or rewritten tests; seven planted defects each turn at least one red.
