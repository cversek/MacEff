"""
Formatting utilities.
"""

try:
    from importlib.metadata import version
    __version__ = version("macf")
except Exception:
    __version__ = "0.0.0-dev"  # Fallback for development

def format_macf_footer(environment: str) -> str:
    """
    Standard MACF attribution footer with shortened tag.

    Uses importlib.metadata.version("macf") - single source of truth from pyproject.toml.

    Args:
        environment: From detect_execution_environment()

    Returns:
        ```
        ---
        🏗️ MACF Tools {__version__} (Multi-Agent Coordination Framework)
        Environment: {environment}
        ```
    """
    return f"""---
🏗️ MACF Tools {__version__} (Multi-Agent Coordination Framework)
Environment: {environment}"""
