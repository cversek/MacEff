"""
VoiceService — Persistent TCP daemon keeping Whisper model warm.

Modeled on SearchService architecture: TCP socket server that loads
heavy dependencies once at startup, then accepts requests over JSON
protocol. Model stays in GPU memory for ~150ms transcription vs
~1.9s cold load.

Protocol (newline-delimited JSON):
    Request:  {"action": "transcribe", "audio": "<base64 of the file>", "suffix": ".oga", "language": "en", "conditioned": true, "correct": true}
    Response: {"text": "...", "segments": [...], "engine": "mlx-whisper", "duration_ms": 150, "corrections": [...]}

    Request:  {"action": "status"}
    Response: {"status": "ready", "engine": "mlx-whisper", "model": "...", "uptime_s": 3600}

    There is no stop verb: the port answers any local caller, so stopping is the service's
    own account's act, by signal (``macf_tools voice service stop``) (#868).

Usage:
    macf_tools voice service start
    macf_tools voice service stop
    macf_tools voice service status
"""

import json
import os
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Optional

DEFAULT_PORT = 9002  # SearchService uses 9001
DEFAULT_HOST = "127.0.0.1"
PID_FILE_NAME = "macf_voice_service.pid"

_start_time = None
_engine = None
_model_name = None


def get_pid_file_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return Path(runtime_dir) / PID_FILE_NAME


def write_pid_file(pid: int) -> None:
    get_pid_file_path().write_text(str(pid))


def read_pid_file() -> Optional[int]:
    pid_file = get_pid_file_path()
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def is_service_running() -> bool:
    pid = read_pid_file()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        get_pid_file_path().unlink(missing_ok=True)
        return False


def get_service_status() -> dict:
    """Get service status for CLI display."""
    if not is_service_running():
        return {"running": False}

    try:
        result = send_request({"action": "status"})
        result["running"] = True
        return result
    except (ConnectionError, OSError):
        return {"running": False, "error": "PID exists but service not responding"}


