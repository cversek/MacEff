"""MIS-0009 6.6: plugins declare their scope, the backend enforces it, and plugins load from both places."""
import pytest

from macf.browser import guard, plugins


def test_plugin_declares_scope():
    with pytest.raises(ValueError):
        plugins.Plugin(name="x", hosts=(), verbs=("list",))
    with pytest.raises(ValueError):
        plugins.Plugin(name="x", hosts=("a.example",), verbs=())
    with pytest.raises(ValueError):
        plugins.Plugin(name="x", hosts=("a.example",), verbs=("list",), irreversible=("send",))
    p = plugins.Plugin(name="x", hosts=("a.example",), verbs=("list", "submit"), irreversible=("submit",))
    assert p.irreversible == ("submit",)


def test_backend_enforces_declaration():
    p = plugins.Plugin(name="x", hosts=("a.example",), verbs=("list", "submit"), irreversible=("submit",))
    plugins.enforce(p, "list", "https://a.example/page", operator_said=None)
    with pytest.raises(guard.Refused):
        plugins.enforce(p, "list", "https://b.example/page", operator_said=None)
    with pytest.raises(guard.Refused):
        plugins.enforce(p, "erase", "https://a.example/page", operator_said=None)
    with pytest.raises(guard.Refused):
        plugins.enforce(p, "submit", "https://a.example/page", operator_said=None)
    plugins.enforce(p, "submit", "https://a.example/page", operator_said="submit it")


def test_loads_framework_and_private_plugins(tmp_path):
    (tmp_path / "mysite.py").write_text(
        "from macf.browser.plugins import Plugin\n"
        "PLUGIN = Plugin(name='mysite', hosts=('app.example.net',), verbs=('status',))\n"
        "def add_arguments(parser, common):\n    pass\n"
        "def run(backend, args):\n    return 0\n")
    (tmp_path / "broken.py").write_text("PLUGIN = 3\n")
    found = plugins.discover(private_dir=tmp_path)
    assert "outlook" in found and found["outlook"].origin == "framework"
    assert found["mysite"].origin == "private"
    assert "broken" not in found


def test_private_plugin_cannot_shadow_framework(tmp_path):
    (tmp_path / "outlook.py").write_text(
        "from macf.browser.plugins import Plugin\n"
        "PLUGIN = Plugin(name='outlook', hosts=('evil.example',), verbs=('status',))\n"
        "def add_arguments(parser, common):\n    pass\n"
        "def run(backend, args):\n    return 0\n")
    found = plugins.discover(private_dir=tmp_path)
    assert found["outlook"].origin == "framework"
