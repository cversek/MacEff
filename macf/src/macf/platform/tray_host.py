"""Whether this host can show the tray, and if not, why not.

MIS-0002-R73 (readout_MUST_say_tray_unavailable): where a host cannot show the tray, the
readout says so. The readout calls ``tray_host``; this module lives outside the tray
package so that asking never imports it (MIS-0002-R68 (layer_MUST-NOT_depend_on_tray)).
Whether the tray's extra is installed is answered by ``find_spec``, which locates a
module without running it.
"""
import getpass
import importlib.util
import os
import pwd
import sys
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class TrayHost:
    available: bool
    reason: str = ""

    def said(self) -> str:
        """The readout's line."""
        return "tray: available" if self.available else f"tray: unavailable ({self.reason})"


def console_owner() -> str:
    """Who owns the GUI console: the logged-in user, or root at the login window."""
    return pwd.getpwuid(os.stat("/dev/console").st_uid).pw_name


def tray_host(platform: str = sys.platform,
              find_spec: Callable = importlib.util.find_spec,
              owner: Callable[[], str] = console_owner,
              user: Optional[str] = None) -> TrayHost:
    """Whether this user, on this host, can be shown the tray; the reason when not.

    The tray is a macOS menu-bar app for now, so any other platform says so. On macOS
    it needs its extra, and a GUI session that belongs to this user: over SSH to a Mac
    sitting at the login window there is nowhere to show it.
    """
    if platform != "darwin":
        return TrayHost(False, "the tray runs only on macOS so far")
    if find_spec("rumps") is None:
        return TrayHost(False, "its extra is not installed: pip install 'macf[tray]'")
    try:
        who = owner()
    except (OSError, KeyError) as e:
        return TrayHost(False, f"the GUI console's owner cannot be read: {e}")
    if who == "root":
        return TrayHost(False, "nobody is logged in to the GUI")
    if who != (user or getpass.getuser()):
        return TrayHost(False, "the GUI belongs to another user")
    return TrayHost(True)
