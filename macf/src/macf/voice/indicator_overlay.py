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
TRACE_POINTS = 140
WIDTH, HEIGHT = 620, 72


class Overlay:
    def __init__(self, app):
        self.agent, self.mode = "", ""
        self.wave, self.levels = [], []
        #: How much of the end window is left (R56): a bar along the bottom edge that drains in a pause.
        self.window = 1.0
        win = self.win = Gtk.ApplicationWindow(application=app)
        win.set_default_size(WIDTH, HEIGHT)
        win.set_decorated(False)
        # Transparent, as the desktop's own indicator is: only the band and the meter are drawn.
        css = Gtk.CssProvider()
        css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
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
        if "window" in message:
            self.window = max(0.0, min(1.0, float(message["window"])))
        elif "show" in message:
            self.agent, self.mode = message["show"]["agent"], message["show"]["mode"]
            self.wave, self.levels, self.window = [], [], 1.0
            self.win.present()
        elif "hide" in message:
            self.win.set_visible(False)
        elif "level" in message:
            self.levels = (self.levels + [float(message["level"])])[-TRACE_POINTS:]
            self.wave = [float(x) for x in message.get("wave", [])]
        self.area.queue_draw()

    def draw(self, _area, cr, width, height):
        """A transparent strip: a band of the voice's loudness, mirrored about a centre line and scrolling
        as the operator speaks (newest at the right), a small segmented level meter beside it, the agent
        and mode in small text, and the end window as a thin bar along the bottom (R21, R22, R56)."""
        cr.set_operator(0)                        # CLEAR: nothing behind the band is painted over
        cr.paint()
        cr.set_operator(2)                        # OVER
        meter_w = 14
        band_w = width - meter_w - 10
        mid = height / 2
        if self.levels:
            cr.set_source_rgba(0.93, 0.58, 0.13, 0.95)   # amber, the band
            step = band_w / TRACE_POINTS
            start = band_w - len(self.levels) * step      # the newest sample is at the right edge
            for i, value in enumerate(self.levels):
                h = max(1.0, min(1.0, value * 7) * (height * 0.42))
                cr.rectangle(start + i * step, mid - h, max(1.0, step - 0.6), 2 * h)
            cr.fill()
        now = self.levels[-1] if self.levels else 0.0
        segments, seg_h = 10, (height - 16) / 10
        lit = round(min(1.0, now * 7) * segments)
        for s in range(segments):                  # the level meter, bottom up
            y = height - 8 - (s + 1) * seg_h
            if s < lit:
                cr.set_source_rgba(*(0.45, 0.85, 0.45) if s < 6 else (0.95, 0.8, 0.3) if s < 8 else (0.95, 0.35, 0.3), 0.95)
            else:
                cr.set_source_rgba(0.5, 0.5, 0.5, 0.25)
            cr.rectangle(width - meter_w, y + 1, meter_w, seg_h - 2)
            cr.fill()
        cr.set_source_rgba(0.95, 0.95, 0.95, 0.85)
        cr.select_font_face("Sans")
        cr.set_font_size(11)
        cr.move_to(4, 12)
        cr.show_text(f"● {self.agent} · {MODES.get(self.mode, self.mode)}")
        # The end window (R56): full while speaking or just paused, draining toward the utterance's end,
        # amber when it runs low. Speaking fills it again.
        if self.window < 0.35:
            cr.set_source_rgba(0.95, 0.75, 0.3, 0.95)
        else:
            cr.set_source_rgba(0.45, 0.8, 0.95, 0.85 if self.window < 1.0 else 0.4)
        cr.rectangle(0, height - 3, band_w * self.window, 3)
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
