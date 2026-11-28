"""The speech weights are fetched by the operator's approval and the engine reads the cache only (#1124).

The hub is a fake: nothing is downloaded and no network is used.
"""
import argparse
import hashlib
import os
import sys
import types

import pytest

from macf.voice.speech import cli, weights


class FakeHub:
    """The parts of huggingface_hub the weights module uses, over a repository of named files."""

    def __init__(self, files, cached=(), root=None):
        self.files = dict(files)
        self.cache = set(cached)
        self.root = root
        self.bytes = {}            # name -> the bytes a download writes (default: b"x" * size, capped)
        self.lfs = set()           # names the hub gives a SHA-256 for
        self.downloads = []
        self.downloaded = set()    # names a download wrote to disk under root
        self.constants = types.SimpleNamespace(HF_HUB_OFFLINE=False)
        self.api_error = None

    def try_to_load_from_cache(self, repo, name):
        if name in getattr(self, "noexist", ()):
            return object()  # the hub's marker for a file it has recorded as absent from the repository
        if self.root is not None and name in self.downloaded:
            path = self.root / name.replace("/", "_")
            return str(path) if path.exists() else None      # a file deleted from the cache is no longer cached
        return f"/cache/{name}" if name in self.cache else None

    def HfApi(self):
        hub = self

        class Api:
            def model_info(self, repo, files_metadata=False):
                if hub.api_error:
                    raise hub.api_error
                return types.SimpleNamespace(siblings=[
                    types.SimpleNamespace(rfilename=n, size=s, lfs=(types.SimpleNamespace(sha256=hub.sha(n))
                                                                    if n in hub.lfs else None))
                    for n, s in hub.files.items()])
        return Api()

    def content(self, name):
        return self.bytes.get(name, f"content of {name}".encode())

    def sha(self, name):
        return hashlib.sha256(self.content(name)).hexdigest()

    def hf_hub_download(self, repo, name):
        self.downloads.append(name)
        self.cache.add(name)
        self.downloaded.add(name)
        if self.root is None:
            return f"/cache/{name}"
        path = self.root / name.replace("/", "_")
        blob = self.root / ("blob_" + name.replace("/", "_"))      # the hub's cache: a snapshot link to a blob
        blob.write_bytes(self.bytes.get("DOWNLOADED:" + name, self.content(name)))
        if path.is_symlink() or path.exists():
            path.unlink()
        path.symlink_to(blob)
        return str(path)


FILES = {"config.json": 2_000, "kokoro-v1_0.safetensors": 327_000_000, "voices/am_michael.safetensors": 500_000,
         "voices/af_heart.safetensors": 520_000, "voices/bm_george.safetensors": 510_000, "samples/x.wav": 900_000}


@pytest.fixture
def hub(monkeypatch, tmp_path):
    fake = FakeHub(FILES, root=tmp_path)
    monkeypatch.setattr(weights, "_hub", lambda: fake)
    return fake


def _args(**kw):
    return argparse.Namespace(**{"voice": [], "approve": [], **kw})


def test_a_file_the_hub_has_recorded_as_absent_is_not_cached(hub):
    hub.noexist = {"config.json"}
    assert weights.is_cached("config.json") is False
    hub.cache = {"kokoro-v1_0.safetensors"}
    assert weights.is_cached("kokoro-v1_0.safetensors") is True and weights.is_cached("voices/x.safetensors") is False


def test_a_blend_names_each_voice_and_the_wanted_files_are_core_plus_one_per_voice():
    assert weights.voice_names("am_michael:0.6,bm_george:0.4") == ["am_michael", "bm_george"]
    assert weights.voice_names("af_heart") == ["af_heart"]
    assert weights.wanted(["bm_george", "am_michael", "am_michael"]) == [
        "config.json", "kokoro-v1_0.safetensors", "voices/am_michael.safetensors", "voices/bm_george.safetensors"]


