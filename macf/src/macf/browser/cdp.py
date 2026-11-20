"""The `cdp` backend: attach to a browser the operator started and act within the rules (MIS-0009 6.1-6.5).

Observation reads the accessibility tree through a protocol session, so nothing runs in the page (R09).
Interaction uses Playwright's locators, after the guard's checks, and reports what changed (R10, R11).
Playwright is imported only when a command runs, so the rest of macf works without the browser extra (R04).
"""
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from macf.browser import guard

DEFAULT_ENDPOINT = "http://localhost:9222"
# A fixed settle time after each act: a person's pace for the operator's comfort, never randomized (R23, R24).
PACE_S = 1.0
OURS = "macf-browser"  # window.name of a tab the agent opened, so it can find and reuse its own tab (R08)

# Unsaved form input: fields whose value differs from their default (R14). Interaction only.
DIRTY_JS = """() => [...document.querySelectorAll('input:not([type=hidden]):not([type=password]), textarea')]
  .filter(e => e.offsetParent !== null).map(e => ({value: e.value || '', default: e.defaultValue || ''}))"""


def endpoint_ok(url: str) -> bool:
    """Only a debugging endpoint on this machine: the operator's own browser, never a remote one (R01)."""
    if not url:
        return False
    u = urlparse(url)
    return u.scheme in ("http", "ws") and u.hostname in ("localhost", "127.0.0.1", "::1") and bool(u.port)


def default_profile_dirs() -> List[Path]:
    home = Path(os.environ.get("HOME", str(Path.home())))
    mac = home / "Library" / "Application Support"
    return [mac / "Google" / "Chrome", mac / "Google" / "Chrome Beta", mac / "Chromium",
            mac / "Microsoft Edge", mac / "BraveSoftware" / "Brave-Browser",
            home / ".config" / "google-chrome", home / ".config" / "chromium",
            home / ".config" / "microsoft-edge", home / ".config" / "BraveSoftware" / "Brave-Browser"]


def check_profile_dir(path) -> Path:
    """The launcher's profile directory: never the operator's everyday profile (R02)."""
    p = Path(path).expanduser().resolve()
    for d in default_profile_dirs():
        d = d.resolve()
        if p == d or d in p.parents:
            raise guard.Refused(f"{p} is a browser's default profile: the agent's browser uses a separate profile "
                                f"(MIS-0009-R02)")
    return p


