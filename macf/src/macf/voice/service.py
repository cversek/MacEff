"""
VoiceService — Persistent TCP daemon keeping Whisper model warm.

Modeled on SearchService architecture: TCP socket server that loads
heavy dependencies once at startup, then accepts requests over JSON
protocol. Model stays in GPU memory for ~150ms transcription vs
~1.9s cold load.

Protocol (newline-delimited JSON):
    Request:  {"action": "transcribe", "file": "/path/to/audio.oga", "language": "en", "conditioned": true, "correct": true}
    Response: {"text": "...", "segments": [...], "engine": "mlx-whisper", "duration_ms": 150, "corrections": [...]}

    Request:  {"action": "status"}
    Response: {"status": "ready", "engine": "mlx-whisper", "model": "...", "uptime_s": 3600}

    Request:  {"action": "shutdown"}
    Response: {"status": "shutting_down"}

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
        data = b''
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if b'\n' in data:
                break
        return json.loads(data.decode('utf-8').strip())
    finally:
        sock.close()


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
        return {"status": "shutting_down"}

    elif action == "transcribe":
        file_path = request.get("file")
        if not file_path or not Path(file_path).exists():
            return {"error": f"File not found: {file_path}"}

        language = request.get("language", "en")
        conditioned = request.get("conditioned", True)
        correct = request.get("correct", True)

        # Build prompt
        prompt = None
        if conditioned:
            try:
                from .vocabulary import build_whisper_prompt
                prompt = build_whisper_prompt()
            except Exception:
                pass

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
                except Exception as e:
                    response["correction_error"] = str(e)

            return response

        except Exception as e:
            return {"error": str(e)}

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
        except socket.timeout:
            continue
        except OSError:
            break

        try:
            data = b''
            conn.settimeout(30.0)
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b'\n' in data:
                    break

            if data:
                request = json.loads(data.decode('utf-8').strip())
                response = handle_request(request)
                conn.sendall(json.dumps(response).encode('utf-8') + b'\n')

                if request.get("action") == "shutdown":
                    conn.close()
                    break
        except Exception as e:
            try:
                conn.sendall(json.dumps({"error": str(e)}).encode('utf-8') + b'\n')
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

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

    # Try graceful shutdown via TCP first
    try:
        send_request({"action": "shutdown"}, timeout=5.0)
        print(f"Voice service stopped (PID {pid})")
        time.sleep(0.5)
        get_pid_file_path().unlink(missing_ok=True)
        return 0
    except (ConnectionError, OSError):
        pass

    # Fallback: SIGTERM
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Voice service stopped via SIGTERM (PID {pid})")
        get_pid_file_path().unlink(missing_ok=True)
        return 0
    except (ProcessLookupError, PermissionError) as e:
        print(f"Failed to stop voice service: {e}")
        return 1
