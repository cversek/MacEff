### Added

- **MIS-0008, Draft: voice for MacEff agents** (`framework/mis/MIS-0008-voice-input-channel.md`). It specifies the MacEff Voice Input Channel (wake phrase, hold and toggle hotkeys, a recording indicator, one capture unit per machine dispatching to each agent), voice generation with an agent-led voice selection, and a voice lock with a lockout and a raised guard. It also renames the MacEff channel to the MacEff Notification Channel. A working prototype follows in the same pull request.

- **The MacEff Voice Input Channel, its plugin side** (`macf.channels.voice_input_channel`, plugin `maceff-voice-input-channel`, MIS-0008 R04 to R08): utterances from the agent's own primal daemon arrive as labeled channel events. The label (trigger, time spoken, voice lock, screen state) comes before the words, a locked or unknown screen marks an utterance information only, and spoken markup is neutralized. It reuses the Notification Channel's server, which now lets a subclass choose its socket, record, event and hello.

### Changed

- **The MacEff channel is now the MacEff Notification Channel** (MIS-0008 R01 to R03, R54): plugin id `maceff-notification-channel`, source `plugin:maceff-notification-channel:maceff`, module `macf.channels.notification_channel`, console script `maceff-notification-channel`. A clean break: a notice from the old source is refused, named on stderr, and recorded once as a `channel_source_refused` event. The input-origin classifier and the taint check now share one source constant.
  **Upgrade:** run `macf_tools agent init --update` so the daemon and the plugin change together, then restart the session.
