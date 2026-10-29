"""The MacEff channel's name, and the one safe way to read a channel event's source.

Kept apart from the channel server so the prompt hook, which runs on every prompt,
can read a tag without importing the server.

READ ONLY THE TAG THAT OPENS THE PROMPT. Measured on Claude Code 2.1.296: content
sent through a channel can contain an opening ``<channel source="...">`` tag of its
own; the client escapes a closing tag in content but not an opening one, so a forged
tag naming another channel arrives, unchanged, inside the real event. Only the tag at
the very start was set by the transport (MIS-0002-R121
(hooks_MUST_read_source_from_origin_or_opening_tag)).

The source itself is read by ``macf.utils.input_origin``, the reader both producers
of the operator's activity share. This module reads the notice's other attributes.
"""
import re
from typing import Dict, Optional

from macf.utils.input_origin import (
    MACEFF_CHANNEL_SOURCE,
    from_maceff_channel,
    opening_channel_source,
)

SERVER_NAME = "maceff"
PLUGIN_NAME = "maceff-channel"
#: How Claude Code names a plugin's channel: ``plugin:<plugin>:<server>``. Kept in
#: ``input_origin`` so the transcript monitor can test it without this package.
CHANNEL_SOURCE = MACEFF_CHANNEL_SOURCE

_OPENING = re.compile(r'<channel ([^>\n]*)>')
_ATTR = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)="([^"]*)"')


def opening_tag(prompt: str) -> Optional[Dict[str, str]]:
    """The attributes of the channel tag that opens *prompt*, or None if it opens with none.

    Anchored at the start of the prompt (leading whitespace allowed) and limited to
    the first line, so a tag anywhere later is never read.
    """
    text = prompt.lstrip()
    match = _OPENING.match(text)
    if match is None:
        return None
    return dict(_ATTR.findall(match.group(1)))


def is_maceff_notice(prompt: str) -> bool:
    """True when the prompt is an event of the MacEff channel, by its opening tag."""
    return from_maceff_channel(opening_channel_source(prompt))
