#!/usr/bin/env python3
"""Draw the tray's state glyphs: SVG sources, then PNGs at 18 px and 36 px (@2x).

The mark is a ring (the host) carrying three dots (its agents). Each state changes
the shape, never only a color, because the glyphs are macOS template images: black
and alpha only, tinted by the system for light and dark menu bars. A white fill would
tint like black, so every knock-out is an SVG mask.

    python3 tools/make_tray_glyphs.py            # writes into macf/src/macf/tray/glyphs/
    python3 tools/make_tray_glyphs.py --check    # exits 1 if the sources differ from this drawing

The PNGs need rsvg-convert (librsvg).
"""
import argparse
import math
import pathlib
import shutil
import subprocess
import sys

OUT = pathlib.Path(__file__).resolve().parent.parent / "macf" / "src" / "macf" / "tray" / "glyphs"

CX = CY = 18.0
R = 12.0
DOT = 3.6
SW = 2.4
AGENTS = [(CX + R * math.cos(math.radians(a)), CY - R * math.sin(math.radians(a))) for a in (90, 210, 330)]
BUBBLE = ("M 21 22 h 13 a 2 2 0 0 1 2 2 v 7 a 2 2 0 0 1 -2 2 h -8 l -3.5 3 v -3 h -1.5 "
          "a 2 2 0 0 1 -2 -2 v -7 a 2 2 0 0 1 2 -2 z")


def _doc(defs, body):
    head = '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36">\n'
    return head + (f"  <defs>\n{defs}\n  </defs>\n" if defs else "") + body + "\n</svg>\n"


def _ring(extra=""):
    return f'<circle cx="{CX}" cy="{CY}" r="{R}" fill="none" stroke="#000" stroke-width="{SW}"{extra}/>'


def _dots():
    return "".join(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{DOT}" fill="#000"/>' for x, y in AGENTS)


def _mask(mid, cuts):
    """White keeps, black cuts: the drawing shows everywhere except under ``cuts``."""
    return (f'    <mask id="{mid}" maskUnits="userSpaceOnUse" x="0" y="0" width="36" height="36">'
            f'<rect width="36" height="36" fill="#fff"/>{cuts}</mask>')


def glyphs():
    """Each state's SVG text, by state name."""
    circ = 2 * math.pi * R
    cut_dots = "".join(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{DOT}" fill="#000"/>' for x, y in AGENTS)
    hollow = "".join(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{DOT - 0.9}" fill="none" stroke="#000" '
                     f'stroke-width="1.8"/>' for x, y in AGENTS)
    halo = f'<path d="{BUBBLE}" fill="#000" stroke="#000" stroke-width="3.2" stroke-linejoin="round"/>'
    bubble_dots = "".join(f'<circle cx="{x}" cy="27.5" r="1.15" fill="#000"/>' for x in (24.5, 27.5, 30.5))
    slash_cut = '<line x1="5" y1="31" x2="31" y2="5" stroke="#000" stroke-width="6.4" stroke-linecap="round"/>'
    slash = '<line x1="5" y1="31" x2="31" y2="5" stroke="#000" stroke-width="2.6" stroke-linecap="round"/>'
    return {
        # the plain mark
        "running": _doc("", "  " + _ring() + _dots()),
        # hollow agents; the ring is cut under each dot so its inside is clear
        "stopped": _doc(_mask("m", cut_dots), f'  <g mask="url(#m)">{_ring()}</g>{hollow}'),
        # three quarters of the ring, open between the top and right agents: coming up
        "starting": _doc("", "  " + _ring(f' stroke-linecap="round" stroke-dasharray="{0.75 * circ:.2f} '
                                          f'{0.25 * circ:.2f}" transform="rotate(30 18 18)"') + _dots()),
        # a broken ring: the daemon did not answer
        "unreachable": _doc("", "  " + _ring(' stroke-dasharray="3.2 3.2"') + _dots()),
        # a speech bubble knocked out of the mark: someone is being asked
        "waiting_on_a_person": _doc(_mask("m", halo) + "\n" + _mask("b", bubble_dots),
                                    f'  <g mask="url(#m)">{_ring()}{_dots()}</g>'
                                    f'<path d="{BUBBLE}" fill="#000" mask="url(#b)"/>'),
        # a slash through the whole mark
        "failed": _doc(_mask("m", slash_cut), f'  <g mask="url(#m)">{_ring()}{_dots()}</g>{slash}'),
    }


def main(argv=None):
    """Write or check the glyph sources, then render the PNGs."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="compare the sources to this drawing; write nothing")
    args = ap.parse_args(argv)
    drawn = glyphs()
    if args.check:
        stale = [n for n, text in drawn.items() if not (OUT / f"{n}.svg").is_file()
                 or (OUT / f"{n}.svg").read_text() != text]
        if stale:
            print(f"glyph sources differ from tools/make_tray_glyphs.py: {', '.join(stale)}", file=sys.stderr)
            return 1
        print(f"{len(drawn)} glyph sources match")
        return 0
    if shutil.which("rsvg-convert") is None:
        print("rsvg-convert not found (brew install librsvg)", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in drawn.items():
        svg = OUT / f"{name}.svg"
        svg.write_text(text)
        for suffix, side in (("", 18), ("@2x", 36)):
            subprocess.run(["rsvg-convert", "-w", str(side), "-h", str(side), str(svg),
                            "-o", str(OUT / f"{name}{suffix}.png")], check=True)
    print(f"wrote {len(drawn)} glyphs to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
