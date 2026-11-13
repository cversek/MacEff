### Added

- **MIS-0008, Draft: voice for MacEff agents** (`framework/mis/MIS-0008-voice-input-channel.md`). It specifies the MacEff Voice Input Channel (wake phrase, hold and toggle hotkeys, a recording indicator, one capture unit per machine dispatching to each agent), voice generation with an agent-led voice selection, and a voice lock with a lockout and a raised guard. It also renames the MacEff channel to the MacEff Notification Channel. A working prototype follows in the same pull request.

- **The MacEff Voice Input Channel, its plugin side** (`macf.channels.voice_input_channel`, plugin `maceff-voice-input-channel`, MIS-0008 R04 to R08): utterances from the agent's own primal daemon arrive as labeled channel events. The label (trigger, time spoken, voice lock, screen state) comes before the words, a locked or unknown screen marks an utterance information only, and spoken markup is neutralized. It reuses the Notification Channel's server, which now lets a subclass choose its socket, record, event and hello.

- **The daemon's carriage of an utterance, for one agent** (`macf.pd.voice_carriage`, MIS-0008 R10 to R12, R40). A declaration's new `voice` section names its capture unit, which must be a declared service unit, and holds the lockout settings (three attempts and ten minutes by default). An `utterance` request on the control socket is taken only from a process of that unit. The daemon gives each utterance its id, sends it on its own voice socket to a Voice Input Channel below the session, and answers every one with a receipt. An utterance with no channel attached is refused, not held. Each leaves a `pd_voice_utterance` event with its metadata and length, never its words. `agent init` installs the voice plugin and its launch flag only where a voice section is declared, and a voice section is refused at load if a declared channel allowlist leaves the voice channel out.

- **The capture unit** (`python -m macf.voice.capture`, MIS-0008 R13 to R18, R21, R22, R27). A declared unit that listens for its agent's wake phrase and takes the hold key and continual voice from declared trigger devices. It shows a recording indicator with the agent, the mode, a waveform and a volume trace, and hands each utterance to its daemon. The logic is platform-free behind four backends with contract checks a porter runs (`macf.voice.capture.contract`). The Linux backends use `pw-record`, kernel input events read directly, the screen locker or logind's lock hint, and a GTK layer-shell overlay. Its microphone state rides its liveness beat into the daemon's status. New commands: `macf_tools voice listen [on|off]` and `voice capture status`. Its models are in the new `voice` extra.

### Fixed

- **Transcription on Linux** (`macf.voice.transcribe`): detection offered faster-whisper, but the dispatch had no branch for it, so every Linux transcription raised "Unknown engine". It now runs, and `transcribe_array` transcribes samples held in memory.

### Changed

- **The MacEff channel is now the MacEff Notification Channel** (MIS-0008 R01 to R03, R54): plugin id `maceff-notification-channel`, source `plugin:maceff-notification-channel:maceff`, module `macf.channels.notification_channel`, console script `maceff-notification-channel`. A clean break: a notice from the old source is refused, named on stderr, and recorded once as a `channel_source_refused` event. The input-origin classifier and the taint check now share one source constant.
  **Upgrade:** run `macf_tools agent init --update` so the daemon and the plugin change together, then restart the session.
