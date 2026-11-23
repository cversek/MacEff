"""Voice transcription engine with platform-selective backend.

Supports:
- mlx-whisper (Apple Silicon, primary)
- faster-whisper (Linux/container, fallback)
- openai-whisper (universal fallback)
"""

import subprocess
import sys
import json
import time
import tempfile
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class TranscriptSegment:
    """A segment of transcribed text with timing."""
    text: str
    start: float = 0.0
    end: float = 0.0
    confidence: float = 0.0
    speaker: Optional[str] = None


@dataclass
class TranscriptResult:
    """Complete transcription result."""
    text: str
    segments: list
    language: str = "en"
    engine: str = "unknown"
    model: str = "unknown"
    duration_audio: float = 0.0
    duration_transcribe: float = 0.0

    def to_dict(self):
        return {
            "text": self.text,
            "segments": [asdict(s) if isinstance(s, TranscriptSegment) else s for s in self.segments],
            "language": self.language,
            "engine": self.engine,
            "model": self.model,
            "duration_audio": self.duration_audio,
            "duration_transcribe": self.duration_transcribe,
        }


def convert_to_wav(input_path: str, output_path: Optional[str] = None) -> str:
    """Convert audio file to 16kHz mono WAV using ffmpeg."""
    input_p = Path(input_path)
    if output_path is None:
        output_path = str(input_p.with_suffix('.wav'))
        # If same extension, use temp file
        if input_p.suffix.lower() == '.wav':
            tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            output_path = tmp.name
            tmp.close()

    try:
        subprocess.run([
            'ffmpeg', '-i', str(input_path),
            '-ar', '16000',
            '-ac', '1',
            '-y',
            '-loglevel', 'error',
            output_path
        ], check=True, capture_output=True, text=True)
    except FileNotFoundError:
        print("⚠️ MACF: ffmpeg not found — required for audio conversion", file=sys.stderr)
        raise
    except subprocess.CalledProcessError as e:
        print(f"⚠️ MACF: ffmpeg conversion failed: {e.stderr}", file=sys.stderr)
        raise

    return output_path


def detect_engine():
    """Detect best available transcription engine for this platform."""
    import platform

    # Apple Silicon: prefer mlx-whisper
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx_whisper
            return "mlx"
        except ImportError:  # noqa: S110 - not installed is the normal miss; the next engine is probed
            pass

    # Linux/other: prefer faster-whisper
    try:
        import faster_whisper
        return "faster-whisper"
    except ImportError:  # noqa: S110 - not installed is the normal miss; the next engine is probed
        pass

    # Universal fallback: openai-whisper
    try:
        import whisper
        return "whisper"
    except ImportError:  # noqa: S110 - not installed is the normal miss; None is returned if no engine loads
        pass

    return None


#: Whisper skips a word that a silence this long surrounds (its hallucination_silence_threshold).
MLX_SILENCE_S = 1.0
#: A segment Whisper itself thinks is probably silence, decoded with little confidence, is dropped.
NO_SPEECH_DROP = 0.5
LOGPROB_DROP = -0.8
#: A segment mostly outside the Latin script is a hallucination on an English seat.
LATIN_SHARE_MIN = 0.6
#: Whisper's own sign of a decoding loop; with the temperature fixed at 0 there is no fallback to escape it.
COMPRESSION_DROP = 2.4
#: A word or short phrase said this many times in a row is a loop ("Bumble, Bumble, ..."): kept once.
REPEAT_RUN = 4


def cut_repeats(text: str) -> str:
    """Collapse a run of the same word or phrase (up to three words) repeated REPEAT_RUN or more times
    in a row to a single copy."""
    words = text.split()
    norm = [w.strip(".,!?;:").lower() for w in words]
    out, i = [], 0
    while i < len(words):
        for n in (1, 2, 3):
            unit = norm[i:i + n]
            if len(unit) < n or not any(unit):
                continue
            count = 1
            while norm[i + count * n:i + (count + 1) * n] == unit:
                count += 1
            if count >= REPEAT_RUN:
                out.extend(words[i:i + n])
                i += count * n
                break
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def segment_is_speech(seg: dict) -> bool:
    """False for a segment that is Whisper's invention: likely silence decoded with low confidence, or
    text mostly outside the Latin script."""
    if seg.get("no_speech_prob", 0.0) > NO_SPEECH_DROP and seg.get("avg_logprob", 0.0) < LOGPROB_DROP:
        return False
    if seg.get("compression_ratio", 0.0) > COMPRESSION_DROP and len(set(cut_repeats(seg.get("text", "")).split())) < 4:
        return False  #nothing but a loop
    letters = [c for c in seg.get("text", "") if c.isalpha()]
    if letters and sum(1 for c in letters if ord(c) < 0x250) / len(letters) < LATIN_SHARE_MIN:
        return False
    return True