def send_request(request: dict, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 30.0) -> dict:
    """Send a request to the voice service and get response."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        sock.sendall(json.dumps(request).encode('utf-8') + b'\n')
        data = read_request_line(sock)    # the reply is bounded the same way: a squatted port can send without end
        return json.loads(data.decode('utf-8').strip())
    finally:
        sock.close()


#: The suffixes of audio the service will stage, and the most audio it takes in one request.
AUDIO_SUFFIXES = (".oga", ".ogg", ".opus", ".wav", ".mp3", ".m4a", ".flac", ".webm")
MAX_AUDIO_BYTES = 64 * 1024 * 1024
#: The most one request line may hold: the base64 of the largest audio, and a megabyte of JSON
#: around it. Reading stops here, before anything is parsed, so no caller can make the service
#: hold more than this however long it keeps sending (#868).
MAX_REQUEST_BYTES = (MAX_AUDIO_BYTES + 2) // 3 * 4 + 1024 * 1024


class RequestTooLarge(Exception):
    """A request line ran past MAX_REQUEST_BYTES without ending."""


def read_request_line(conn) -> bytes:
    """One request line from *conn*, read up to its newline, or RequestTooLarge at the bound."""
    data = bytearray()       # appended in place: bytes += would copy the buffer on every chunk
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_REQUEST_BYTES:
            raise RequestTooLarge
        if b'\n' in chunk:
            break
    return bytes(data)


def _transcribe_staged(request: dict) -> dict:
    """Transcribe the audio a request carries, never a file it names.

    The port takes any local process, and a request that named a path made the service read any file its
    account can, for a caller who may not (a confused deputy, #868). The caller reads its own
    file and sends the bytes (``audio``, base64, with the ``suffix`` that says its format); the service
    stages them in a private directory it removes afterwards, and opens nothing the caller named."""
    import base64
    import binascii
    import shutil
    import tempfile
    if "file" in request:
        return {"error": "transcribe takes the audio itself ('audio', base64, and its 'suffix'), not a path"}
    suffix = str(request.get("suffix") or "").lower()
    raw = request.get("audio")
    if suffix not in AUDIO_SUFFIXES or not isinstance(raw, str):
        return {"error": f"transcribe takes 'audio' (base64) and a 'suffix' of one of {', '.join(AUDIO_SUFFIXES)}"}
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return {"error": "the audio isn't valid base64"}
    if not data or len(data) > MAX_AUDIO_BYTES:
        return {"error": f"the audio is empty or over {MAX_AUDIO_BYTES // (1024 * 1024)} MB"}
    staging = tempfile.mkdtemp(prefix="macf-voice-")       # mode 0700: only the service's account reads it
    try:
        staged = Path(staging) / f"audio{suffix}"
        staged.write_bytes(data)
        return _transcribe_file(str(staged), request)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _transcribe_file(file_path: str, request: dict) -> dict:
    """Transcribe the staged file *file_path* with the request's options and return the reply."""
    language = request.get("language", "en")
    conditioned = request.get("conditioned", True)
    correct = request.get("correct", True)

    # Build prompt
    prompt = None
    if conditioned:
        try:
            from .vocabulary import build_whisper_prompt
            prompt = build_whisper_prompt()
        except ImportError as e:
            print(f"⚠️ MACF: vocabulary module unavailable, proceeding without prompt: {e}", file=sys.stderr)

    # Transcribe (model is already warm in memory)
    try:
        from .transcribe import transcribe
        t0 = time.time()
        result = transcribe(
            audio_path=file_path,
            engine=request.get("engine"),
            language=language,
            initial_prompt=prompt,
        )
        elapsed_ms = (time.time() - t0) * 1000

        response = result.to_dict()
        response["duration_ms"] = round(elapsed_ms)

        # Apply fuzzy correction if requested
        if correct:
            try:
                from .correction import correct_transcript
                corrected = correct_transcript(result.text)
                response["corrected_text"] = corrected.corrected_text
                response["corrections"] = [
                    {"original": c.original, "corrected": c.corrected, "confidence": c.confidence}
                    for c in corrected.corrections
                ]
            except Exception as e:  # noqa: BLE001 - any failure becomes the fixed reply below
                # A fixed reply, like the transcription's: the detail goes to the log only.
                print(f"⚠️ MACF: voice: correction failed: {e}", file=sys.stderr)
                response["correction_error"] = "the correction failed"

        return response

    except Exception as e:  # noqa: BLE001 - any failure becomes the one fixed reply below
        # The detail (ffmpeg's command line names the path) goes to the service's own log, which
        # only its account reads; the caller learns only that the file couldn't be transcribed
        # (#868).
        print(f"⚠️ MACF: voice: transcription failed: {e}", file=sys.stderr)
        return {"error": "the audio file can't be read"}


def handle_request(request: dict) -> dict:
    """Handle a single request from a client."""
    global _start_time, _engine, _model_name

    action = request.get("action", "")

    if action == "status":
        uptime = time.time() - _start_time if _start_time else 0
        return {
            "status": "ready",
            "engine": _engine or "unknown",
            "model": _model_name or "unknown",
            "uptime_s": round(uptime),
            "pid": os.getpid(),
        }

    elif action == "shutdown":
        # Any local process can reach the port, so a stop verb here let anyone stop the service.
        # Stopping is a signal from the service's own account (#868).
        return {"error": "shutdown is not a request this service takes; stop it with "
                         "`macf_tools voice service stop`"}

    elif action == "transcribe":
        return _transcribe_staged(request)

    else:
        return {"error": f"Unknown action: {action}"}


def start_service(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                  model: Optional[str] = None, foreground: bool = False) -> int:
    """Start the voice service daemon."""
    global _start_time, _engine, _model_name

    if is_service_running():
        print(f"Voice service already running (PID {read_pid_file()})")
        return 1

    if not foreground:
        # Daemonize
        pid = os.fork()
        if pid > 0:
            # Parent: write PID and exit
            write_pid_file(pid)
            print(f"Voice service started (PID {pid}, port {port})")
            return 0

        # Child: continue as daemon
        os.setsid()
        # Redirect stdout/stderr to log
        log_path = Path("/tmp") / "macf_voice_service.log"
        sys.stdout = open(log_path, "a")
        sys.stderr = sys.stdout

    # Write PID (for foreground mode or child process)
    write_pid_file(os.getpid())

    # Pre-warm: load the Whisper model
    print(f"[{time.strftime('%H:%M:%S')}] Loading Whisper model...", flush=True)
    try:
        from .transcribe import detect_engine
        _engine = detect_engine()
        if _engine == "mlx":
            import mlx_whisper
            _model_name = model or "mlx-community/whisper-large-v3-turbo"
            # Warm load: transcribe 0.1s of silence to load model into GPU
            import tempfile, subprocess
            silence = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono',
                          '-t', '0.1', '-y', '-loglevel', 'error', silence.name],
                         capture_output=True)
            mlx_whisper.transcribe(silence.name, path_or_hf_repo=_model_name)
            Path(silence.name).unlink()
            print(f"[{time.strftime('%H:%M:%S')}] Model loaded: {_model_name} ({_engine})", flush=True)
        elif _engine == "whisper":
            import whisper
            _model_name = model or "turbo"
            whisper.load_model(_model_name)
            print(f"[{time.strftime('%H:%M:%S')}] Model loaded: {_model_name} ({_engine})", flush=True)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] No engine available", flush=True)
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Model load failed: {e}", flush=True)

    _start_time = time.time()

    # Setup signal handlers
    def handle_signal(signum, frame):
        print(f"\n[{time.strftime('%H:%M:%S')}] Shutting down (signal {signum})", flush=True)
        get_pid_file_path().unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Start TCP server
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    server.settimeout(1.0)  # 1s timeout for accept (allows signal handling)

    print(f"[{time.strftime('%H:%M:%S')}] Voice service listening on {host}:{port}", flush=True)

    while True:
        try:
            conn, addr = server.accept()
        except socket.timeout:  # noqa: S112 - idle tick: accept() times out each second so the loop stays responsive
            continue
        except OSError:
            break

        try:
            conn.settimeout(30.0)
            try:
                data = read_request_line(conn)
            except RequestTooLarge:
                print(f"⚠️ MACF: voice: a request ran past {MAX_REQUEST_BYTES} bytes and was refused unread", file=sys.stderr)
                conn.sendall(json.dumps({"error": f"the request is over {MAX_REQUEST_BYTES // (1024 * 1024)} MB"}).encode('utf-8') + b'\n')
                continue
            if data:
                request = json.loads(data.decode('utf-8').strip())
                response = handle_request(request)
                conn.sendall(json.dumps(response).encode('utf-8') + b'\n')
        except Exception as e:
            print(f"⚠️ MACF: voice: a request failed: {e}", file=sys.stderr)
            try:
                conn.sendall(json.dumps({"error": "the request failed"}).encode('utf-8') + b'\n')
            except OSError as send_err:
                print(f"⚠️ MACF: failed to send error response to voice client: {send_err}", file=sys.stderr)
        finally:
            try:
                conn.close()
            except OSError as e:
                print(f"⚠️ MACF: failed to close voice client connection: {e}", file=sys.stderr)

    server.close()
    get_pid_file_path().unlink(missing_ok=True)
    print(f"[{time.strftime('%H:%M:%S')}] Voice service stopped", flush=True)
    return 0


def stop_service() -> int:
    """Stop the voice service daemon."""
    pid = read_pid_file()
    if pid is None:
        print("Voice service not running")
        return 1

    if not is_service_running():
        print("Voice service not running (stale PID file)")
        get_pid_file_path().unlink(missing_ok=True)
        return 1

    # By signal: the service takes no stop request over its port (#868).
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Voice service stopped via SIGTERM (PID {pid})")
        get_pid_file_path().unlink(missing_ok=True)
        return 0
    except (ProcessLookupError, PermissionError) as e:
        print(f"Failed to stop voice service: {e}")
        return 1
