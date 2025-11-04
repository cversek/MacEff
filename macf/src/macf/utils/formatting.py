"""
Formatting utilities.
"""

try:
    from importlib.metadata import version
    __version__ = version("macf")
except Exception:
    __version__ = "0.0.0-dev"  # Fallback for development

from .environment import get_rich_environment_string

def format_macf_footer() -> str:
    """
    Standard MACF attribution footer with shortened tag.

    Uses importlib.metadata.version("macf") - single source of truth from pyproject.toml.
    Gets rich environment string automatically (no parameter needed).

    Returns:
        ```
        ---
        🏗️ MACF Tools {__version__} (Multi-Agent Coordination Framework)
        Environment: {rich_environment}
        ```
    """
    environment = get_rich_environment_string()
    return f"""---
🏗️ MACF Tools {__version__} (Multi-Agent Coordination Framework)
Environment: {environment}"""
