"""Render each SVG in a folder to PNGs at 18 and 36 px, and build a preview sheet: every glyph
at 1x and 2x on a light and a dark menu bar, template-style (black tinted to the bar's ink).
Run inside a throwaway container with cairosvg on the path:  python3 render.py DIR"""
import io
import sys
from pathlib import Path

import cairosvg
from PIL import Image

ORDER = ["running", "stopped", "starting", "unreachable", "waiting_on_a_person", "failed"]
d = Path(sys.argv[1])
pngs = {}
for name in ORDER:
    svg = (d / f"{name}.svg").read_bytes()
    for px, suffix in ((18, ""), (36, "@2x")):
        data = cairosvg.svg2png(bytestring=svg, output_width=px, output_height=px)
        (d / f"{name}{suffix}.png").write_bytes(data)
        pngs[(name, px)] = Image.open(io.BytesIO(data)).convert("RGBA")

# sheet: rows = light bar 1x, light bar 2x, dark bar 1x, dark bar 2x; columns = states
cell, pad = 44, 6
sheet = Image.new("RGBA", (pad + len(ORDER) * cell, pad + 4 * cell), (128, 128, 128, 255))
for row, (bg, ink, px) in enumerate([((236, 236, 236), (0, 0, 0), 18), ((236, 236, 236), (0, 0, 0), 36),
                                     ((40, 40, 40), (255, 255, 255), 18), ((40, 40, 40), (255, 255, 255), 36)]):
    for col, name in enumerate(ORDER):
        x, y = pad + col * cell, pad + row * cell
        tile = Image.new("RGBA", (cell - pad, cell - pad), bg + (255,))
        g = pngs[(name, px)]
        tinted = Image.new("RGBA", g.size, ink + (0,))
        tinted.putalpha(g.getchannel("A"))
        tile.alpha_composite(tinted, ((cell - pad - px) // 2, (cell - pad - px) // 2))
        sheet.alpha_composite(tile, (x, y))
sheet = sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST)
sheet.save(d / "preview_sheet.png")
print("rendered", len(pngs), "PNGs and preview_sheet.png")
