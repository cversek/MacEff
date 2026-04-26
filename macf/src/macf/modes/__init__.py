"""
Modes subsystem — mode detection, emoji dashboard, Markov recommender.

Three-layer mode system:
- Operational modes: AUTO_MODE, USER_IDLE, QUIET_MODE, LOW_CONTEXT
- Work modes: DISCOVER, BUILD, CURATE, CONSOLIDATE
- Recommender: Markov transition model with Monte Carlo sampling

Policy spec: framework/policies/base/operations/mode_system.md
"""
from .detection import (
    detect_active_modes,
    anticipate_mode_change,
    format_mode_indicators,
    should_self_manage_closeout,
    should_closeout_now,
    is_quiet,
    get_current_work_mode,
    is_markov_eligible,
    apply_sprint_mode_lock,
    get_transition_distribution,
    sample_next_work_mode,
    get_skill_name_for_mode,
    format_recommendation,
    load_transition_config,
    OPERATIONAL_MODES,
    WORK_MODES,
    ALL_MODES,
)
