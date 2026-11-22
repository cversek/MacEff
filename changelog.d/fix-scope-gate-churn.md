### Fixed

- **The idle-stop failsafe counts progress, not activity** (#1119). A blocked Stop resets the count only when a tool call since the previous one is new or returned a new result; re-running a check whose answer has not changed counts as idle. The count lives in the event log (`scope_gate_held`) and starts fresh at the operator's prompt. At fail-open the scope gate pauses the scope with a churn record. The sprint nag, the countdown and `task pause` on a scoped task name `task scope pause`.
- **Budget mode `conserve` has an effect** (#1120): the failsafe yields on the first idle Stop. A mode that lapses after the weekly window is announced once in the budget notice.

### Changed

- `autonomous_sprint`: a forced turn has a price, and waiting on compute or another seat with ready work exhausted is a required pause. `credit_budget`: conserve's effect and the lapse notice.
- PA preamble v1.10: a Budget section pointing at `credit_budget` and the scope pause.
