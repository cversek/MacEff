# Porting MacEff voice to a new platform

**For:** whoever brings the voice subsystem (MIS-0008) up on a platform other than Linux, macOS first.
**Status:** written from the Linux bring-up. The macOS notes in section 6 are suggestions, not tested; correct them as you go.

---

## 1. What is portable and what is not

The capture logic, the wake check, the end window, the stop words, the voice lock, dispatch, and the speech queue are the same everywhere. **Five things differ by platform.** Each sits behind a small interface with a contract check.

| Backend | Interface | What it does | Linux reference | Contract check |
|---|---|---|---|---|
| Audio in | `capture.backends.AudioIn` | Opens the microphone, reads 80 ms frames of 16 kHz mono int16, closes it | `capture.linux.PipeWireAudio` (`pw-record` on a pipe) | `capture.contract.check_audio_in` |
| Lock state | `capture.backends.LockState` | `unlocked`, `locked` or `unknown`; never raises | `capture.linux.LinuxLockState` (logind and known lockers) | `capture.contract.check_lock_state` |
| Indicator | `capture.backends.Indicator` | Shows the agent and mode, a waveform, a volume trace, and the end window while recording | `capture.linux.OverlayIndicator` (a layer-shell overlay process) | `capture.contract.check_indicator` |
| Triggers | `capture.backends.TriggerSource` | Key presses and releases from declared devices; `poll()` never blocks | `capture.linux.EvdevTriggers` (input devices read directly) | `capture.contract.check_trigger_source` |
| Audio out | `speech.backends.AudioOut` | Plays a spoken sentence; `stop()` works from any thread | `speech.backends.PipeWireOut` (`pw-cat`) | `speech.backends.check_audio_out` |

The models aren't platform code. The wake features (openWakeWord), the speech check (Silero) and the voice (Kokoro) all run on ONNX Runtime, and transcription already picks `mlx-whisper` on Apple Silicon (`voice.transcribe.detect_engine`). Each needs only its packages and model files on the new machine.

**The rules a backend must keep come from MIS-0008, not from the Linux code:**
- R13: raw audio never touches the disk. Pipes and memory only.
- R15: listening off means the microphone isn't read. Close the device rather than discarding frames, so the platform's own microphone light agrees.
- R07: a lock state that can't be read is `unknown`, which counts as locked.
- R18: no socket, pipe or command line can press a key for the capture unit. It reads its trigger devices itself.
- R21: the indicator shows only while recording, and a desktop that can't show it refuses before any recording.

## 2. Knowing a backend is right

Each check raises an `AssertionError` naming the first broken promise:

```python
from macf.voice.capture import contract
contract.check_audio_in(MyMicrophone)        # a function that makes a fresh one
contract.check_lock_state(MyLockState())
contract.check_indicator(MyIndicator())
contract.check_trigger_source(MyTriggers(devices))
```

Add your backends to `macf/tests/test_voice_backends.py::test_every_backend_passes_its_contract`, under a platform guard as the Linux ones are. Backends that open the real microphone or draw on the real screen go in the live test, which runs only with `MACF_VOICE_LIVE_TESTS=1`.

A contract check proves the interface, not the experience. Section 5 lists what only a live trial showed on Linux.

## 3. Where a platform's backends are chosen

Today four places refuse anything but Linux, each with a message pointing here. Add a branch for the new platform in each:

- `voice/capture/__main__.py`: `build` (one agent's unit) and `_platform_backends` (a system daemon's unit for its members).
- `voice/capture/trial.py`: `build`, for `macf_tools voice capture trial`.
- `voice/speech/__main__.py`: `main` constructs `PipeWireOut` and the Linux lock state for the speech worker.

Keep the platform imports inside the branch, so one platform's modules never load on another.

## 4. The order to bring it up

Each step has a check that fails if the step went wrong.

