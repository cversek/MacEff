### Changed

- **The MacEff channel is now the MacEff Notification Channel** (MIS-0008 R01 to R03, R54): plugin id `maceff-notification-channel`, source `plugin:maceff-notification-channel:maceff`, module `macf.channels.notification_channel`, console script `maceff-notification-channel`. A clean break: a notice from the old source is refused, named on stderr, and recorded once as a `channel_source_refused` event. The input-origin classifier and the taint check now share one source constant.
  **Upgrade:** run `macf_tools agent init --update` so the daemon and the plugin change together, then restart the session.
