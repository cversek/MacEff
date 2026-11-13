"""The recording indicator's overlay on a Linux Wayland desktop (MIS-0008 R21, R22).

Run by the capture unit under the system's Python, which carries GTK 4 and gtk4-layer-shell; it
imports nothing from macf. It reads one JSON object per line on its stdin and draws:

    {"show": {"agent": "...", "mode": "wake_phrase|hold_key|continual_voice"}}
    {"level": 0.12, "wave": [-0.1, 0.2, ...]}
    {"hide": true}

A strip at the top of the screen shows the agent's name and the mode, the newest waveform, and a
volume trace of the recent levels. It takes no input and sends nothing back. It exits when its
stdin closes, so it never outlives the capture unit.
"""
import json
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gio, GLib, Gtk, Gtk4LayerShell  # noqa: E402

def _unix_input(fd):
    """A GIO stream on ``fd``: GioUnix where this GLib has it, the older Gio name where it doesn't."""
    try:
        gi.require_version("GioUnix", "2.0")
        from gi.repository import GioUnix
        return GioUnix.InputStream.new(fd, False)
    except (ValueError, ImportError):
        return Gio.UnixInputStream.new(fd, False)


MODES = {"wake_phrase": "wake phrase", "hold_key": "hold key", "continual_voice": "continual voice"}
TRACE_POINTS = 90
WIDTH, HEIGHT = 420, 84


class Overlay:
    def __init__(self, app):
        self.agent, self.mode = "", ""
        self.wave, self.levels = [], []
        win = self.win = Gtk.ApplicationWindow(application=app)
        win.set_default_size(WIDTH, HEIGHT)
        win.set_decorated(False)
        Gtk4LayerShell.init_for_window(win)
        Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_margin(win, Gtk4LayerShell.Edge.TOP, 12)
        Gtk4LayerShell.set_keyboard_mode(win, Gtk4LayerShell.KeyboardMode.NONE)
        self.area = Gtk.DrawingArea()
        self.area.set_content_width(WIDTH)
        self.area.set_content_height(HEIGHT)
        self.area.set_draw_func(self.draw)
        win.set_child(self.area)
        stream = Gio.DataInputStream.new(_unix_input(sys.stdin.fileno()))
        self.stream, self.app = stream, app
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self.on_line)

    def on_line(self, stream, result):
        line, _length = stream.read_line_finish_utf8(result)
        if line is None:                      # the capture unit is gone: so is its indicator
            self.app.quit()
            return
        try:
            self.take(json.loads(line))
        except (ValueError, KeyError, TypeError) as e:
            print(f"indicator overlay: skipped a malformed line: {e}", file=sys.stderr)
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self.on_line)

    def take(self, message):
        if "show" in message:
            self.agent, self.mode = message["show"]["agent"], message["show"]["mode"]
            self.wave, self.levels = [], []
            self.win.present()
        elif "hide" in message:
            self.win.set_visible(False)
        elif "level" in message:
            self.levels = (self.levels + [float(message["level"])])[-TRACE_POINTS:]
            self.wave = [float(x) for x in message.get("wave", [])]
        self.area.queue_draw()

    def draw(self, _area, cr, width, height):
        cr.set_source_rgba(0.08, 0.09, 0.11, 0.92)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cr.set_source_rgb(0.95, 0.35, 0.3)       # the recording dot
        cr.arc(16, 18, 6, 0, 6.2832)
        cr.fill()
        cr.set_source_rgb(0.92, 0.92, 0.92)
        cr.select_font_face("Sans")
        cr.set_font_size(13)
        cr.move_to(30, 23)
        cr.show_text(f"{self.agent} · {MODES.get(self.mode, self.mode)}")
        mid = height * 0.62
        half = width / 2 - 20
        if self.wave:                             # the waveform, left half
            cr.set_source_rgb(0.45, 0.8, 0.95)
            cr.set_line_width(1.5)
            step = half / max(1, len(self.wave) - 1)
            for i, x in enumerate(self.wave):
                point = (12 + i * step, mid - max(-1.0, min(1.0, x * 4)) * (height * 0.3))
                (cr.move_to if i == 0 else cr.line_to)(*point)
            cr.stroke()
        if self.levels:                           # the volume trace, right half
            cr.set_source_rgb(0.55, 0.9, 0.55)
            bar = half / TRACE_POINTS
            for i, value in enumerate(self.levels):
                h = min(1.0, value * 6) * (height * 0.55)
                cr.rectangle(width / 2 + 8 + i * bar, height - 8 - h, max(1.0, bar - 0.5), h)
            cr.fill()


def main():
    # Without a display there is nothing to draw on; say so and exit, rather than waiting on input
    # with no window, which leaves the capture unit recording unseen. A capture unit run as a
    # daemon unit needs WAYLAND_DISPLAY in its declared environment.
    if not Gtk.init_check():
        print("indicator overlay: no display to draw on (is WAYLAND_DISPLAY set?)", file=sys.stderr)
        return 2
    if not Gtk4LayerShell.is_supported():
        print("indicator overlay: no layer shell: no Wayland display (WAYLAND_DISPLAY), a compositor "
              "without it, or libgtk4-layer-shell not preloaded (LD_PRELOAD)", file=sys.stderr)
        return 3
    app = Gtk.Application(application_id="org.maceff.VoiceIndicator", flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda a: setattr(a, "overlay", Overlay(a)))
    app.hold()
    return app.run([])


if __name__ == "__main__":
    sys.exit(main())
