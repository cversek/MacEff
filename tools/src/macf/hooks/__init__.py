"""Hook ecosystem for cognitive superpower capabilities."""

# Import run functions from handle_* modules
from .handle_session_start import run as session_start_run
from .handle_user_prompt_submit import run as user_prompt_submit_run
from .handle_stop import run as stop_run
from .handle_subagent_stop import run as subagent_stop_run
from .handle_pre_tool_use import run as pre_tool_use_run
from .handle_post_tool_use import run as post_tool_use_run

__all__ = [
    'session_start_run',
    'user_prompt_submit_run',
    'stop_run',
    'subagent_stop_run',
    'pre_tool_use_run',
    'post_tool_use_run'
]