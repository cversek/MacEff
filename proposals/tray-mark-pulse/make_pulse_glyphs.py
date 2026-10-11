#!/usr/bin/env python3
"""Draw the 'pulse' tray mark's six state glyphs: SVG sources, PNGs at 18 and 36 px.

The mark is a ring with a heartbeat across it: the layer's whole job is knowing what is
alive. Each state changes the silhouette, never only a colour: black and alpha only, so
macOS tints them as template images. Knock-outs are masks, since a white fill would tint
like black.
"""
import pathlib, subprocess, sys

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
SW = 2.6
RING = 'cx="18" cy="18" r="14"'
PULSE = "M 6.5 19 H 11.5 L 14.5 10.5 L 18.5 26 L 21.5 15 L 23.5 19 H 29.5"
FLAT = "M 8 18 H 28"
LINE = f'fill="none" stroke="#000" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round"'


def doc(body, defs=""):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36">\n'
            + (f"  <defs>{defs}</defs>\n" if defs else "") + body + "\n</svg>\n")


GLYPHS = {
    # The plain mark: a ring and a beat.
    "running": doc(f'  <circle {RING} {LINE}/>\n  <path d="{PULSE}" {LINE}/>'),
    # Coming up: the beat is there, the ring not yet closed.
    "starting": doc(f'  <path d="M 32 18 A 14 14 0 1 1 18 4" {LINE}/>\n  <path d="{PULSE}" {LINE}/>'),
    # Down by choice: the line goes flat inside a whole ring.
    "stopped": doc(f'  <circle {RING} {LINE}/>\n  <path d="{FLAT}" {LINE}/>'),
    # Unreachable: the ring breaks up and there is nothing to read inside it.
    "unreachable": doc(f'  <circle {RING} {LINE} stroke-dasharray="6.2 5"/>'),
    # Waiting on a person: paused, holding for you.
    "waiting_on_a_person": doc(f'  <circle {RING} {LINE}/>\n'
                               f'  <path d="M 14.5 12 V 24 M 21.5 12 V 24" fill="none" stroke="#000" stroke-width="3.4" stroke-linecap="round"/>'),
    # Failed: the heaviest shape, a solid disc with the beat cut out of it.
    "failed": doc('  <circle cx="18" cy="18" r="15.3" fill="#000" mask="url(#cut)"/>',
                  defs=f'<mask id="cut"><rect width="36" height="36" fill="#fff"/>'
                       f'<path d="{PULSE}" fill="none" stroke="#000" stroke-width="{SW}" '
                       f'stroke-linecap="round" stroke-linejoin="round"/></mask>'),
}

OUT.mkdir(parents=True, exist_ok=True)
for name, svg in GLYPHS.items():
    src = OUT / f"{name}.svg"
    src.write_text(svg)
    for px, suffix in ((18, ""), (36, "@2x")):
        subprocess.run(["rsvg-convert", "-w", str(px), "-h", str(px), "-o", str(OUT / f"{name}{suffix}.png"), str(src)], check=True)
print("drew", ", ".join(GLYPHS))
