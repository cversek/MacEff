"""Wake-phrase definition, recording, training and measurement (MIS-0008 6.5)."""

#: What a kept clip can be: the phrase, something close to it, ordinary speech, the quiet room, and
#: another agent's phrase that must not wake this one (R24). Here, so the CLI can list them cheaply.
KINDS = ("phrase", "near_miss", "speech", "room", "other_phrase")


class PhraseRefused(ValueError):
    """A phrase that can't make a working wake, with the reason."""