def transcribe_mlx(wav_path: str, model: str = "mlx-community/whisper-large-v3-turbo",
                   language: str = "en", initial_prompt: Optional[str] = None, light: bool = False) -> TranscriptResult:
    """Transcribe using mlx-whisper (Apple Silicon native)."""
    import mlx_whisper

    #the Linux engine cuts silence before decoding (FULL_DECODE); mlx has no VAD, so it gets the bounded
    #decode, Whisper's own skip of words found in long silences, and the segment filter below: without them
    #it writes words, often in other scripts, into the quiet at an utterance's edges
    kwargs = {
        "path_or_hf_repo": model,
        "language": language,
        "word_timestamps": True,
        "hallucination_silence_threshold": MLX_SILENCE_S,
        **BOUNDED_DECODE,
    }
    if light:  #a short check (the wake phrase) needs the words only: word timing roughly doubles its time
        kwargs["word_timestamps"] = False
        del kwargs["hallucination_silence_threshold"]
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt

    t0 = time.time()
    result = mlx_whisper.transcribe(wav_path, **kwargs)
    elapsed = time.time() - t0

    segments = []
    for seg in result.get("segments", []):
        if not segment_is_speech(seg):
            continue
        segments.append(TranscriptSegment(
            text=cut_repeats(seg.get("text", "").strip()),
            start=seg.get("start", 0.0),
            end=seg.get("end", 0.0),
            confidence=1.0 - seg.get("no_speech_prob", 0.0),
        ))

    return TranscriptResult(
        text=" ".join(s.text for s in segments if s.text).strip(),
        segments=segments,
        language=result.get("language", language),
        engine="mlx-whisper",
        model=model.split("/")[-1] if "/" in model else model,
        duration_audio=segments[-1].end if segments else 0.0,
        duration_transcribe=elapsed,
    )


def transcribe_faster_whisper(wav_path: str, model: str = "large-v3-turbo",
                              language: str = "en", initial_prompt: Optional[str] = None) -> TranscriptResult:
    """Transcribe using faster-whisper (Linux and containers; the GPU when CUDA loads, else the CPU)."""
    from faster_whisper import WhisperModel

    try:
        whisper_model = WhisperModel(model, device="cuda", compute_type="float16")
    except (RuntimeError, ValueError) as e:
        print(f"⚠️ MACF: faster-whisper can't use the GPU ({e}); transcribing on the CPU", file=sys.stderr)
        whisper_model = WhisperModel(model, device="cpu", compute_type="int8")

    kwargs = {"language": language}
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt

    t0 = time.time()
    seg_iter, info = whisper_model.transcribe(wav_path, **kwargs)
    segments = [TranscriptSegment(text=s.text.strip(), start=s.start, end=s.end,
                                  confidence=1.0 - getattr(s, "no_speech_prob", 0.0))
                for s in seg_iter]          # the iterator decodes lazily, so time it whole
    elapsed = time.time() - t0

    return TranscriptResult(
        text=" ".join(s.text for s in segments).strip(),
        segments=segments,
        language=getattr(info, "language", None) or language,
        engine="faster-whisper",
        model=model,
        duration_audio=segments[-1].end if segments else 0.0,
        duration_transcribe=elapsed,
    )


