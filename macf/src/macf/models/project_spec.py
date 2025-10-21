"""
Pydantic models for projects.yaml configuration validation.

Models correspond to the YAML structure documented in:
docs/arch_v0.3_named_agents/05_implementation_guide.md (lines 127+)
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class RepoMount(BaseModel):
    """Git repository mount configuration."""

    url: str = Field(
        ...,
        description="Git repository URL (e.g., git@github.com:user/repo.git)"
    )

    path: str = Field(
        ...,
        description="Relative path within project workspace (e.g., repos/backend)"
    )


class DataMount(BaseModel):
    """Data directory mount configuration."""

    type: str = Field(
        ...,
        description="Mount type (e.g., 'bind')"
    )

    source: str = Field(
        ...,
        description="Source path on host filesystem"
    )

    target: str = Field(
        ...,
        description="Target path within project (relative, e.g., 'data')"
    )

    read_only: bool = Field(
        default=False,
        description="Whether mount is read-only"
    )


class ProjectSpec(BaseModel):
    """Specification for a project workspace."""

    context: str = Field(
        ...,
        description="Path to project context file (Project layer CLAUDE.md source)"
    )

    repos: Optional[List[RepoMount]] = Field(
        default_factory=list,
        description="Git repositories to clone into project workspace"
    )

    data_mounts: Optional[List[DataMount]] = Field(
        default_factory=list,
        description="Data directory mounts (bind mounts from host)"
    )

    commands: Optional[Dict[str, str]] = Field(
        default=None,
        description="Project-specific slash commands (name -> path mapping)"
    )


class ProjectsConfig(BaseModel):
    """
    Root configuration model for projects.yaml.

    Example:
        projects:
          NeuroVEP:
            context: ../custom/projects/NeuroVEP_context.md
            repos:
              - url: git@github.com:user/neurovep_analysis.git
                path: repos/neurovep_analysis
            data_mounts:
              - type: bind
                source: /Users/user/Dropbox/NeuroVEP
                target: data
                read_only: false
            commands:
              analyze_vep: ../custom/projects/commands/analyze_vep.md
    """

    projects: Dict[str, ProjectSpec] = Field(
        ...,
        description="Dictionary of project name to ProjectSpec"
    )