def test_the_listing_gives_sizes_and_what_is_cached(hub):
    hub.cache = {"config.json"}
    files = weights.listing(weights.wanted(["am_michael"]))
    assert [(f.name, f.size, f.cached) for f in files] == [
        ("config.json", 2_000, True), ("kokoro-v1_0.safetensors", 327_000_000, False),
        ("voices/am_michael.safetensors", 500_000, False)]


def test_a_voice_the_repository_does_not_have_is_an_error_naming_it(hub):
    with pytest.raises(weights.WeightsMissing, match="voices/zz_nobody.safetensors"):
        weights.listing(weights.wanted(["zz_nobody"]))


def test_an_unreachable_hub_lists_the_files_without_sizes_and_says_so(hub, capsys):
    hub.api_error = OSError("network is down")
    hub.cache = {"config.json"}
    files = weights.listing(["config.json", "kokoro-v1_0.safetensors"])
    assert [(f.name, f.size, f.cached) for f in files] == [("config.json", None, True),
                                                           ("kokoro-v1_0.safetensors", None, False)]
    assert "couldn't read the file sizes" in capsys.readouterr().err


def _files(*names):
    return [weights.File(n, FILES[n], False) for n in names]


def test_fetch_downloads_exactly_the_named_files(hub, tmp_path):
    got = weights.fetch(_files("config.json", "voices/am_michael.safetensors"))
    assert got == [str(tmp_path / "config.json"), str(tmp_path / "voices_am_michael.safetensors")]
    assert hub.downloads == ["config.json", "voices/am_michael.safetensors"]


def test_a_downloaded_file_is_checked_against_the_hubs_sha256(hub):
    hub.lfs = {"kokoro-v1_0.safetensors"}
    listed = weights.listing(["kokoro-v1_0.safetensors"])
    assert listed[0].sha256 == hub.sha("kokoro-v1_0.safetensors")
    assert weights.fetch(listed)                                          # the bytes match: accepted
    hub.bytes["DOWNLOADED:kokoro-v1_0.safetensors"] = b"not what the hub holds"
    with pytest.raises(weights.WeightsMissing, match="SHA-256 is not the hub's"):
        weights.fetch(listed)


def test_a_file_refused_on_its_checksum_is_deleted_so_the_engine_cannot_load_it(hub, tmp_path):
    hub.lfs = {"kokoro-v1_0.safetensors"}
    listed = weights.listing(["kokoro-v1_0.safetensors"])
    hub.bytes["DOWNLOADED:kokoro-v1_0.safetensors"] = b"not what the hub holds"
    with pytest.raises(weights.WeightsMissing, match="deleted it from the cache"):
        weights.fetch(listed)
    assert not (tmp_path / "kokoro-v1_0.safetensors").is_symlink() and not (tmp_path / "kokoro-v1_0.safetensors").exists()
    assert not (tmp_path / "blob_kokoro-v1_0.safetensors").exists()     # the blob behind the link too
    assert weights.is_cached("kokoro-v1_0.safetensors") is False
    with pytest.raises(weights.WeightsMissing, match="voice models fetch"):
        weights.require(["kokoro-v1_0.safetensors"])             # an unattended restart refuses it, not loads it


def test_a_small_file_with_no_checksum_from_the_hub_is_taken_as_downloaded(hub):
    listed = weights.listing(["config.json"])
    assert listed[0].sha256 is None
    hub.bytes["DOWNLOADED:config.json"] = b"anything"
    assert weights.fetch(listed)


def test_require_names_what_is_missing_and_the_command_that_fetches_it(hub):
    hub.cache = {"config.json", "kokoro-v1_0.safetensors"}
    weights.require(["config.json", "kokoro-v1_0.safetensors"])           # all there: nothing raised
    with pytest.raises(weights.WeightsMissing) as e:
        weights.require(["config.json", "voices/af_heart.safetensors"])
    said = str(e.value)
    assert "voices/af_heart.safetensors" in said and "config.json" not in said.split("missing")[0]
    assert "macf_tools voice models fetch --voice af_heart" in said


