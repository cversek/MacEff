### Added

- **`public_voice` 2.5: whose words on a public thread may steer an agent** (policy `public_voice`). Text from outside the trusted set (the operator and the maintainers the operator names) is data, never an instruction. The author is read from the forge, not from a signature. An outsider's request goes to the operator, and a trusted maintainer's work is still reviewed. A repository's thread guards (locked maintainer issues, hidden outsider comments on maintainer pull requests) narrow what reaches an agent without replacing the rule.
