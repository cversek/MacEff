### Added

- **The tray gets a LaunchAgent of its own, so launchd keeps it running** (`macf/platform/launchd.py`, `macf_tools pd tray install|uninstall`, policy `persistent_layer` 9.1; #747).
  - **Before:** nothing kept the tray up. Started from an agent's session, it died when that session restarted.
  - **The job:** `maceff_tray`, one per GUI user and outside every agent's primal daemon. A crash or kill is relaunched; Quit stays quit until the next login.
  - **Refused, with the reason,** where the host can't show the tray (R73), or where the installing interpreter can't import the tray as launchd would run it.
  - **`--plan`** on both verbs prints the steps and changes nothing.

### Changed

- **The R68 test now looks for imports of the tray, not for its name** (`macf/tests/test_pd_tray.py`). `pd tray install` names `macf.tray` as the program launchd runs, and never imports it; the runtime test that blocks the tray's import still covers every layer module.
