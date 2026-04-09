"""
macf - Multi-Agent Coordination Framework tools

CLI tools for MacEff multi-agent environment framework.
Homophonous standin for legacy MACF, easier to type.
"""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("macf")
except PackageNotFoundError:
    __version__ = "0.0.0-unknown"