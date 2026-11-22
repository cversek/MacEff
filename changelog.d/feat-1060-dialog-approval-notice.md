### Added

- **The agent hears when the operator approved its previous call at a dialog** (GH#1060, autonomous_operation 5.5): at each call's start, one line in the agent's context says the session's previous call ran on the operator's answer to a permission dialog, not on a rule, so an agent unsure of the operator's presence can tell the two apart. Only that exception is said, once, and nothing is recorded for it; the read goes back only to the previous call (about 10 ms on a 370 MB log). A call a rule or the mode let through says nothing, and a denial the client already reports.
