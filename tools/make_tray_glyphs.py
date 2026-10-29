#!/usr/bin/env python3
"""Make the tray's state glyphs: SVGs, then PNGs at 18 px and 36 px (@2x).

The mark is the flame spirit, the operator's choice for the tray (#584): one glyph
per state, prompted by the operator, traced to SVG with potrace, and set on one
baseline at one scale. The traced sources live in tools/tray_mark/flame_spirit/.
Each state changes the shape, never only a color, because the glyphs are macOS
template images: black and alpha only, tinted by the system for light and dark
menu bars.

    python3 tools/make_tray_glyphs.py            # writes into macf/src/macf/tray/glyphs/
    python3 tools/make_tray_glyphs.py --check    # exits 1 if the glyphs differ from the sources

The PNGs need rsvg-convert (librsvg).
"""
import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "tools" / "tray_mark" / "flame_spirit"
OUT = ROOT / "macf" / "src" / "macf" / "tray" / "glyphs"
STATES = ("running", "starting", "waiting_on_a_person", "failed", "unreachable", "stopped")


def glyphs():
    """Each state's SVG text, by state name: the traced source, in black written as #000."""
    return {s: (SOURCES / f"{s}.svg").read_text().replace('"#000000"', '"#000"') for s in STATES}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare, write nothing")
    args = parser.parse_args(argv)
    drawn = glyphs()
    if args.check:
        stale = [s for s, svg in drawn.items()
                 if not (OUT / f"{s}.svg").exists() or (OUT / f"{s}.svg").read_text() != svg]
        for s in stale:
            print(f"{s}.svg differs from its source; run tools/make_tray_glyphs.py", file=sys.stderr)
        return 1 if stale else 0
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        print("rsvg-convert isn't on PATH (brew install librsvg)", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for s, svg in drawn.items():
        src = OUT / f"{s}.svg"
        src.write_text(svg)
        for name, side in ((f"{s}.png", 18), (f"{s}@2x.png", 36)):
            subprocess.run([rsvg, "-w", str(side), "-h", str(side), "-o", str(OUT / name), str(src)], check=True)
    print(f"wrote {len(drawn)} glyphs to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
