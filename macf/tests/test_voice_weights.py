"""The speech weights are fetched by the operator's approval and the engine reads the cache only (#1124).

The hub is a fake: nothing is downloaded and no network is used.
"""
import argparse
import os
import sys
import types

import pytest

from macf.voice.speech import cli, weights


class FakeHub:
    """The parts of huggingface_hub the weights module uses, over a repository of named files."""

    def __init__(self, files, cached=()):
        self.files = dict(files)
        self.cache = set(cached)
        self.downloads = []
        self.constants = types.SimpleNamespace(HF_HUB_OFFLINE=False)
        self.api_error = None

    def try_to_load_from_cache(self, repo, name):
        if name in getattr(self, "noexist", ()):
            return object()  # the hub's marker for a file it has recorded as absent from the repository
        return f"/cache/{name}" if name in self.cache else None

    def HfApi(self):
        hub = self

        class Api:
            def model_info(self, repo, files_metadata=False):
                if hub.api_error:
                    raise hub.api_error
                return types.SimpleNamespace(siblings=[types.SimpleNamespace(rfilename=n, size=s)
                                                       for n, s in hub.files.items()])
        return Api()

    def hf_hub_download(self, repo, name):
        self.downloads.append(name)
        self.cache.add(name)
        return f"/cache/{name}"


FILES = {"config.json": 2_000, "kokoro-v1_0.safetensors": 327_000_000, "voices/am_michael.safetensors": 500_000,
         "voices/af_heart.safetensors": 520_000, "voices/bm_george.safetensors": 510_000, "samples/x.wav": 900_000}


@pytest.fixture
def hub(monkeypatch):
    fake = FakeHub(FILES)
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


def test_fetch_downloads_exactly_the_named_files(hub):
    assert weights.fetch(["config.json", "voices/am_michael.safetensors"]) == [
        "/cache/config.json", "/cache/voices/am_michael.safetensors"]
    assert hub.downloads == ["config.json", "voices/am_michael.safetensors"]


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