def transcribe_whisper(wav_path: str, model: str = "turbo",
                       language: str = "en", initial_prompt: Optional[str] = None) -> TranscriptResult:
    """Transcribe using OpenAI Whisper (universal fallback)."""
    import whisper

    whisper_model = whisper.load_model(model)

    kwargs = {"language": language}
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt

    t0 = time.time()
    result = whisper_model.transcribe(wav_path, **kwargs)
    elapsed = time.time() - t0

    segments = []
    for seg in result.get("segments", []):
        segments.append(TranscriptSegment(
            text=seg.get("text", "").strip(),
            start=seg.get("start", 0.0),
            end=seg.get("end", 0.0),
            confidence=1.0 - seg.get("no_speech_prob", 0.0),
        ))

    return TranscriptResult(
        text=result.get("text", "").strip(),
        segments=segments,
        language=result.get("language", language),
        engine="openai-whisper",
        model=model,
        duration_audio=segments[-1].end if segments else 0.0,
        duration_transcribe=elapsed,
    )


#: Models loaded once per process, by (engine, model): a capture unit transcribes many times, and
#: loading a model costs seconds each time.
_LOADED: dict = {}


def release_models() -> int:
    """Drop every loaded transcription model, so the memory it held (the GPU's, where it ran there) is given
    back; the next transcription loads it again. Returns how many were dropped. A transcription still running
    keeps its own reference and finishes first (MIS-0008 R58)."""
    import gc
    dropped = len(_LOADED)
    _LOADED.clear()
    gc.collect()
    return dropped

#: The model each engine uses when none is named.
DEFAULT_MODELS = {"mlx": "mlx-community/whisper-large-v3-turbo", "faster-whisper": "large-v3-turbo",
                  "whisper": "turbo"}


def _faster_whisper_model(model: str):
    key = ("faster-whisper", model)
    if key not in _LOADED:
        from faster_whisper import WhisperModel
        _LOADED[key] = WhisperModel(model, device="auto", compute_type="default")
    return _LOADED[key]


def _segments_result(segments, text: str, language: str, engine: str, model: str, elapsed: float) -> TranscriptResult:
    return TranscriptResult(text=text.strip(), segments=segments, language=language, engine=engine, model=model,
                            duration_audio=segments[-1].end if segments else 0.0, duration_transcribe=elapsed)


#: Decoding that can't run away. Whisper's defaults retry at rising temperatures and condition each window on
#: the last, and on a short clip primed with a prompt that can loop: a live trial's "yo tom" came back as the
#: phrase repeated to the token limit, after 38 s on the CPU. Greedy, unconditioned decoding took at most 1.2 s
#: on the same clips.
BOUNDED_DECODE = {"temperature": 0.0, "condition_on_previous_text": False}

#: A full transcription has silence cut out before Whisper sees it. A capture unit's last stretch is often only
#: the quiet before its end window, and Whisper primed with a vocabulary writes speech into silence: a live
#: utterance ended in "So, let's get started." a dozen times (2026-11-14). On the kept clips, 5 s of that quiet
#: came back as "So, let's take a look at the top of the screen."; with this filter every silent tail came back
#: empty, and the speech in all 13 clips was kept, at the same speed. Short checks are left without it: the
#: speech gate has already judged their window, and a filter could clip a phrase that short.
FULL_DECODE = {"vad_filter": True}


def transcribe_faster_whisper(audio, model: str = "large-v3-turbo", language: str = "en",
                              initial_prompt: Optional[str] = None, max_tokens: Optional[int] = None) -> TranscriptResult:
    """Transcribe with faster-whisper, the Linux engine. ``audio`` is a WAV path, or float32
    samples at 16 kHz held in memory, which is how a capture unit calls it (MIS-0008 R13). ``max_tokens``
    caps a short check (a wake phrase, a stop word), so a loop costs a moment rather than the token limit."""
    whisper_model = _faster_whisper_model(model)
    t0 = time.time()
    capped = {"without_timestamps": True, "max_new_tokens": max_tokens} if max_tokens else FULL_DECODE
    found, info = whisper_model.transcribe(audio, language=language, initial_prompt=initial_prompt,
                                           **BOUNDED_DECODE, **capped)
    segments = [TranscriptSegment(text=s.text.strip(), start=s.start, end=s.end, confidence=1.0 - s.no_speech_prob)
                for s in found]       # the generator does the work, so the time is taken after it
    return _segments_result(segments, " ".join(s.text for s in segments), info.language or language,
                            "faster-whisper", model, time.time() - t0)


