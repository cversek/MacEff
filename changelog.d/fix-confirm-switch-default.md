### Changed

- **`inject model` answers the client's "Switch model?" dialog by default** (`supervisor.py`, `cli.py`, policy `capability_boundaries` §5.1). The dialog is drawn only in the terminal. Left for a person, it froze a session the operator was driving over Remote Control, so he had to go to the terminal to answer it. His ruling: "Just make the default the one that doesn't strand your session." The follower still answers only a dialog that offers the model asked for, once. `--no-confirm` replaces `--confirm-switch` and leaves the dialog for a person.
