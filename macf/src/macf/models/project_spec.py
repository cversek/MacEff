"""
Pydantic models for projects.yaml configuration validation.

Models correspond to the YAML structure documented in:
docs/arch_v0.3_named_agents/05_implementation_guide.md (lines 127+)
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class RepoMount(BaseModel):
    """Git repository mount configuration."""

    url: str = Field(
        ...,
        description="Git repository URL (e.g., git@github.com:user/repo.git)"
    )

    name: Optional[str] = Field(
        default=None,
        description="Repository name (optional, defaults to name extracted from URL)"
    )

    worktree: bool = Field(
        default=True,
        description="Create git worktree (True) or plain clone (False). Worktrees enable multi-agent collaboration without race conditions."
    )

    default_branch: str = Field(
        default="main",
        description="Default branch for worktree creation (e.g., 'main', 'master', 'develop')"
    )

    @model_validator(mode='after')
    def extract_name_from_url(self):
        """Extract repository name from URL if name not provided."""
        if self.name is not None:
            return self

        # Extract from URL
        url = self.url
        if not url:
            return self

        # Handle git@github.com:user/repo.git or https://github.com/user/repo.git
        if url.endswith('.git'):
            url = url[:-4]

        # Extract last component (repo name)
        # Handle both git@github.com:user/repo and https://github.com/user/repo
        if ':' in url and '@' in url:
            # SSH format: git@github.com:user/repo
            self.name = url.split(':')[-1].split('/')[-1]
        else:
            # HTTPS format: https://github.com/user/repo
            self.name = url.rstrip('/').split('/')[-1]
        return self


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
                name: neurovep_analysis  # Optional, defaults to 'neurovep_analysis' from URL
                worktree: true  # Default, creates git worktree
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