def transcribe_array(audio, engine: Optional[str] = None, model: Optional[str] = None, language: str = "en",
                     initial_prompt: Optional[str] = None, max_tokens: Optional[int] = None) -> TranscriptResult:
    """Transcribe samples held in memory: float32 or int16, mono, 16 kHz. Nothing is written to
    disk, so raw audio stays in the caller's memory (MIS-0008 R13). Every engine takes an array.
    ``max_tokens`` caps a short check; only faster-whisper honors it so far, and the others say so."""
    import numpy as np
    samples = np.asarray(audio)
    if samples.dtype == np.int16:
        samples = samples.astype(np.float32) / 32768.0
    samples = samples.astype(np.float32, copy=False)
    engine = engine or detect_engine()
    if engine is None:
        raise RuntimeError("No transcription engine available. Install one of: "
                           "mlx-whisper (Mac), faster-whisper (Linux), openai-whisper (universal)")
    model = model or DEFAULT_MODELS.get(engine, "")
    if engine == "faster-whisper":
        return transcribe_faster_whisper(samples, model=model, language=language, initial_prompt=initial_prompt,
                                         max_tokens=max_tokens)
    if engine == "mlx":  #no token cap in mlx; a short check runs light instead
        return transcribe_mlx(samples, model=model, language=language, initial_prompt=initial_prompt,
                              light=bool(max_tokens))
    if max_tokens:
        import warnings
        warnings.warn(f"{engine} doesn't cap tokens yet: a short check can run as long as a full transcription",
                      RuntimeWarning, stacklevel=2)
    if engine == "whisper":
        return transcribe_whisper(samples, model=model, language=language, initial_prompt=initial_prompt)
    raise ValueError(f"Unknown engine: {engine}")


def transcribe(audio_path: str, engine: Optional[str] = None,
               model: Optional[str] = None, language: str = "en",
               initial_prompt: Optional[str] = None) -> TranscriptResult:
    """Transcribe audio file with platform-selective engine.

    Args:
        audio_path: Path to audio file (any format ffmpeg supports)
        engine: Force specific engine ('mlx', 'faster-whisper', 'whisper')
        model: Model name/path (engine-specific defaults if None)
        language: Language code (default: 'en')
        initial_prompt: Whisper initial_prompt for vocabulary conditioning

    Returns:
        TranscriptResult with text, segments, and metadata
    """
    audio_p = Path(audio_path)
    if not audio_p.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Convert to WAV if not already
    if audio_p.suffix.lower() not in ('.wav',):
        wav_path = convert_to_wav(str(audio_p))
        cleanup_wav = True
    else:
        wav_path = str(audio_p)
        cleanup_wav = False

    try:
        # Select engine
        if engine is None:
            engine = detect_engine()
        if engine is None:
            raise RuntimeError(
                "No transcription engine available. Install one of: "
                "mlx-whisper (Mac), faster-whisper (Linux), openai-whisper (universal)"
            )

        # Dispatch to engine
        if engine == "mlx":
            result = transcribe_mlx(
                wav_path,
                model=model or "mlx-community/whisper-large-v3-turbo",
                language=language,
                initial_prompt=initial_prompt,
            )
        elif engine == "faster-whisper":
            # detect_engine's choice on Linux; it had no branch here, so every Linux run failed (#1013)
            result = transcribe_faster_whisper(
                wav_path,
                model=model or "large-v3-turbo",
                language=language,
                initial_prompt=initial_prompt,
            )
        elif engine == "whisper":
            result = transcribe_whisper(
                wav_path,
                model=model or "turbo",
                language=language,
                initial_prompt=initial_prompt,
            )
        elif engine == "faster-whisper":
            # detect_engine has offered this engine on Linux all along; the dispatch had no
            # branch for it, so every Linux transcription raised "Unknown engine".
            result = transcribe_faster_whisper(
                wav_path,
                model=model or DEFAULT_MODELS["faster-whisper"],
                language=language,
                initial_prompt=initial_prompt,
            )
        else:
            raise ValueError(f"Unknown engine: {engine}")

        return result

    finally:
        if cleanup_wav and Path(wav_path).exists():
            Path(wav_path).unlink()
