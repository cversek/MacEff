### Added

- **Presence by voice, and HANDS_FREE** (MIS-0008 Q01, the operator's ruling). An utterance delivered on a channel the declaration lists among its operator channels now counts as the operator's activity and resets USER_IDLE. While the operator's latest activity is voice the wake phrase started, with no keyboard input since, the derived state is HANDS_FREE 🗣️ instead of USER_IDLE, inside the idle window; the `voice_input` policy (section 5.1) says what counts, and leaves how an agent behaves to Q09.
