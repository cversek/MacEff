"""The menu-bar app: one icon over every installed agent, drawn with rumps (macOS).

Optional: ``pip install 'macf[tray]'``, then ``python -m macf.tray``. Everything it shows
comes from ``Controller.poll``; everything it does goes through ``Controller.act``.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .controller import Controller
from .model import ACTS

GLYPHS = Path(__file__).resolve().parent / "glyphs"
POLL_S = 5


def glyph(state) -> str:
    """The template image for the icon's state; an empty host shows as stopped."""
    return str(GLYPHS / f"{state or 'stopped'}@2x.png")


def main() -> int:
    try:
        import rumps
    except ImportError:
        print("The tray needs rumps: pip install 'macf[tray]' (macOS only).", file=sys.stderr)
        return 1

    controller = Controller()

    class TrayApp(rumps.App):
        def __init__(self):
            super().__init__("MacEff", icon=glyph("stopped"), template=True, quit_button=None)
            self.refresh(None)

        def _act(self, card, act, unit):
            def callback(_):
                answer = controller.act(card, act, unit)
                if not answer.get("ok"):
                    rumps.alert(f"{card}: {act} {unit} was refused", answer.get("error") or "")
                self.refresh(None)
            return callback

        @rumps.timer(POLL_S)
        def refresh(self, _):
            state = controller.poll()
            self.icon = glyph(state.icon)
            self.menu.clear()
            if state.alerting:
                self.menu.add(rumps.MenuItem(f"{state.icon.replace('_', ' ')}: {', '.join(state.caused_by)}"))
                self.menu.add(rumps.separator)
            for e in state.entries:
                item = rumps.MenuItem(e.label if not e.error else f"{e.label} ({e.error})")
                for unit in sorted(e.units):
                    sub = rumps.MenuItem(f"{unit}: {e.units[unit].replace('_', ' ')}")
                    for act in ACTS:
                        sub.add(rumps.MenuItem(act.capitalize(), callback=self._act(e.card, act, unit)))
                    item.add(sub)
                self.menu.add(item)
            for err in controller.errors:
                self.menu.add(rumps.MenuItem(err))
            if not state.entries and not controller.errors:
                self.menu.add(rumps.MenuItem("No MacEff agents are installed on this host"))
            self.menu.add(rumps.separator)
            self.menu.add(rumps.MenuItem("Quit", callback=rumps.quit_application))

    TrayApp().run()
    return 0
