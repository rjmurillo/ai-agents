"""Tests for validate_workflows.py security validations."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("validate_workflows")
WorkflowValidator = _mod.WorkflowValidator


class TestValidatePermissions:
    """Tests for permissions validation (security requirement)."""

    def test_error_when_no_permissions_anywhere(self, tmp_path: Path):
        """Workflows with no permissions declaration produce an error."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "name": "test",
            "jobs": {"build": {"runs-on": "ubuntu-latest", "steps": []}},
        }
        validator.validate_permissions(tmp_path / "test.yml", content)
        assert len(validator.errors) == 1
        assert "Missing 'permissions'" in validator.errors[0]

    def test_no_error_with_top_level_permissions(self, tmp_path: Path):
        """Top-level permissions declaration is sufficient."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "name": "test",
            "permissions": {"contents": "read"},
            "jobs": {"build": {"runs-on": "ubuntu-latest", "steps": []}},
        }
        validator.validate_permissions(tmp_path / "test.yml", content)
        assert len(validator.errors) == 0

    def test_no_error_with_all_jobs_having_permissions(self, tmp_path: Path):
        """Per-job permissions on every job is also acceptable."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "name": "test",
            "jobs": {
                "build": {
                    "runs-on": "ubuntu-latest",
                    "permissions": {"contents": "read"},
                    "steps": [],
                },
                "deploy": {
                    "runs-on": "ubuntu-latest",
                    "permissions": {"contents": "write"},
                    "steps": [],
                },
            },
        }
        validator.validate_permissions(tmp_path / "test.yml", content)
        assert len(validator.errors) == 0

    def test_error_when_some_jobs_missing_permissions(self, tmp_path: Path):
        """If no top-level perms and some jobs lack them, report error."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "name": "test",
            "jobs": {
                "build": {
                    "runs-on": "ubuntu-latest",
                    "permissions": {"contents": "read"},
                    "steps": [],
                },
                "deploy": {
                    "runs-on": "ubuntu-latest",
                    "steps": [],
                },
            },
        }
        validator.validate_permissions(tmp_path / "test.yml", content)
        assert len(validator.errors) == 1


class TestExpressionInjection:
    """Tests for expression injection detection."""

    def test_detects_github_event_in_run(self, tmp_path: Path):
        """${{ github.event.* }} in run blocks is flagged."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": 'echo "${{ github.event.issue.title }}"',
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 1
        assert "Expression injection" in validator.errors[0]

    def test_allows_safe_env_expressions(self, tmp_path: Path):
        """${{ env.FOO }} in run blocks is safe."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": 'echo "${{ env.MY_VAR }}"',
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 0

    def test_allows_secrets(self, tmp_path: Path):
        """${{ secrets.TOKEN }} in run blocks is safe."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": 'curl -H "Authorization: ${{ secrets.TOKEN }}"',
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 0

    def test_allows_matrix_and_inputs(self, tmp_path: Path):
        """${{ matrix.os }} and ${{ inputs.version }} are safe."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": "echo ${{ matrix.os }} ${{ inputs.version }}",
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 0

    def test_allows_steps_outputs(self, tmp_path: Path):
        """${{ steps.id.outputs.result }} is safe."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": "echo ${{ steps.check.outputs.result }}",
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 0

    def test_detects_github_head_ref(self, tmp_path: Path):
        """${{ github.head_ref }} is attacker-controlled."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": "git checkout ${{ github.head_ref }}",
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 1

    def test_no_error_on_steps_without_run(self, tmp_path: Path):
        """Steps without run blocks are skipped."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "uses": "actions/checkout@abc123",
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 0

    def test_allows_hashfiles(self, tmp_path: Path):
        """${{ hashFiles('...') }} is safe."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": "echo ${{ hashFiles('**/package-lock.json') }}",
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 0

    def test_allows_github_repository(self, tmp_path: Path):
        """${{ github.repository }} is repo-controlled, not attacker-controlled."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": "echo ${{ github.repository }}",
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 0

    def test_allows_github_event_name(self, tmp_path: Path):
        """${{ github.event_name }} is repo-controlled."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": "echo ${{ github.event_name }}",
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 0

    def test_detects_pr_title_injection(self, tmp_path: Path):
        """${{ github.event.pull_request.title }} is attacker-controlled."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": 'echo "${{ github.event.pull_request.title }}"',
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 1

    def test_detects_comment_body_injection(self, tmp_path: Path):
        """${{ github.event.comment.body }} is attacker-controlled."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "run": 'echo "${{ github.event.comment.body }}"',
                        }
                    ]
                }
            }
        }
        validator.validate_expression_injection(tmp_path / "t.yml", content)
        assert len(validator.errors) == 1
