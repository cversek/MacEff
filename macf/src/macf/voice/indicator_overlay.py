"""The recording indicator's overlay on a Linux Wayland desktop (MIS-0008 R21, R22).

Run by the capture unit under the system's Python, which carries GTK 4 and gtk4-layer-shell; it
imports nothing from macf. It reads one JSON object per line on its stdin and draws:

    {"show": {"agent": "...", "mode": "wake_phrase|hold_key|continual_voice"}}
    {"level": 0.12, "wave": [-0.1, 0.2, ...], "spectrum": [0.0, 0.4, ...]}
    {"window": 0.6}
    {"text": "the words transcribed so far"}
    {"hide": true}

A strip at the top of the screen shows the agent's name, the mode and how long the recording has run,
the voice's loudness band and a level meter, and the end window along its bottom. Under it, two views
the operator opens or closes: the words transcribed so far, and a spectrogram. Each remembers whether
it was left open, across recordings and restarts, in one small file under XDG_STATE_HOME; that is the
only thing it writes, and it sends nothing back to the capture unit. It exits when its stdin closes,
so it never outlives the capture unit.
"""
import json
import os
import sys
import time
from pathlib import Path

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


MODES = {"wake_phrase": "wake phrase", "hold_key": "hold key", "continual_voice": "continual voice",
         "key_session": "key session · locked"}
TRACE_POINTS = 140
#: How opaque the dark tint behind the indicator is, between the 50% and 80% the operator suggested.
TINT = 0.65
WIDTH, HEIGHT = 620, 72
#: The spectrogram view: how many frames it scrolls through (12.5 a second), and its height.
SPEC_FRAMES, SPEC_HEIGHT = 200, 110
#: Which views the operator left open, so the next recording opens them again.
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "maceff" / "voice_indicator.json"
CSS = b"""
window { background: transparent; }
.voice-view { background-color: rgba(15, 18, 23, 0.88); border-radius: 8px; padding: 4px 8px; }
.voice-view label { color: #eeeeee; font-size: 11px; }
"""


def load_open_views():
    try:
        return set(json.loads(STATE.read_text()).get("open", []))
    except (OSError, ValueError, AttributeError):
        return set()                          # nothing remembered yet, or unreadable: start with views closed


def save_open_views(names):
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"open": sorted(names)}))
    except OSError as e:
        print(f"indicator overlay: couldn't remember which views are open: {e}", file=sys.stderr)


def heat(v):
    """A spectrogram cell's color: dark blue for quiet, through amber, to white for loud."""
    if v < 0.5:
        return 0.05 + v * 1.4, 0.07 + v * 0.6, 0.20 + v * 0.3  # noqa: MACEFF004 - an (r, g, b) color, whose order is fixed by convention and cairo takes it as is
    v -= 0.5
    return 0.75 + v * 0.5, 0.37 + v * 1.2, 0.35 + v * 1.3  # noqa: MACEFF004 - an (r, g, b) color, as above


