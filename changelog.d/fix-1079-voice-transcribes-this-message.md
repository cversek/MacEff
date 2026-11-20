### Fixed

- **The prompt hook transcribes the voice message it was given, not the newest file in the inbox** (#1079). It took the newest `.oga` in the account-default inbox, so before the message was downloaded a clip from months earlier was transcribed and shown as the message. It now looks in the plugin's state directory (`TELEGRAM_STATE_DIR`, else the default) and accepts only a file written at or after the message's own time; otherwise it says how to download this message by its `file_id`.
