### Changed

- **MIS-0005 (draft): a unit's exit-code contract may be the default** (`framework/mis/MIS-0005-unit-exit-code-contract-default.md`, policy `persistent_layer`). It updates MIS-0002-R09 to say what the declaration model already does: a unit states its command, account, restart policy and liveness interval, and its exit-code contract only when it means something other than the default (exit 0 is success, exit 78 asks not to be restarted). No declaration changes. One test names the requirement; two planted defects (a dropped default, a defaulted liveness interval) each fail it.
