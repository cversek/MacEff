# tools/src/maceff/cli.py
import argparse, json, os, sys
from pathlib import Path
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

try:
    from . import __version__ as _ver
except Exception:
    _ver = "0.0.0"

# -------- helpers --------
def _pick_tz():
    """Prefer MACEFF_TZ, then TZ, else system local; fall back to UTC."""
    for key in ("MACEFF_TZ", "TZ"):
        name = os.getenv(key)
        if name and ZoneInfo is not None:
            try:
                return ZoneInfo(name)
            except Exception:
                pass
    try:
        return datetime.now().astimezone().tzinfo or timezone.utc
    except Exception:
        return timezone.utc

def _now_iso(tz=None):
    tz = tz or _pick_tz()
    return datetime.now(tz).replace(microsecond=0).isoformat()

# -------- commands --------
def cmd_env(_: argparse.Namespace) -> int:
    warn = float(os.getenv("MACEFF_TOKEN_WARN", "0.85"))
    hard = float(os.getenv("MACEFF_TOKEN_HARD", "0.95"))
    mode = os.getenv("MACEFF_BUDGET_MODE", "concise/default")
    vcs = "git" if (Path.cwd() / ".git").exists() else "none"
    tz = _pick_tz()
    tz_label = getattr(tz, "key", None) or str(tz)

    data = {
        "time_local": _now_iso(tz),
        "time_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "tz": tz_label,
        "time_source": "env",  # future: "gateway"
        "budget": {
            "adapter": "absent",
            "mode": mode,
            "thresholds": {"warn": warn, "hard": hard},
        },
        "persistence": {"adapter": "absent", "plan": "emit checkpoints inline"},
        "cwd": str(Path.cwd()),
        "vcs": vcs,
    }
    print(json.dumps(data, indent=2))
    return 0

def cmd_time(_: argparse.Namespace) -> int:
    print(_now_iso())  # local (per MACEFF_TZ/TZ)
    return 0

def cmd_budget(_: argparse.Namespace) -> int:
    warn = float(os.getenv("MACEFF_TOKEN_WARN", "0.85"))
    hard = float(os.getenv("MACEFF_TOKEN_HARD", "0.95"))
    mode = os.getenv("MACEFF_BUDGET_MODE", "concise/default")
    payload = {"mode": mode, "thresholds": {"warn": warn, "hard": hard}}
    used = os.getenv("MACEFF_TOKEN_USED")
    if used is not None:
        try:
            payload["used"] = float(used)
        except ValueError:
            pass
    print(json.dumps(payload, indent=2))
    return 0

def cmd_checkpoint(args: argparse.Namespace) -> int:
    note = args.note or ""
    ts = _now_iso()
    log_path = Path.home() / "agent" / "public" / "logs" / "checkpoints.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "note": note}) + "\n")
    print(str(log_path))
    return 0

# -------- parser --------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="maceff_tools", description="maceff demo CLI (no external deps)"
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {_ver}")
    sub = p.add_subparsers(dest="cmd")  # keep non-required for compatibility
    sub.add_parser("env", help="print env summary (JSON)").set_defaults(func=cmd_env)
    sub.add_parser("time", help="print current local time").set_defaults(func=cmd_time)
    sub.add_parser("budget", help="print budget thresholds (JSON)").set_defaults(func=cmd_budget)
    cp = sub.add_parser("checkpoint", help="append a checkpoint note")
    cp.add_argument("--note", default="", help="freeform note to include")
    cp.set_defaults(func=cmd_checkpoint)

    return p

def main(argv=None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "cmd", None):
        exit(args.func(args))
    parser.print_help()

if __name__ == "__main__":
    main()
