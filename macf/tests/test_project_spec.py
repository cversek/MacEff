"""
Pragmatic tests for project_spec.py Pydantic models.

Tests focus on core validation: valid YAML parsing, required field enforcement,
type validation, and default values. Does NOT test every permutation.
"""

import pytest
from pydantic import ValidationError

from macf.models.project_spec import (
    RepoMount,
    DataMount,
    ProjectSpec,
    ProjectsConfig,
)


def test_repo_mount_valid():
    """Valid RepoMount with required fields."""
    repo = RepoMount(
        url="git@github.com:user/neurovep_analysis.git",
        path="repos/neurovep_analysis"
    )

    assert repo.url == "git@github.com:user/neurovep_analysis.git"
    assert repo.path == "repos/neurovep_analysis"


def test_repo_mount_missing_required_fields():
    """RepoMount fails when required fields missing."""
    # Missing url
    with pytest.raises(ValidationError) as exc_info:
        RepoMount(path="repos/backend")
    assert "url" in str(exc_info.value)

    # Missing path
    with pytest.raises(ValidationError) as exc_info:
        RepoMount(url="git@github.com:user/repo.git")
    assert "path" in str(exc_info.value)


def test_data_mount_valid():
    """Valid DataMount with required fields."""
    mount = DataMount(
        type="bind",
        source="/Users/user/Dropbox/NeuroVEP",
        target="data"
    )

    assert mount.type == "bind"
    assert mount.source == "/Users/user/Dropbox/NeuroVEP"
    assert mount.target == "data"
    assert mount.read_only is False  # Default value


def test_data_mount_read_only_explicit():
    """DataMount supports explicit read_only flag."""
    mount = DataMount(
        type="bind",
        source="/data/readonly",
        target="data",
        read_only=True
    )

    assert mount.read_only is True


def test_project_spec_minimal():
    """Valid ProjectSpec with only required field."""
    project = ProjectSpec(
        context="../custom/projects/NeuroVEP_context.md"
    )

    assert project.context == "../custom/projects/NeuroVEP_context.md"
    assert project.repos == []  # Default empty list
    assert project.data_mounts == []  # Default empty list
    assert project.commands is None


def test_project_spec_full():
    """Valid ProjectSpec with all optional fields."""
    project = ProjectSpec(
        context="../custom/projects/NeuroVEP_context.md",
        repos=[
            RepoMount(
                url="git@github.com:user/neurovep_analysis.git",
                path="repos/neurovep_analysis"
            ),
            RepoMount(
                url="git@github.com:user/neurovep_pipeline.git",
                path="repos/neurovep_pipeline"
            )
        ],
        data_mounts=[
            DataMount(
                type="bind",
                source="/Users/user/Dropbox/NeuroVEP",
                target="data",
                read_only=False
            )
        ],
        commands={
            "analyze_vep": "../custom/projects/commands/analyze_vep.md",
            "run_pipeline": "../custom/projects/commands/run_pipeline.md"
        }
    )

    assert len(project.repos) == 2
    assert len(project.data_mounts) == 1
    assert "analyze_vep" in project.commands
    assert project.commands["run_pipeline"] == "../custom/projects/commands/run_pipeline.md"


def test_projects_config_valid():
    """Valid ProjectsConfig with multiple projects."""
    config = ProjectsConfig(
        projects={
            "NeuroVEP": ProjectSpec(
                context="../custom/projects/NeuroVEP_context.md",
                repos=[
                    RepoMount(
                        url="git@github.com:user/neurovep_analysis.git",
                        path="repos/neurovep_analysis"
                    )
                ]
            ),
            "Research": ProjectSpec(
                context="../custom/projects/Research_context.md"
            )
        }
    )

    assert "NeuroVEP" in config.projects
    assert "Research" in config.projects
    assert len(config.projects["NeuroVEP"].repos) == 1
    assert len(config.projects["Research"].repos) == 0


def test_projects_config_missing_required_section():
    """ProjectsConfig fails when projects section missing."""
    with pytest.raises(ValidationError) as exc_info:
        ProjectsConfig()

    error = exc_info.value
    assert "projects" in str(error)


def test_project_spec_missing_context():
    """ProjectSpec fails when required context field missing."""
    with pytest.raises(ValidationError) as exc_info:
        ProjectSpec(
            repos=[
                RepoMount(
                    url="git@github.com:user/repo.git",
                    path="repos/backend"
                )
            ]
        )

    error = exc_info.value
    assert "context" in str(error)
