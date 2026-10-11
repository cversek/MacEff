#!/usr/bin/env python3
"""A proposal for the tray's mark: a stack of three containers (the agents) on a dock (the host).

Same conventions as tools/make_tray_glyphs.py, so the proposals compare like for like: a
36-unit canvas rendered at 18 px and 36 px (@2x), black and alpha only (template images),
every knock-out an SVG mask, the same stroke weight, the same speech bubble and slash.

    python3 make_stack_glyphs.py OUTDIR
"""
import pathlib
import sys

SW = 2.4                       # stroke weight, as the ring's
DOCK_Y = 31.0
BOX_X, BOX_W, BOX_H, RX = 8.0, 20.0, 6.0, 1.2
LEVELS = (22.5, 15.0, 7.5)     # bottom, middle, top: 1.5 between containers
BUBBLE = ("M 21 22 h 13 a 2 2 0 0 1 2 2 v 7 a 2 2 0 0 1 -2 2 h -8 l -3.5 3 v -3 h -1.5 "
          "a 2 2 0 0 1 -2 -2 v -7 a 2 2 0 0 1 2 -2 z")


def _doc(defs, body):
    head = '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36">\n'
    return head + (f"  <defs>\n{defs}\n  </defs>\n" if defs else "") + body + "\n</svg>\n"


def _mask(mid, cuts):
    return (f'    <mask id="{mid}" maskUnits="userSpaceOnUse" x="0" y="0" width="36" height="36">'
            f'<rect width="36" height="36" fill="#fff"/>{cuts}</mask>')


def _dock(extra="", cap="round"):
    return (f'<line x1="4" y1="{DOCK_Y}" x2="32" y2="{DOCK_Y}" stroke="#000" stroke-width="{SW}" '
            f'stroke-linecap="{cap}"{extra}/>')


def _box(y, x=BOX_X, hollow=False):
    if hollow:
        return (f'<rect x="{x + 0.9}" y="{y + 0.9}" width="{BOX_W - 1.8}" height="{BOX_H - 1.8}" rx="{RX}" '
                f'fill="none" stroke="#000" stroke-width="1.8"/>')
    return f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" rx="{RX}" fill="#000"/>'


def _stack(hollow=False):
    return "".join(_box(y, hollow=hollow) for y in LEVELS)


def glyphs():
    halo = f'<path d="{BUBBLE}" fill="#000" stroke="#000" stroke-width="3.2" stroke-linejoin="round"/>'
    bubble_dots = "".join(f'<circle cx="{x}" cy="27.5" r="1.15" fill="#000"/>' for x in (24.5, 27.5, 30.5))
    slash_cut = '<line x1="5" y1="31" x2="31" y2="5" stroke="#000" stroke-width="6.4" stroke-linecap="round"/>'
    slash = '<line x1="5" y1="31" x2="31" y2="5" stroke="#000" stroke-width="2.6" stroke-linecap="round"/>'
    # starting: the top container hoisted up and swung right, on its way to its place
    hoisted = (_box(LEVELS[0]) + _box(LEVELS[1]) + _box(3.5, x=BOX_X + 5.0)
               + f'<line x1="{BOX_X + 15.0}" y1="0.5" x2="{BOX_X + 15.0}" y2="3.5" stroke="#000" stroke-width="1.6"/>')
    return {
        # the plain mark: three agents on their host
        "running": _doc("", "  " + _stack() + _dock()),
        # hollow containers: the agents are there, nothing runs in them
        "stopped": _doc("", "  " + _stack(hollow=True) + _dock()),
        # the top container still swinging into place
        "starting": _doc("", "  " + hoisted + _dock()),
        # a broken dock, two stubs with a gap: the host's daemon did not answer
        "unreachable": _doc("", "  " + _stack() + _dock(' stroke-dasharray="10 8 10"', cap="butt")),
        # a speech bubble knocked out of the mark: someone is being asked
        "waiting_on_a_person": _doc(_mask("m", halo) + "\n" + _mask("b", bubble_dots),
                                    f'  <g mask="url(#m)">{_stack()}{_dock()}</g>'
                                    f'<path d="{BUBBLE}" fill="#000" mask="url(#b)"/>'),
        # a slash through the whole mark
        "failed": _doc(_mask("m", slash_cut), f'  <g mask="url(#m)">{_stack()}{_dock()}</g>{slash}'),
    }


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, svg in glyphs().items():
        (out / f"{name}.svg").write_text(svg)
    print("wrote", len(glyphs()), "SVGs to", out)
