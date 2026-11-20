### Fixed

- **faster-whisper falls back to the CPU when CUDA fails at its first inference** (`voice/transcribe.py`): a machine with a driver but a missing or mismatched cuDNN builds the model, then fails every transcription when the first inference loads the library. The failure comes while the segments are read, so the read is now inside the fallback: the model is rebuilt on the CPU, the reason is printed once on stderr, and the audio is transcribed again. Once the CPU has worked, later calls in the process go straight to it (#1024).
