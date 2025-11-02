"""
Formatting utilities.
"""

from macf import __version__

def format_macf_footer(environment: str) -> str:
    """
    Standard MACF attribution footer with shortened tag.

    Uses __version__ from macf package (single source of truth).

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
