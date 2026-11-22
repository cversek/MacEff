"""The recording indicator's overlay on macOS (MIS-0008 R21, R22).

Run by the capture unit as its own process, under a Python that carries PyObjC (AppKit); it
imports nothing from macf. It reads the same JSON lines as the Linux overlay on its stdin:

    {"show": {"agent": "...", "mode": "wake_phrase|hold_key|continual_voice|key_session"}}
    {"level": 0.12, "wave": [-0.1, 0.2, ...], "spectrum": [...]}
    {"window": 0.6}
    {"text": "the words so far", "tentative": "..."}
    {"hide": true}

A borderless, non-activating panel at the top of the main screen shows the agent's name, the
mode and how long the recording has run, a waveform and level meter, the words so far, and the
end window along its bottom. It never takes focus or the mouse, so typing goes on reaching the
front app. It writes nothing, sends nothing back, and exits when its stdin closes.
"""
import json
import sys
import threading
import time

import objc
from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered, NSBezierPath,
                    NSColor, NSFont, NSFontAttributeName, NSForegroundColorAttributeName, NSMakeRect, NSPanel,
                    NSScreen, NSStatusWindowLevel, NSView, NSWindowCollectionBehaviorCanJoinAllSpaces,
                    NSWindowCollectionBehaviorStationary, NSWindowStyleMaskBorderless,
                    NSWindowStyleMaskNonactivatingPanel)
from Foundation import NSObject, NSString
from PyObjCTools import AppHelper

MODES = {"wake_phrase": "wake phrase", "hold_key": "hold key", "continual_voice": "continual voice",
         "key_session": "key session · locked"}
WIDTH, HEIGHT = 620, 84
TRACE_POINTS = 140


class IndicatorView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(IndicatorView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.agent, self.mode, self.started = "", "", time.monotonic()
        self.wave, self.levels, self.left = [], [], 1.0
        self.so_far, self.tentative = "", ""
        return self

    def isFlipped(self):
        return True

    @objc.python_method
    def _text(self, text, x, y, size, color):
        attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(size), NSForegroundColorAttributeName: color}
        NSString.stringWithString_(text).drawAtPoint_withAttributes_((x, y), attrs)

    def drawRect_(self, rect):
        w, h = self.bounds().size.width, self.bounds().size.height
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.06, 0.07, 0.09, 0.82).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(self.bounds(), 10, 10).fill()
        white, grey = NSColor.whiteColor(), NSColor.colorWithCalibratedWhite_alpha_(0.75, 1.0)
        red = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.25, 0.25, 1.0)
        red.set()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(12, 12, 10, 10)).fill()
        elapsed = int(time.monotonic() - self.started)
        self._text("%s  ·  %s  ·  %d:%02d" % (self.agent, MODES.get(self.mode, self.mode), elapsed // 60, elapsed % 60),
                   30, 7, 13, white)
        if self.levels:  # level meter, right of the title
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.3, 0.85, 0.45, 1.0).set()
            NSBezierPath.fillRect_(NSMakeRect(w - 130, 11, 110 * min(1.0, self.levels[-1] * 8), 8))
        if self.wave:  # waveform band
            path, mid, n = NSBezierPath.bezierPath(), 40, len(self.wave)
            for i, v in enumerate(self.wave):
                point = (12 + (w - 24) * i / max(1, n - 1), mid - max(-1.0, min(1.0, v * 4)) * 12)
                path.moveToPoint_(point) if i == 0 else path.lineToPoint_(point)
            grey.set()
            path.setLineWidth_(1.2)
            path.stroke()
        words = (self.so_far + (" " + self.tentative if self.tentative else "")).strip()
        if words:
            self._text(words[-90:], 12, 54, 11, grey)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.35, 0.6, 1.0, 1.0).set()  # end window
        NSBezierPath.fillRect_(NSMakeRect(10, h - 5, (w - 20) * max(0.0, min(1.0, self.left)), 3))


class Controller(NSObject):
    def build(self):
        screen = NSScreen.mainScreen().frame()
        x = screen.origin.x + (screen.size.width - WIDTH) / 2
        y = screen.origin.y + screen.size.height - HEIGHT - 34
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, WIDTH, HEIGHT), style, NSBackingStoreBuffered, False)
        self.panel.setLevel_(NSStatusWindowLevel)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setIgnoresMouseEvents_(True)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                          | NSWindowCollectionBehaviorStationary)
        self.view = IndicatorView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        self.panel.setContentView_(self.view)
        return self

    def handle_(self, line):
        try:
            message = json.loads(str(line))
        except ValueError as e:
            print("indicator: a line that isn't JSON: %s" % e, file=sys.stderr)
            return
        v = self.view
        if "show" in message:
            v.agent, v.mode = message["show"].get("agent", ""), message["show"].get("mode", "")
            v.started, v.wave, v.levels, v.left, v.so_far, v.tentative = time.monotonic(), [], [], 1.0, "", ""
            self.panel.orderFrontRegardless()
        if "hide" in message:
            self.panel.orderOut_(None)
        if "level" in message:
            v.levels = (v.levels + [float(message["level"])])[-TRACE_POINTS:]
            v.wave = message.get("wave", v.wave)
        if "window" in message:
            v.left = float(message["window"])
        if "text" in message:
            v.so_far, v.tentative = message["text"], message.get("tentative", "")
        v.setNeedsDisplay_(True)

    def finish_(self, _):
        AppHelper.stopEventLoop()


def read_stdin(controller):
    for line in sys.stdin:
        if line.strip():
            controller.performSelectorOnMainThread_withObject_waitUntilDone_("handle:", line, False)
    controller.performSelectorOnMainThread_withObject_waitUntilDone_("finish:", None, False)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # no Dock icon, never the front app
    controller = Controller.alloc().init().build()
    threading.Thread(target=read_stdin, args=(controller,), daemon=True).start()
    AppHelper.runEventLoop(installInterrupt=True)


if __name__ == "__main__":
    main()
