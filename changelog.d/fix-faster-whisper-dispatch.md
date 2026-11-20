### Fixed

- `voice transcribe` on Linux: `detect_engine()` chose faster-whisper but `transcribe()` had no branch for it, so every run failed with "Unknown engine" (#1013). faster-whisper now transcribes, on the GPU when CUDA loads and on the CPU otherwise.
