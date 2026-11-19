### Added

- **Host-wide voice claims** (MIS-0008 R26, for per-agent capture units on one host before the shared unit of R46). Each agent's own capture unit claims its keys and wake phrase in a registry in the daemon runtime directory (`voice-claims.json`) before it listens; a key or phrase another live agent on the host already holds refuses the start with R26's message. A claim whose unit has died no longer counts, and an agent's new claim replaces its own old one (`macf.voice.capture.claims`).