class Overlay:
    def __init__(self, app):
        self.agent, self.mode = "", ""
        self.wave, self.levels, self.spectra = [], [], []
        self.started = time.monotonic()
        #: How much of the end window is left (R56): a bar along the bottom edge that drains in a pause.
        self.window = 1.0
        self.open_views = load_open_views()
        win = self.win = Gtk.ApplicationWindow(application=app)
        win.set_default_size(WIDTH, HEIGHT)
        win.set_decorated(False)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk4LayerShell.init_for_window(win)
        Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_margin(win, Gtk4LayerShell.Edge.TOP, 12)
        Gtk4LayerShell.set_keyboard_mode(win, Gtk4LayerShell.KeyboardMode.NONE)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.area = Gtk.DrawingArea()
        self.area.set_content_width(WIDTH)
        self.area.set_content_height(HEIGHT)
        self.area.set_draw_func(self.draw)
        box.append(self.area)
        # The words transcribed so far, the operator's request: "a window underneath that shows you that".
        self.text = Gtk.Label(label="", xalign=0, wrap=True, max_width_chars=80)
        self.text.set_size_request(WIDTH - 24, -1)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.text)
        scroll.set_min_content_height(70)
        scroll.set_max_content_height(160)
        scroll.set_propagate_natural_height(True)
        self.scroll = scroll
        box.append(self.view("transcript", "Transcript so far", scroll))
        self.spec = Gtk.DrawingArea()
        self.spec.set_content_width(WIDTH - 16)
        self.spec.set_content_height(SPEC_HEIGHT)
        self.spec.set_draw_func(self.draw_spectrogram)
        box.append(self.view("spectrogram", "Spectrogram", self.spec))
        win.set_child(box)
        stream = Gio.DataInputStream.new(_unix_input(sys.stdin.fileno()))
        self.stream, self.app = stream, app
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self.on_line)

    def view(self, name, title, child):
        """An expander that opens as the operator last left it, and remembers each change."""
        expander = Gtk.Expander(label=title)
        expander.set_child(child)
        expander.set_expanded(name in self.open_views)
        expander.set_hexpand(True)
        # Darker than the strip's tint: these hold text, which must read over a busy window beneath.
        panel = Gtk.Box()
        panel.add_css_class("voice-view")
        panel.set_hexpand(True)
        panel.append(expander)

        def changed(widget, _param):
            (self.open_views.add if widget.get_expanded() else self.open_views.discard)(name)
            save_open_views(self.open_views)
        expander.connect("notify::expanded", changed)
        return panel

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
        elif "text" in message:
            self.text.set_label(str(message["text"]))
            adj = self.scroll.get_vadjustment()
            GLib.idle_add(lambda: adj.set_value(adj.get_upper()) or False)   # the newest words in view
        elif "show" in message:
            self.agent, self.mode = message["show"]["agent"], message["show"]["mode"]
            self.wave, self.levels, self.spectra, self.window = [], [], [], 1.0
            self.started = time.monotonic()
            self.text.set_label("")
            self.win.present()
        elif "hide" in message:
            self.win.set_visible(False)
        elif "level" in message:
            self.levels = (self.levels + [float(message["level"])])[-TRACE_POINTS:]
            self.wave = [float(x) for x in message.get("wave", [])]
            if "spectrum" in message:
                self.spectra = (self.spectra + [[float(v) for v in message["spectrum"]]])[-SPEC_FRAMES:]
                self.spec.queue_draw()
        self.area.queue_draw()

    def draw(self, _area, cr, width, height):
        """A transparent strip: a band of the voice's loudness, mirrored about a centre line and scrolling
        as the operator speaks (newest at the right), a small segmented level meter beside it, the agent,
        mode and elapsed time in small text, and the end window as a thin bar along the bottom (R21, R22, R56)."""
        cr.set_operator(0)                        # CLEAR: nothing behind the band is painted over
        cr.paint()
        cr.set_operator(2)                        # OVER
        # A dark tint behind it all, partly see-through, so the band reads against any wallpaper. The operator
        # asked for "a little bit of a darker tint... maybe do like 80% alpha or something or a 50% alpha".
        r = 10
        cr.new_sub_path()
        cr.arc(width - r, r, r, -1.5708, 0)
        cr.arc(width - r, height - r, r, 0, 1.5708)
        cr.arc(r, height - r, r, 1.5708, 3.1416)
        cr.arc(r, r, r, 3.1416, 4.7124)
        cr.close_path()
        cr.set_source_rgba(0.06, 0.07, 0.09, TINT)
        cr.fill()
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
        elapsed = int(time.monotonic() - self.started)
        # How long this recording has run, the operator's "little counter that says how long it is".
        cr.show_text(f"● {self.agent} · {MODES.get(self.mode, self.mode)} · {elapsed // 60}:{elapsed % 60:02d}")
        # The end window (R56): full while speaking or just paused, draining toward the utterance's end,
        # amber when it runs low. Speaking fills it again.
        if self.window < 0.35:
            cr.set_source_rgba(0.95, 0.75, 0.3, 0.95)
        else:
            cr.set_source_rgba(0.45, 0.8, 0.95, 0.85 if self.window < 1.0 else 0.4)
        cr.rectangle(0, height - 3, band_w * self.window, 3)
        cr.fill()

    def draw_spectrogram(self, _area, cr, width, height):
        """Frequency up, time across, newest at the right: each column one frame's bands, colored by loudness."""
        if not self.spectra:
            return
        bands = len(self.spectra[-1])
        col_w, row_h = width / SPEC_FRAMES, height / max(bands, 1)
        start = width - len(self.spectra) * col_w
        for i, column in enumerate(self.spectra):
            x = start + i * col_w
            for b, v in enumerate(column):
                cr.set_source_rgba(*heat(v), 0.95)
                cr.rectangle(x, height - (b + 1) * row_h, col_w + 0.5, row_h + 0.5)
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