def test_going_offline_sets_the_environment_and_the_hubs_constant(hub, monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    weights.go_offline()
    assert os.environ["HF_HUB_OFFLINE"] == "1" and hub.constants.HF_HUB_OFFLINE is True


def test_interactive_approval_takes_only_the_yeses():
    files = [weights.File("a", 1, False), weights.File("b", 2, False), weights.File("c", 3, False)]
    answers = iter(["y", "n", "YES"])
    assert weights.approve_interactively(files, lambda prompt: next(answers)) == ["a", "c"]
    answers = iter(["", "no", "maybe"])
    assert weights.approve_interactively(files, lambda prompt: next(answers)) == []


# ── the command ───────────────────────────────────────────────────────────────

def test_fetch_with_nothing_approved_and_no_terminal_fetches_nothing_and_lists_the_files(hub, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert cli.cmd_models_fetch(_args(voice=["am_michael"])) == 3
    out = capsys.readouterr()
    assert hub.downloads == []
    assert "voices/am_michael.safetensors" in out.out and "327.0 MB" in out.out
    assert "approve each file you want with --approve" in out.err


def test_fetch_takes_only_the_approved_files(hub, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    rc = cli.cmd_models_fetch(_args(voice=["am_michael"], approve=["config.json", "voices/am_michael.safetensors"]))
    assert hub.downloads == ["config.json", "voices/am_michael.safetensors"]
    assert rc == 3                                                   # the weights file is still missing
    assert "still missing: kokoro-v1_0.safetensors" in capsys.readouterr().err


def test_fetch_of_everything_approved_succeeds_and_a_second_run_has_nothing_to_do(hub, capsys):
    names = weights.wanted(["am_michael"])
    assert cli.cmd_models_fetch(_args(voice=["am_michael"], approve=names)) == 0
    assert sorted(hub.downloads) == sorted(names)
    assert cli.cmd_models_fetch(_args(voice=["am_michael"])) == 0
    assert len(hub.downloads) == len(names)
    assert "everything the engine needs is cached" in capsys.readouterr().out


def test_an_approval_naming_a_file_that_is_not_on_the_list_fetches_nothing(hub, capsys):
    rc = cli.cmd_models_fetch(_args(voice=["am_michael"], approve=["config.json", "samples/x.wav"]))
    assert rc == 2 and hub.downloads == []
    assert "not a file to fetch: samples/x.wav" in capsys.readouterr().err


def test_at_a_terminal_each_file_is_asked_about(hub, monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    answers = iter(["y", "n", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert cli.cmd_models_fetch(_args(voice=["am_michael"])) == 3
    assert hub.downloads == ["config.json", "voices/am_michael.safetensors"]


def test_status_says_what_is_cached_and_exits_by_it(hub, capsys):
    hub.cache = {"config.json"}
    assert cli.cmd_models_status(_args(voice=["am_michael"])) == 1
    assert "cached   config.json" in capsys.readouterr().out
    hub.cache = set(weights.wanted(["am_michael"]))
    assert cli.cmd_models_status(_args(voice=["am_michael"])) == 0


def test_the_unknown_voice_is_exit_two_with_its_name(hub, capsys):
    assert cli.cmd_models_fetch(_args(voice=["zz_nobody"])) == 2
    assert "zz_nobody" in capsys.readouterr().err


# ── the engine ────────────────────────────────────────────────────────────────

class _Model:
    sample_rate = 24000

    def __init__(self):
        self.voices = []

    def generate(self, text, voice, speed, lang_code):
        self.voices.append(voice)
        import numpy as np
        yield types.SimpleNamespace(audio=np.zeros(240, np.float32))


@pytest.fixture
def mlx(monkeypatch):
    loads = []
    model = _Model()
    utils = types.ModuleType("mlx_audio.tts.utils")
    utils.load_model = lambda name: loads.append(name) or model
    for name in ("mlx_audio", "mlx_audio.tts"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "mlx_audio.tts.utils", utils)
    return types.SimpleNamespace(loads=loads, model=model)


def test_the_engine_will_not_start_on_weights_that_were_not_fetched_and_downloads_nothing(hub, mlx):
    from macf.voice.speech.macos import MlxKokoroEngine
    with pytest.raises(RuntimeError, match="macf_tools voice models fetch"):
        MlxKokoroEngine()
    assert mlx.loads == [] and hub.downloads == []


def test_the_engine_starts_from_the_cache_and_reads_the_cache_only(hub, mlx, monkeypatch):
    from macf.voice.speech.macos import MLX_KOKORO, MlxKokoroEngine
    hub.cache = set(weights.wanted([weights.WARMUP_VOICE]))
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    MlxKokoroEngine()
    assert mlx.loads == [MLX_KOKORO] and os.environ["HF_HUB_OFFLINE"] == "1"
    assert mlx.model.voices == [weights.WARMUP_VOICE]                  # its first line, in the warm-up voice


def test_a_voice_that_was_not_fetched_is_said_not_downloaded(hub, mlx):
    from macf.voice.speech.macos import MlxKokoroEngine
    hub.cache = set(weights.wanted([weights.WARMUP_VOICE]))
    engine = MlxKokoroEngine()
    with pytest.raises(weights.WeightsMissing, match="voice models fetch --voice af_heart"):
        engine.say("hello", "af_heart", 1.0, "en-us")
    assert hub.downloads == []
    hub.cache.add("voices/af_heart.safetensors")                       # fetched by the operator since
    engine.say("hello", "af_heart", 1.0, "en-us")
    assert mlx.model.voices[-1] == "af_heart"


def test_a_fetch_whose_bytes_are_not_the_hubs_is_refused_with_its_own_exit(hub, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    hub.lfs = {"kokoro-v1_0.safetensors"}
    hub.bytes["DOWNLOADED:kokoro-v1_0.safetensors"] = b"tampered"
    assert cli.cmd_models_fetch(_args(voice=["am_michael"], approve=["kokoro-v1_0.safetensors"])) == 4
    assert "SHA-256 is not the hub's" in capsys.readouterr().err


def test_the_repository_is_the_one_the_engine_names():
    from macf.voice.speech.macos import MLX_KOKORO
    assert weights.REPO == "prince-canuma/Kokoro-82M" and MLX_KOKORO == weights.REPO


def test_a_blend_is_spoken_in_its_heaviest_voice_and_only_that_voice_must_be_fetched(hub, mlx):
    from macf.voice.speech.macos import MlxKokoroEngine
    hub.cache = set(weights.wanted([weights.WARMUP_VOICE, "bm_george"]))   # the blend's other voice is not fetched
    engine = MlxKokoroEngine()
    engine.say("hello", "bm_george:0.7,af_heart:0.3", 1.0, "en-us")
    assert mlx.model.voices[-1] == "bm_george"
    with pytest.raises(weights.WeightsMissing, match="--voice af_heart"):
        engine.say("hello", "af_heart:0.7,bm_george:0.3", 1.0, "en-us")


def test_without_a_voice_named_the_agents_own_voice_is_the_one_listed(hub, monkeypatch, capsys):
    from macf.pd.interface import SpeechSettings
    monkeypatch.setattr("macf.voice.speech.__main__.settings_for",
                        lambda home: SpeechSettings(voice="bm_george:0.6,am_michael:0.4"))
    monkeypatch.setattr(cli, "_home", lambda: None)
    assert cli.cmd_models_status(_args()) == 1
    out = capsys.readouterr().out
    assert "voices/bm_george.safetensors" in out and "voices/am_michael.safetensors" in out
    assert "af_heart" not in out


def test_an_unreadable_declaration_lists_the_warm_up_voice_and_says_why(hub, monkeypatch, capsys):
    def broken(home):
        raise OSError("declaration gone")
    monkeypatch.setattr("macf.voice.speech.__main__.settings_for", broken)
    monkeypatch.setattr(cli, "_home", lambda: None)
    cli.cmd_models_status(_args())
    out = capsys.readouterr()
    assert f"voices/{weights.WARMUP_VOICE}.safetensors" in out.out
    assert "the agent's voice couldn't be read (OSError: declaration gone)" in out.err
