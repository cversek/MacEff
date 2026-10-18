"""The organization allowlist of channel plugins, against what the declaration lists.

Claude Code reads ``allowedChannelPlugins`` from managed settings. When it is set, it replaces
the default list, so a channel it leaves out stops loading at the next start, the operator's
own messaging channel included, and the only sign is a line printed at start that nobody
reads after an unattended restart. A declaration lists every channel the list admits
(MIS-0002-R124 (allowlist_declaration_MUST_list_every_channel)), so the two can be compared
here: a channel the list admits and the declaration leaves out is one nobody declared, and a
channel the declaration lists and the allowlist leaves out will not load.
"""
import json
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

from macf.pd.interface import Declaration

#: Where Claude Code reads managed settings, Linux and macOS, as ``permission_watch`` reads them.
MANAGED_SETTINGS = (Path("/etc/claude-code/managed-settings.json"),
                    Path("/Library/Application Support/ClaudeCode/managed-settings.json"))

Plugin = Tuple[str, str]        # (plugin, marketplace)


def _entry(raw) -> Optional[Plugin]:
    """One allowlist entry: the documented object form, or the ``plugin@marketplace`` string the
    client also accepts. Anything else admits nothing, and is left out."""
    if isinstance(raw, dict) and isinstance(raw.get("plugin"), str) and isinstance(raw.get("marketplace"), str):
        return raw["plugin"], raw["marketplace"]
    if isinstance(raw, str) and raw.count("@") == 1 and all(raw.split("@")):
        plugin, marketplace = raw.split("@")
        return plugin, marketplace
    return None


def managed_allowlist(files: Optional[Iterable[Path]] = None) -> Optional[Set[Plugin]]:
    """The channel plugins the organization allowlist admits, or None when no managed settings
    file sets one. A file that exists and can't be read raises OSError or ValueError, because
    a list that can't be read is not the same as no list. ``files`` defaults to
    ``MANAGED_SETTINGS``, read at call time so a test can point it elsewhere.

    Only the files are read. Claude Code also takes managed settings from macOS configuration
    profiles and from an organization's admin console, and an allowlist set there isn't seen
    here, so it reads as no allowlist."""
    for f in (MANAGED_SETTINGS if files is None else files):
        if not f.exists():
            continue
        settings = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(settings, dict) or "allowedChannelPlugins" not in settings:
            continue
        entries = settings["allowedChannelPlugins"]
        if not isinstance(entries, list):
            raise ValueError(f"{f}: allowedChannelPlugins is not a list")
        return {e for e in (_entry(r) for r in entries) if e is not None}
    return None


def _names(plugins: Iterable[Plugin]) -> str:
    return ", ".join(f"{p}@{m}" for p, m in sorted(plugins))


def findings(declaration: Declaration, admitted: Optional[Set[Plugin]]) -> List[str]:
    """What differs between the allowlist and the declaration's ``allowlisted_channels``, one line
    each; empty when they agree, or when the deployment sets no allowlist."""
    if admitted is None:
        return []
    why = "(MIS-0002-R124 (allowlist_declaration_MUST_list_every_channel))"
    if declaration.allowlisted_channels is None:
        if not admitted:
            return [f"the organization allowlist admits no channel plugin, so no channel loads; "
                    f"declare allowlisted_channels as [] to say that is meant {why}"]
        return [f"the organization allowlist admits {len(admitted)} channel plugin(s) ({_names(admitted)}), "
                f"and the declaration lists none: list every one in allowlisted_channels {why}"]
    declared = {(c.plugin, c.marketplace) for c in declaration.allowlisted_channels}
    out = []
    if admitted - declared:
        out.append(f"the organization allowlist admits {_names(admitted - declared)}, which the "
                   f"declaration's allowlisted_channels leaves out {why}")
    if declared - admitted:
        out.append(f"the declaration lists {_names(declared - admitted)}, which the organization "
                   f"allowlist leaves out, so it won't load {why}")
    return out
