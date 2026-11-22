"""The speech weights the MLX engine runs on, fetched with the operator's approval and then only read from disk (#1124).

The engine used to download its weights from Hugging Face at its first start, from a daemon, unasked, and an offline
first start fell back to the CPU model and stayed there until a start that happened online. Now the fetch is a command
the operator runs, file by file: ``macf_tools voice models fetch`` lists what the engine needs with each file's size,
and fetches only the files named with ``--approve`` (or answered yes to at a terminal). The worker loads from the local
cache alone: it sets the hub's offline switch before it loads, and a missing file is said with the command that
fetches it.

Which files: the model's ``config.json`` and weights, and one ``voices/<name>.safetensors`` for each voice the agent
speaks in (a blend names several). The repository holds 122 files, 389 MB, including every voice and sample audio;
none of those is listed unless the agent uses it.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence

#: Kokoro's MLX weights on Hugging Face.
REPO = "prince-canuma/Kokoro-82M"
#: The files the model itself needs, whatever the voice.
CORE = ("config.json", "kokoro-v1_0.safetensors")
#: The voice the engine speaks its first line in, at start, before any message has named one.
WARMUP_VOICE = "am_michael"


@dataclass(frozen=True)
class File:
    name: str
    size: Optional[int]
    cached: bool


class WeightsMissing(RuntimeError):
    """Files the engine needs are not in the local cache; the message says which and what fetches them."""


def voice_names(voice: str) -> List[str]:
    """The voices in a voice setting: one name, or the names of a blend such as ``am_michael:0.6,bm_george:0.4``."""
    return [p.split(":", 1)[0].strip() for p in voice.split(",") if p.strip()]


def wanted(voices: Iterable[str]) -> List[str]:
    """The file names the engine needs for these voices, in a stable order."""
    return list(CORE) + [f"voices/{v}.safetensors" for v in sorted(set(voices))]


def _hub():
    import huggingface_hub
    return huggingface_hub


def is_cached(name: str, repo: str = REPO) -> bool:
    """Whether the file is in the local cache. Reads nothing from the network."""
    found = _hub().try_to_load_from_cache(repo, name)
    return isinstance(found, str)


def listing(names: Sequence[str], repo: str = REPO) -> List[File]:
    """Each wanted file with its size and whether it is cached. Asks the hub for the sizes (metadata only,
    nothing is downloaded); a file the repository does not have is an error, not a silent omission."""
    sizes: Dict[str, Optional[int]] = {}
    try:
        info = _hub().HfApi().model_info(repo, files_metadata=True)
        sizes = {s.rfilename: s.size for s in info.siblings}
    except Exception as e:  # noqa: BLE001 - the hub is a network service: offline or refused, the list still names the files
        print(f"⚠️ MACF: voice: couldn't read the file sizes from {repo} ({type(e).__name__}: {e}); "
              f"listing the files without them", file=sys.stderr)
        return [File(n, None, is_cached(n, repo)) for n in names]
    absent = [n for n in names if n not in sizes]
    if absent:
        raise WeightsMissing(f"{repo} has no file named {', '.join(absent)}; the voice name may be wrong")
    return [File(n, sizes[n], is_cached(n, repo)) for n in names]


def fetch(names: Sequence[str], repo: str = REPO) -> List[str]:
    """Download exactly these files into the hub's cache and return their paths."""
    return [_hub().hf_hub_download(repo, n) for n in names]


def go_offline() -> None:
    """From here the process reads the cache only: the environment switch for libraries yet to import the hub, and
    the hub's own constant for one already imported."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        _hub().constants.HF_HUB_OFFLINE = True
    except ImportError:  # noqa: S110 - no hub installed: nothing to switch, and the engine's own import says so
        pass


def require(names: Sequence[str], repo: str = REPO) -> None:
    """Raise ``WeightsMissing`` naming the files not cached and the command that fetches them."""
    missing = [n for n in names if not is_cached(n, repo)]
    if missing:
        voices = [n[len("voices/"):-len(".safetensors")] for n in missing if n.startswith("voices/")]
        flags = "".join(f" --voice {v}" for v in voices)
        raise WeightsMissing(f"the speech weights are not fetched ({', '.join(missing)} missing from the local cache); "
                             f"run `macf_tools voice models fetch{flags}` and approve the files")


def megabytes(size: Optional[int]) -> str:
    return "size unknown" if size is None else f"{size / 1e6:.1f} MB"


def approve_interactively(files: Sequence[File], ask: Optional[Callable[[str], str]] = None) -> List[str]:
    """Ask about each file in turn and return the names answered ``y``. Anything else is no."""
    ask = ask or input
    return [f.name for f in files if ask(f"fetch {f.name} ({megabytes(f.size)})? [y/N] ").strip().lower() in ("y", "yes")]