def launch(profile_dir, port: int = 9222, chrome: Optional[str] = None) -> int:
    """Start a browser on a separate profile with its debugging port open; the operator signs in by hand."""
    profile = check_profile_dir(profile_dir)
    profile.mkdir(parents=True, exist_ok=True)
    chrome = chrome or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    proc = subprocess.Popen([chrome, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                             "--no-first-run", "--no-default-browser-check"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.pid


def observe(page, session) -> dict:
    """What a page shows, read through the accessibility tree: no script runs in the page (R09)."""
    tree = session.send("Accessibility.getFullAXTree")
    nodes = []
    for n in tree.get("nodes", []):
        if n.get("ignored"):
            continue
        name = (n.get("name") or {}).get("value") or ""
        role = (n.get("role") or {}).get("value") or ""
        if name.strip() and role != "InlineTextBox":  # inline boxes repeat their StaticText parent
            nodes.append({"role": role, "name": name})
    root = next((n["name"] for n in nodes if n["role"] == "RootWebArea"), "")  # the title, without page script
    return {"url": page.url, "title": root, "nodes": nodes,
            "digest": guard.digest(f"{n['role']}:{n['name']}" for n in nodes)}


class Backend:
    """One attachment to the operator's browser for one command."""

    def __init__(self, endpoint: str, hosts: List[str], plugin=None, agent_home=None):
        if not endpoint_ok(endpoint):
            raise guard.Refused(f"{endpoint!r} is not a debugging endpoint on this machine (MIS-0009-R01)")
        self.endpoint, self.hosts, self.plugin = endpoint, list(hosts), plugin
        self.agent_home = agent_home
        self._pw = self.browser = None

    def start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise guard.Unavailable("Playwright is not installed: pip install 'macf[browser]' "
                                    "(then: playwright install chromium)") from e
        from playwright.sync_api import Error as PlaywrightError
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.connect_over_cdp(self.endpoint)
        except PlaywrightError as e:
            self._pw.stop()
            raise guard.Unavailable(f"no browser answers at {self.endpoint}: start one with "
                                    f"`macf_tools browser cdp launch` and sign in ({e})") from e
        return self

    def stop(self):
        # Detaching leaves every tab open: the operator closes tabs, never the agent (R08).
        if self._pw:
            self._pw.stop()

    ### tabs

    def _pages(self):
        return [p for c in self.browser.contexts for p in c.pages]

    def tabs(self, interact: bool = False) -> List[dict]:
        out = []
        for i, p in enumerate(self._pages()):
            tab = {"index": i, "url": p.url, "title": "", "ours": False, "page": p}
            if interact and guard.host_in_scope(p.url, self.hosts):
                tab["ours"] = p.evaluate("() => window.name") == OURS
            out.append(tab)
        return out

    def page_for(self, index: Optional[int], interact: bool, open_url: Optional[str] = None):
        tab = guard.select_tab(self.tabs(interact), self.hosts, index=index, interact=interact)
        if tab:
            return tab["page"]
        if not open_url:
            raise guard.Refused(f"no tab on {self.hosts}: name one with --tab, or open the site first")
        if not guard.host_in_scope(open_url, self.hosts):
            raise guard.Refused(f"{open_url} is outside the host scope {self.hosts} (MIS-0009-R05)")
        page = self.browser.contexts[0].new_page()
        page.goto(open_url, wait_until="domcontentloaded")
        page.evaluate(f"() => {{ window.name = '{OURS}'; }}")
        self.settle(page)
        return page

    ### observation

    def session(self, page):
        return page.context.new_cdp_session(page)

    def observe(self, page) -> dict:
        return observe(page, self.session(page))

    def state(self, page) -> dict:
        snap = self.observe(page)
        return {"url": snap["url"], "title": snap["title"], "digest": snap["digest"]}

    def screenshot(self, page, out) -> str:
        guard.check_capture(bool(self.plugin and self.plugin.no_capture))
        out = guard.check_destination(out, self.agent_home) if self.agent_home else Path(out).resolve()
        page.screenshot(path=str(out))
        return str(out)

    ### interaction

    def settle(self, page):
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except PlaywrightTimeout as e:
            print(f"⚠️ MACF: page still loading after 15 s (continuing): {e}", file=sys.stderr)
        time.sleep(PACE_S)

    def _one(self, page, role: str, name: str, exact: bool):
        loc = page.get_by_role(role, name=name, exact=exact)
        count = loc.count()
        visible = count == 1 and loc.is_visible()
        enabled = visible and loc.is_enabled()
        guard.check_target(count, visible, enabled, f"{role} {name!r}")
        return loc

    def click(self, page, role: str, name: str, exact: bool = False, operator_said: Optional[str] = None,
              real_input: bool = False) -> dict:
        loc = self._one(page, role, name, exact)
        words = guard.check_activation(role, name, operator_said)
        before = self.state(page)
        if real_input:
            box = loc.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=8)
            page.mouse.down()
            time.sleep(0.08)
            page.mouse.up()
        else:
            loc.click()
        self.settle(page)
        report = guard.change_report(before, self.state(page))
        report["operator_said"] = words
        return report

    def fill(self, page, role: str, name: str, text: str, exact: bool = False) -> dict:
        loc = self._one(page, role, name, exact)
        guard.check_fill_target({k: loc.get_attribute(k) for k in ("type", "autocomplete", "name", "id",
                                                                    "aria-label")})
        before = self.state(page)
        loc.fill(text)  # by value: no keystrokes, so no shortcut can fire (R37)
        self.settle(page)
        return guard.change_report(before, self.state(page))

    def press(self, page, chord: str, operator_said: Optional[str] = None) -> dict:
        words = guard.check_chord(chord, operator_said)
        before = self.state(page)
        page.keyboard.press(chord)
        self.settle(page)
        report = guard.change_report(before, self.state(page))
        report["operator_said"] = words
        return report

    def goto(self, page, url: str, discard: bool = False) -> dict:
        if not guard.host_in_scope(url, self.hosts):
            raise guard.Refused(f"{url} is outside the host scope {self.hosts} (MIS-0009-R05)")
        guard.check_navigation(page.evaluate(DIRTY_JS), discard)
        before = self.state(page)
        page.goto(url, wait_until="domcontentloaded")
        self.settle(page)
        return guard.change_report(before, self.state(page))

    def download(self, page, role: str, name: str, dest, exact: bool = False,
                 operator_said: Optional[str] = None) -> dict:
        loc = self._one(page, role, name, exact)
        guard.check_activation(role, name, operator_said)
        guard.check_destination(dest, self.agent_home)
        with page.expect_download(timeout=120000) as caught:
            loc.click()
        return guard.save_download(caught.value, dest, self.agent_home)
