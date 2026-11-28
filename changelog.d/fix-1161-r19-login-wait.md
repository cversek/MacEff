### Changed

- **A session that can't log in waits on a person instead of reading failed** (`pd/core.py`, `pd/interface.py`, `pd/watch.py`, `pd/cli.py`, `utils/attach.py`, `transcript_monitor/daemon.py`, `pd/login.py`; MIS-0010 amends MIS-0002-R19 and adds R202 to R204; policy `persistent_layer` §4 and §5.1, #1161):
  - A login failure now puts the session in `waiting_on_a_person`, with `waiting_on: login` in its state record and in the daemon's status. The session stays running, so a person can attach and run `/login`. "Failed" sent people to the host when the session was waiting for them.
  - The outside watch reads AUTH-FAILED from that field at its first pass, with no allowance (R202), and a prompt wait never reads as one.
  - The keystroke fallback holds while the login wait lasts, so nothing is typed into a `/login` flow (R203).
  - The wait ends when the stored credential is renewed, read from its two expiry dates at most once a minute (R204). A login in one session therefore returns every session that shares the credential, not only the one where it was typed.
  - A login-waiting session whose beat stops is still caught as dead. A daemon adopts a wait recorded as `failed` by an earlier build, so a seat whose wait spans the upgrade isn't started twice.
  - Eight new or rewritten tests; seven planted defects each turn at least one red.
