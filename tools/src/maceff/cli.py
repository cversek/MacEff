import argparse

try:
    from . import __version__ as _ver
except Exception:
    _ver = "0.0.0"

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="maceff_tools", description="maceff demo CLI (no external deps)")
    p.add_argument("--version", action="version", version=f"%(prog)s {_ver}")
    sub = p.add_subparsers(dest="cmd")

    ph = sub.add_parser("hello", help="say hello")
    ph.add_argument("name", nargs="?", default="world", help="name to greet")

    return p

def main(argv=None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "hello":
        print(f"Hello, {args.name}!")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
