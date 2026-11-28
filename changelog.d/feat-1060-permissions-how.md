### Added

- **`macf_tools permissions how`: how each recent call was approved** (GH#1060, autonomous_operation 5.5): derived from the event log with no new record, each tool call is listed as approved or denied at a dialog, let through by an allow rule of today's settings that covers the whole call (named with its file), or let through by the permission mode (in auto mode, its classifier). `--days`, `--last` and `--json`. The rules are today's, so a rule changed since a call isn't seen.
