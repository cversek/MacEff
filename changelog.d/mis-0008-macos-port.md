### Added

- **MacEff voice on macOS** (MIS-0008 R14; `macf.voice.capture.macos`, `macf.voice.speech.macos`, `macf.voice.capture.platform`). The capture unit, the trial, `voice wake record` and the speech worker now run on a Mac. The microphone is read through PortAudio and access is asked for through AVFoundation, refused by name when denied. The lock state comes from Quartz's session dictionary, and a session off the console counts as locked. The indicator is a non-activating AppKit panel fed the Linux overlay's lines, and trigger keys are read from declared keyboards through the HID manager. Speech plays through one shared stream, with peaks kept under full scale and resampled to the device's rate, and Kokoro runs on the GPU through mlx-audio. `capture/platform.py` is the one place a platform's backends are chosen.
- **The capture unit answers for its own microphone on a Mac** (`macf.voice.capture.disclaim`). macOS grants the microphone to the responsible process, which under a primal daemon is the daemon's Python. The unit re-spawns itself with responsibility disclaimed, from a bundle that carries a microphone usage description, and its liveness speaks for the pid the daemon started.
- **An accent as its own respelling table** (`macf_tools voice accent on|off`, `voice speak --accent --say-as`), which the operator can switch off when it gets in the way of being understood.
- **`microphone` and `input_monitoring` unit grants**, for a capture unit's declaration on a Mac.

### Fixed

- **The voice extra installs what it says it does:** kokoro-onnx, and the macOS packages.
