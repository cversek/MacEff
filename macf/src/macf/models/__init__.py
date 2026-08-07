"""
Pydantic models for MacEff Named Agents v0.3 configuration validation.

This module provides type-safe validation for agents.yaml and projects.yaml
configuration files used in Named Agents architecture.
"""

from .agent_spec import (
    AgentSpec,
    SubagentSpec,
    AgentsConfig,
    ConsciousnessArtifactsConfig,
    DefaultsConfig,
    EgressPolicy,
)
from .project_spec import (
    ProjectSpec,
    ProjectsConfig,
    RepoMount,
    DataMount,
)

__all__ = [
    # Agent models
    'AgentSpec',
    'SubagentSpec',
    'AgentsConfig',
    'ConsciousnessArtifactsConfig',
    'DefaultsConfig',
    'EgressPolicy',
    # Project models
    'ProjectSpec',
    'ProjectsConfig',
    'RepoMount',
    'DataMount',
]