1. **Transcription from memory.** `transcribe_array` on a second of silence, then on a spoken clip. The check: the words come back, with no file written.
2. **Audio in.** Pass `check_audio_in`, then read a few seconds and look at the levels. The check: speech is clearly louder than the room, and the platform's microphone light turns off on `close()`.
3. **Lock state.** Pass `check_lock_state`, then lock the screen and read it. The check: `locked` while locked, `unlocked` after.
4. **Indicator.** Pass `check_indicator`, then feed it real frames. The check: the waveform moves with your voice and the window drains in a pause.
5. **A live trial.** `macf_tools voice capture trial --phrase "<phrase>" --model <model>` with the operator. The check: each call the operator counts either wakes or prints a near-fire line saying how close it came.
6. **The wake model, retrained on this machine.** `voice wake define`, `record`, `train`, `test` on this microphone. A model trained on another machine's microphone and room is a different model (`voice_input` policy, section 1). The check: the test report, then a live trial with counted calls.
7. **Triggers.** Pass `check_trigger_source`, then hold and toggle with the declared keys. The check: one utterance per hold and per toggle, with the right trigger in the trial's output.
8. **Audio out and the speech worker.** Pass `check_audio_out`, then `macf_tools voice speak`. The check: speech plays, and stops when a recording opens (R29).
9. **The declaration.** A `voice` section, with the capture and speech units declared on the agent's daemon. The check: `voice capture status` shows the unit listening, and an utterance arrives in the session as a voice message.

## 5. What the Linux trials taught

Every one of these passed its tests and still failed with the operator at the microphone:

- **The end of an utterance belongs to the speaker.** A 1.2 s pause cut the operator off mid-thought. The end window (R56) holds for 2 s of quiet, then drains to empty at 5 s, and speech refills it. The stop words "send" and "abort" end it at once.
- **Transcription mishears the stop words.** Whisper wrote "send" as "Sand". The accepted spellings are a table in `capture/unit.py`. Add one only from a real mishearing, never from a guess.
- **A vocabulary prompt matters more than the model.** The operator's everyday dictation was better mainly because it primed Whisper with names and jargon. Set `transcription_prompt` in the voice section.
- **A helper process must not share the terminal's process group.** A Ctrl-C meant for the trial reached the recorder first, and the stop read as a broken stream. Start the recorder and the overlay in their own session.
- **The system's own sounds can fire the wake model.** A tone played when the microphone opened scored 1.0 on a model trained on speech and room noise. Score your platform's tones against the model before trusting it.
- **A busy machine makes misses that aren't the model's.** Training on the same machine during a trial starved the listener of audio. Keep the machine quiet while measuring.
- **Count the calls.** The trial counts wakes; only the speaker knows how many tries it took. Agree a number before starting.

## 6. macOS: suggestions, untested

None of this has been run. It records where the Linux bring-up would look first on a Mac.

- **Audio in:** read 16 kHz mono int16 from the default input through a library such as `sounddevice` (PortAudio), or a subprocess such as `ffmpeg -f avfoundation`, in its own session. The first open triggers macOS's microphone permission dialog for the process that runs the unit, so run the trial once from the same environment the unit will run in.
- **Lock state:** Quartz's `CGSessionCopyCurrentDictionary()` carries `CGSSessionScreenIsLocked` while locked. If the key or the call is missing, answer `unknown`.
- **Indicator:** a small borderless, non-activating window (an `NSPanel` through PyObjC, say) that never takes focus, in its own process fed one line per call, as on Linux.
- **Triggers:** a global key listener (a Quartz event tap) needs the Input Monitoring permission. It must be read inside the capture unit and must not open a socket or accept presses from another process (R18).
- **Audio out:** the same library as audio in, or `afplay` fed from a pipe. `stop()` must interrupt mid-sentence.
- **Transcription:** `mlx-whisper` is already the default engine on Apple Silicon. Confirm `transcribe_array` passes `initial_prompt` through on that path.
