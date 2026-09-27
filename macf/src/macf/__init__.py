"""
macf - Multi-Agent Coordination Framework tools

CLI tools for MacEff multi-agent environment framework.
Homophonous standin for legacy MACF, easier to type.
"""
__all__ = ["__version__"]


def __getattr__(name):
    # Read on first use, not on import: working it out imports importlib.metadata,
    # about 20 ms that every command and hook paid whether or not it showed the
    # version. ``from macf import __version__`` still works; it arrives here.
    if name == "__version__":
        from ._version import VERSION
        return VERSION
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")