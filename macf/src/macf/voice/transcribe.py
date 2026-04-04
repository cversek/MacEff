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
        except ImportError:
            pass

    # Linux/other: prefer faster-whisper
    try:
        import faster_whisper
        return "faster-whisper"
    except ImportError:
        pass

    # Universal fallback: openai-whisper
    try:
        import whisper
        return "whisper"
    except ImportError:
        pass

    return None


def transcribe_mlx(wav_path: str, model: str = "mlx-community/whisper-large-v3-turbo",
                   language: str = "en", initial_prompt: Optional[str] = None) -> TranscriptResult:
    """Transcribe using mlx-whisper (Apple Silicon native)."""
    import mlx_whisper

    kwargs = {
        "path_or_hf_repo": model,
        "language": language,
        "word_timestamps": True,
    }
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt

    t0 = time.time()
    result = mlx_whisper.transcribe(wav_path, **kwargs)
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
        engine="mlx-whisper",
        model=model.split("/")[-1] if "/" in model else model,
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
        elif engine == "whisper":
            result = transcribe_whisper(
                wav_path,
                model=model or "turbo",
                language=language,
                initial_prompt=initial_prompt,
            )
        else:
            raise ValueError(f"Unknown engine: {engine}")

        return result

    finally:
        if cleanup_wav and Path(wav_path).exists():
            Path(wav_path).unlink()
