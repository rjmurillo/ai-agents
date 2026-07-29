"""Tests for validate_workflows.py security validations."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

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

    def test_flags_env_expressions(self, tmp_path: Path):
        """${{ env.FOO }} in run blocks is unsafe: any author can bind it.

        Previously asserted safe. That let a workflow bind `inputs.*` into
        `env:` and interpolate it back into `run:` to launder the taint. See
        TestEnvIsNotALaunderingHop.
        """
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
        assert len(validator.errors) == 1
        assert "env.MY_VAR" in validator.errors[0]

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

    def test_allows_matrix_and_rejects_inputs(self, tmp_path: Path):
        """${{ matrix.os }} is safe. ${{ inputs.version }} is not (issue #3664).

        A `workflow_dispatch` input is free text chosen by whoever dispatches
        the run, and a `workflow_call` input is only as safe as the callers,
        which this validator cannot see. Both spell `inputs.`, so both stay
        unsafe and must be bound through `env:`.
        """
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
        assert len(validator.errors) == 1
        assert "inputs.version" in validator.errors[0]

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


class TestDuplicateKeyRejection:
    """yaml.safe_load keeps the last duplicate silently; GitHub rejects the file."""

    def _write(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "wf.yml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_duplicate_top_level_key_is_a_syntax_error(self, tmp_path: Path):
        path = self._write(
            tmp_path,
            "name: X\non: [push]\n"
            "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps: []\n"
            "jobs:\n  b:\n    runs-on: ubuntu-latest\n    steps: []\n",
        )
        validator = WorkflowValidator(tmp_path)
        assert validator.validate_yaml_syntax(path) is False
        assert "duplicate key" in validator.errors[0]

    def test_duplicate_nested_key_is_a_syntax_error(self, tmp_path: Path):
        path = self._write(
            tmp_path,
            "name: X\non: [push]\njobs:\n  a:\n"
            "    runs-on: ubuntu-latest\n    runs-on: windows-latest\n    steps: []\n",
        )
        validator = WorkflowValidator(tmp_path)
        assert validator.validate_yaml_syntax(path) is False

    def test_a_clean_workflow_still_parses(self, tmp_path: Path):
        path = self._write(
            tmp_path,
            "name: X\non: [push]\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps: []\n",
        )
        validator = WorkflowValidator(tmp_path)
        assert validator.validate_yaml_syntax(path) is True
        assert validator.errors == []

    def test_repeated_keys_in_sibling_mappings_are_not_duplicates(self, tmp_path: Path):
        """Two jobs may both carry runs-on. Only same-mapping repeats are errors."""
        path = self._write(
            tmp_path,
            "name: X\non: [push]\njobs:\n"
            "  a:\n    runs-on: ubuntu-latest\n    steps: []\n"
            "  b:\n    runs-on: ubuntu-latest\n    steps: []\n",
        )
        validator = WorkflowValidator(tmp_path)
        assert validator.validate_yaml_syntax(path) is True


class TestJobsAreRunnable:
    """A job with neither runs-on nor uses is accepted by YAML and rejected by GitHub."""

    def test_job_without_runs_on_is_an_error(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        content = {"name": "X", "on": ["push"], "jobs": {"a": {"steps": []}}}
        validator.validate_workflow_structure(tmp_path / "wf.yml", content)
        assert any("no 'runs-on' value and no 'uses' value" in e for e in validator.errors)

    def test_an_empty_runs_on_value_is_an_error(self, tmp_path: Path):
        """A bare `runs-on:` parses as None and GitHub rejects it at dispatch.

        Testing key presence let this through, so the typo surfaced as a red
        run rather than a red check.
        """
        validator = WorkflowValidator(tmp_path)
        content = {"name": "X", "on": ["push"], "jobs": {"a": {"runs-on": None, "steps": []}}}
        validator.validate_workflow_structure(tmp_path / "wf.yml", content)
        assert any("no 'runs-on' value" in e for e in validator.errors)

    def test_an_empty_matrix_label_list_is_an_error(self, tmp_path: Path):
        """`runs-on: []` is the list-shaped spelling of the same typo."""
        validator = WorkflowValidator(tmp_path)
        content = {"name": "X", "on": ["push"], "jobs": {"a": {"runs-on": [], "steps": []}}}
        validator.validate_workflow_structure(tmp_path / "wf.yml", content)
        assert any("no 'runs-on' value" in e for e in validator.errors)

    def test_a_matrix_label_list_is_runnable(self, tmp_path: Path):
        """Guard the guard: a populated list must not trip the emptiness check."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "name": "X",
            "on": ["push"],
            "jobs": {"a": {"runs-on": ["self-hosted", "linux"], "steps": []}},
        }
        validator.validate_workflow_structure(tmp_path / "wf.yml", content)
        assert validator.errors == []

    def test_reusable_workflow_job_needs_no_runs_on(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        content = {
            "name": "X",
            "on": ["push"],
            "jobs": {"a": {"uses": "o/r/.github/workflows/w.yml@" + "a" * 40}},
        }
        validator.validate_workflow_structure(tmp_path / "wf.yml", content)
        assert validator.errors == []

    def test_non_mapping_job_is_an_error(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        content = {"name": "X", "on": ["push"], "jobs": {"a": "oops"}}
        validator.validate_workflow_structure(tmp_path / "wf.yml", content)
        assert any("must be a mapping" in e for e in validator.errors)

    def test_well_formed_job_produces_no_error(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        content = {
            "name": "X",
            "on": ["push"],
            "jobs": {"a": {"runs-on": "ubuntu-latest", "steps": []}},
        }
        validator.validate_workflow_structure(tmp_path / "wf.yml", content)
        assert validator.errors == []


class TestReusableWorkflowPinning:
    """A job-level `uses` carries the same supply-chain risk as a step-level one."""

    def test_unpinned_reusable_workflow_is_an_error(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        content = {"jobs": {"a": {"uses": "octo/repo/.github/workflows/w.yml@main"}}}
        validator.validate_action_pinning(tmp_path / "wf.yml", content)
        assert len(validator.errors) == 1
        assert "must use SHA pinning" in validator.errors[0]
        assert "Job 'a'" in validator.errors[0]

    def test_pinned_reusable_workflow_passes(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        sha = "b" * 40
        content = {"jobs": {"a": {"uses": f"octo/repo/.github/workflows/w.yml@{sha}"}}}
        validator.validate_action_pinning(tmp_path / "wf.yml", content)
        assert validator.errors == []

    def test_local_reusable_workflow_is_exempt(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        content = {"jobs": {"a": {"uses": "./.github/workflows/local.yml"}}}
        validator.validate_action_pinning(tmp_path / "wf.yml", content)
        assert validator.errors == []

    def test_step_level_pinning_still_reports_the_step_number(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "a": {
                    "runs-on": "ubuntu-latest",
                    "steps": [{"run": "echo"}, {"uses": "actions/checkout@v4"}],
                }
            }
        }
        validator.validate_action_pinning(tmp_path / "wf.yml", content)
        assert len(validator.errors) == 1
        assert "step 2" in validator.errors[0]

    def test_a_non_string_uses_is_an_error_not_a_crash(self, tmp_path: Path):
        """A workflow typo must not abort the pass over every other file.

        ``uses`` comes straight from ``yaml.safe_load``, so a bare ``uses:``
        is ``None`` and ``uses: 1.2`` is a float. Both used to raise
        ``AttributeError`` out of ``_check_pinned``.
        """
        validator = WorkflowValidator(tmp_path)
        content = {"jobs": {"a": {"uses": None}}}
        validator.validate_action_pinning(tmp_path / "wf.yml", content)
        assert len(validator.errors) == 1
        assert "must be a string" in validator.errors[0]
        assert "NoneType" in validator.errors[0]

    def test_a_non_string_uses_does_not_stop_later_findings(self, tmp_path: Path):
        """The whole point of not raising: keep reporting the rest."""
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "a": {
                    "runs-on": "ubuntu-latest",
                    "steps": [{"uses": 42}, {"uses": "actions/checkout@v4"}],
                }
            }
        }
        validator.validate_action_pinning(tmp_path / "wf.yml", content)
        assert len(validator.errors) == 2
        assert "must be a string" in validator.errors[0]
        assert "int" in validator.errors[0]
        assert "SHA pinning" in validator.errors[1]


class TestMalformedJobsDoesNotAbortThePass:
    """A wrong-typed `jobs` must be reported, not raised.

    ``validate_workflow_structure`` already reports it. The later passes used
    to call ``.items()`` on whatever was there, so one malformed file took down
    validation for every remaining file in the repo and the run reported
    nothing about them.
    """

    def test_list_shaped_jobs_does_not_raise_in_action_pinning(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        content = {"jobs": [{"a": {"runs-on": "ubuntu-latest"}}]}
        validator.validate_action_pinning(tmp_path / "wf.yml", content)
        assert validator.errors == []

    def test_string_shaped_jobs_does_not_raise_in_action_pinning(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        validator.validate_action_pinning(tmp_path / "wf.yml", {"jobs": "oops"})
        assert validator.errors == []

    def test_structure_still_reports_the_wrong_type_exactly_once(self, tmp_path: Path):
        """The skip above must not silence the one place that owns the message."""
        validator = WorkflowValidator(tmp_path)
        content = {"name": "X", "on": ["push"], "jobs": "oops"}
        validator.validate_workflow_structure(tmp_path / "wf.yml", content)
        validator.validate_action_pinning(tmp_path / "wf.yml", content)
        assert len([e for e in validator.errors if "must be a dictionary" in e]) == 1


class TestLoaderIsSafe:
    """ADR-006 forbids calling yaml.load at all, SafeLoader subclass or not."""

    def test_the_module_never_names_yaml_load(self):
        source = Path(_mod.__file__).read_text(encoding="utf-8")
        assert "yaml.load(" not in source, (
            "ADR-006 line 293: consumers MUST never call yaml.load(). A later "
            "edit that drops the Loader argument reaches the unsafe default."
        )

    def test_a_python_object_tag_is_rejected(self, tmp_path: Path):
        """The property the ban protects, asserted behaviourally."""
        wf = tmp_path / "wf.yml"
        wf.write_text("name: !!python/object/apply:os.system ['echo pwned']\n", encoding="utf-8")
        validator = WorkflowValidator(tmp_path)
        assert validator.validate_yaml_syntax(wf) is False
        assert any("YAML syntax error" in e for e in validator.errors)

    def test_a_well_formed_workflow_still_parses(self, tmp_path: Path):
        """Guard the guard: the rejection above must not be blanket."""
        wf = tmp_path / "wf.yml"
        wf.write_text("name: X\non: [push]\njobs:\n  a:\n    runs-on: ubuntu-latest\n", "utf-8")
        validator = WorkflowValidator(tmp_path)
        assert validator.validate_yaml_syntax(wf) is True
        assert validator.errors == []


class TestSubprocessDecoding:
    """Captured child output must be decoded explicitly, not by locale default.

    On Windows an unset encoding makes subprocess decode as cp1252. Git prints
    UTF-8 (branch glyphs, non-ASCII paths), the reader thread dies mid-decode,
    and ``result.stdout`` silently comes back as None instead of raising. The
    caller then treats "no changed workflows" as a clean run.
    """

    _CAPTURING = "capture_output=True,"

    def _source(self) -> str:
        return Path(_mod.__file__).read_text(encoding="utf-8")

    def test_every_capture_pins_the_codec(self):
        source = self._source()
        assert source.count(self._CAPTURING) == source.count('encoding="utf-8",')

    def test_no_capture_relies_on_text_mode_alone(self):
        assert "text=True" not in self._source()

    def test_every_capture_tolerates_undecodable_bytes(self):
        source = self._source()
        assert source.count(self._CAPTURING) == source.count('errors="replace",')


def _run_step(expr: str) -> dict[str, object]:
    return {"run": f"echo {expr}"}


class TestExpressionInjectionAllowlist:
    """Unknown expression contexts default to unsafe (issue #3664).

    The previous blocklist enumerated dangerous contexts, so every context
    nobody had listed, `inputs.*` among them, defaulted to safe.
    """

    @staticmethod
    def _check(tmp_path: Path, steps: Sequence[object]) -> list[str]:
        validator = WorkflowValidator(tmp_path)
        content = {"jobs": {"a": {"runs-on": "ubuntu-latest", "steps": steps}}}
        validator.validate_expression_injection(tmp_path / "wf.yml", content)
        return validator.errors

    def test_workflow_dispatch_input_in_a_run_block_is_flagged(self, tmp_path: Path):
        errors = self._check(tmp_path, [_run_step("${{ inputs.days }}")])
        assert len(errors) == 1
        assert "inputs.days" in errors[0]
        assert "not a GitHub-generated value" in errors[0]

    def test_legacy_event_input_alias_is_flagged(self, tmp_path: Path):
        errors = self._check(tmp_path, [_run_step("${{ github.event.inputs.days }}")])
        assert len(errors) == 1

    def test_issue_title_stays_flagged(self, tmp_path: Path):
        """The contexts the old blocklist named must not regress."""
        errors = self._check(tmp_path, [_run_step("${{ github.event.issue.title }}")])
        assert len(errors) == 1

    def test_head_ref_stays_flagged(self, tmp_path: Path):
        errors = self._check(tmp_path, [_run_step("${{ github.head_ref }}")])
        assert len(errors) == 1

    def test_commit_message_stays_flagged(self, tmp_path: Path):
        errors = self._check(tmp_path, [_run_step("${{ github.event.commits[0].message }}")])
        assert len(errors) == 1

    def test_branch_name_contexts_are_not_admitted(self, tmp_path: Path):
        """A fork author picks the branch name, so ref shapes stay unsafe."""
        for expr in ("github.ref", "github.ref_name", "github.base_ref"):
            errors = self._check(tmp_path, [_run_step("${{ " + expr + " }}")])
            assert len(errors) == 1, expr

    def test_github_generated_values_are_not_flagged(self, tmp_path: Path):
        for expr in (
            "github.event_name",
            "github.repository",
            "github.run_id",
            "github.sha",
            "github.server_url",
            "github.actor",
            "github.event.issue.number",
            "github.event.pull_request.number",
        ):
            errors = self._check(tmp_path, [_run_step("${{ " + expr + " }}")])
            assert errors == [], expr

    def test_matrix_references_are_not_flagged(self, tmp_path: Path):
        """`env.` is not in this set: see TestEnvIsNotALaunderingHop."""
        for expr in ("matrix.language", "runner.os", "needs.build.outputs.x"):
            errors = self._check(tmp_path, [_run_step("${{ " + expr + " }}")])
            assert errors == [], expr

    def test_a_function_call_wrapping_a_context_is_flagged(self, tmp_path: Path):
        """The argument reaches the shell, so the wrapper does not launder it."""
        errors = self._check(tmp_path, [_run_step("${{ fromJSON(inputs.blob) }}")])
        assert len(errors) == 1

    def test_a_comparison_on_a_safe_head_is_still_safe(self, tmp_path: Path):
        errors = self._check(tmp_path, [_run_step("${{ github.event_name == 'push' }}")])
        assert errors == []

    def test_a_step_without_a_run_block_is_ignored(self, tmp_path: Path):
        errors = self._check(tmp_path, [{"uses": "actions/checkout@abc"}])
        assert errors == []

    def test_a_non_mapping_step_does_not_raise(self, tmp_path: Path):
        errors = self._check(tmp_path, ["not-a-mapping"])
        assert errors == []

    def test_a_non_list_steps_value_does_not_raise(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        content = {"jobs": {"a": {"runs-on": "ubuntu-latest", "steps": "oops"}}}
        validator.validate_expression_injection(tmp_path / "wf.yml", content)
        assert validator.errors == []

    def test_a_non_mapping_jobs_value_does_not_raise(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        validator.validate_expression_injection(tmp_path / "wf.yml", {"jobs": ["a"]})
        assert validator.errors == []

    def test_the_remediation_names_the_env_binding(self, tmp_path: Path):
        errors = self._check(tmp_path, [_run_step("${{ inputs.days }}")])
        assert "env:" in errors[0]


class TestExpressionInjectionTaintPropagation:
    """Binding a tainted value through env: at the producer does not sanitize it."""

    @staticmethod
    def _check(tmp_path: Path, steps: Sequence[object]) -> list[str]:
        validator = WorkflowValidator(tmp_path)
        content = {"jobs": {"a": {"runs-on": "ubuntu-latest", "steps": steps}}}
        validator.validate_expression_injection(tmp_path / "wf.yml", content)
        return validator.errors

    _PRODUCER = {
        "id": "period",
        "env": {"INPUT_DAYS": "${{ inputs.days }}"},
        "run": 'printf "days=%s\\n" "$INPUT_DAYS" >> "$GITHUB_OUTPUT"',
    }

    def test_a_tainted_step_output_is_flagged_downstream(self, tmp_path: Path):
        errors = self._check(
            tmp_path, [self._PRODUCER, _run_step("${{ steps.period.outputs.days }}")]
        )
        assert len(errors) == 1
        assert "carries the same taint" in errors[0]
        assert "'period'" in errors[0]

    def test_an_untainted_step_output_is_not_flagged(self, tmp_path: Path):
        producer = {
            "id": "calc",
            "run": 'printf "n=%s\\n" "$(date +%s)" >> "$GITHUB_OUTPUT"',
        }
        errors = self._check(tmp_path, [producer, _run_step("${{ steps.calc.outputs.n }}")])
        assert errors == []

    def test_a_producer_that_writes_no_output_does_not_taint(self, tmp_path: Path):
        producer = {"id": "noop", "env": {"D": "${{ inputs.days }}"}, "run": 'echo "$D"'}
        errors = self._check(tmp_path, [producer, _run_step("${{ steps.noop.outputs.x }}")])
        assert errors == []

    def test_taint_does_not_reach_backwards(self, tmp_path: Path):
        """A step before the producer cannot consume its output."""
        errors = self._check(
            tmp_path, [_run_step("${{ steps.period.outputs.days }}"), self._PRODUCER]
        )
        assert errors == []

    def test_taint_does_not_cross_jobs(self, tmp_path: Path):
        validator = WorkflowValidator(tmp_path)
        content = {
            "jobs": {
                "a": {"runs-on": "ubuntu-latest", "steps": [self._PRODUCER]},
                "b": {
                    "runs-on": "ubuntu-latest",
                    "steps": [_run_step("${{ steps.period.outputs.days }}")],
                },
            }
        }
        validator.validate_expression_injection(tmp_path / "wf.yml", content)
        assert validator.errors == []

    def test_a_raw_interpolation_in_the_producer_also_taints(self, tmp_path: Path):
        producer = {
            "id": "period",
            "run": 'echo "days=${{ inputs.days }}" >> "$GITHUB_OUTPUT"',
        }
        errors = self._check(
            tmp_path, [producer, _run_step("${{ steps.period.outputs.days }}")]
        )
        assert len(errors) == 2
        assert any("carries the same taint" in e for e in errors)

    def test_a_producer_without_an_id_cannot_taint(self, tmp_path: Path):
        producer = {
            "env": {"D": "${{ inputs.days }}"},
            "run": 'printf "d=%s\\n" "$D" >> "$GITHUB_OUTPUT"',
        }
        errors = self._check(tmp_path, [producer, _run_step("${{ steps.x.outputs.d }}")])
        assert errors == []

    def test_a_non_string_env_value_does_not_raise(self, tmp_path: Path):
        producer = {"id": "p", "env": {"N": 7}, "run": 'echo x >> "$GITHUB_OUTPUT"'}
        errors = self._check(tmp_path, [producer, _run_step("${{ steps.p.outputs.d }}")])
        assert errors == []


class TestNameTruncationAtUnquotedHash:
    """An unquoted ` #` ends a plain YAML scalar and GitHub reports nothing (#3652)."""

    @staticmethod
    def _check(tmp_path: Path, body: str) -> list[str]:
        path = tmp_path / "wf.yml"
        path.write_text(body, encoding="utf-8")
        validator = WorkflowValidator(tmp_path)
        validator.validate_name_truncation(path)
        return validator.errors

    def test_a_step_name_with_an_issue_reference_is_flagged(self, tmp_path: Path):
        errors = self._check(tmp_path, "      - name: Check parity (issue #2222)\n")
        assert len(errors) == 1
        assert "Check parity (issue" in errors[0]
        assert "#2222)" in errors[0]

    def test_the_message_shows_the_quoted_repair(self, tmp_path: Path):
        errors = self._check(tmp_path, "      - name: Fix for issue #10\n")
        assert 'name: "Fix for issue #10"' in errors[0]

    def test_a_name_wrapping_an_expression_is_flagged(self, tmp_path: Path):
        errors = self._check(tmp_path, "      - name: PR #${{ matrix.number }}\n")
        assert len(errors) == 1

    def test_a_double_quoted_name_is_accepted(self, tmp_path: Path):
        errors = self._check(tmp_path, '      - name: "Check parity (issue #2222)"\n')
        assert errors == []

    def test_a_single_quoted_name_is_accepted(self, tmp_path: Path):
        errors = self._check(tmp_path, "      - name: 'Check parity (issue #2222)'\n")
        assert errors == []

    def test_a_name_without_a_hash_is_accepted(self, tmp_path: Path):
        errors = self._check(tmp_path, "      - name: Check parity\n")
        assert errors == []

    def test_a_hash_with_no_leading_space_is_not_a_comment(self, tmp_path: Path):
        """YAML only starts a comment at a `#` preceded by whitespace."""
        errors = self._check(tmp_path, "      - name: issue#2222 parity\n")
        assert errors == []

    def test_a_whole_line_comment_is_not_a_name(self, tmp_path: Path):
        errors = self._check(tmp_path, "      # name: Check parity (issue #2222)\n")
        assert errors == []

    def test_a_description_field_is_covered(self, tmp_path: Path):
        errors = self._check(tmp_path, "        description: Days to scan #7\n")
        assert len(errors) == 1

    def test_a_block_scalar_header_is_not_flagged(self, tmp_path: Path):
        errors = self._check(tmp_path, "      - name: |\n          multi #line\n")
        assert errors == []

    def test_the_report_carries_the_line_number(self, tmp_path: Path):
        errors = self._check(
            tmp_path, "jobs:\n  a:\n    steps:\n      - name: X #1\n"
        )
        assert len(errors) == 1
        assert ":4:" in errors[0]

    def test_every_offender_on_the_file_is_reported(self, tmp_path: Path):
        errors = self._check(
            tmp_path, "      - name: A #1\n      - name: B #2\n      - name: C\n"
        )
        assert len(errors) == 2

    def test_the_live_workflow_tree_is_clean(self):
        """Regression pin: the ten repaired names must not come back."""
        repo_root = Path(__file__).resolve().parents[1]
        workflows = repo_root / ".github" / "workflows"
        validator = WorkflowValidator(repo_root)
        for path in sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml")):
            validator.validate_name_truncation(path)
        assert validator.errors == []


class TestLiveWorkflowTreeHasNoInjection:
    """Regression pin for the two chains repaired in issue #3664."""

    @staticmethod
    def _scan() -> list[str]:
        repo_root = Path(__file__).resolve().parents[1]
        workflows = repo_root / ".github" / "workflows"
        validator = WorkflowValidator(repo_root)
        import yaml

        paths = sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml"))
        for path in paths:
            content = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                validator.validate_expression_injection(path, content)
        return validator.errors

    def test_no_workflow_interpolates_an_unsafe_expression(self):
        assert self._scan() == []

    def test_the_scan_actually_visited_the_repaired_workflows(self):
        """Guard against the pin passing because nothing was read."""
        import re

        repo_root = Path(__file__).resolve().parents[1]
        for name in ("agent-metrics.yml", "copilot-context-synthesis.yml"):
            path = repo_root / ".github" / "workflows" / name
            assert path.is_file(), name
            body = path.read_text(encoding="utf-8")
            # The reference may sit anywhere inside the expression, including
            # behind a parenthesised `&&`/`||` source-selection guard.
            assert re.search(r"\$\{\{[^}]*inputs\.", body), (
                f"{name} no longer references a dispatch input"
            )
            assert "echo \"days=${{ inputs.days }}\"" not in body


class TestSafeHeadCommentMatchesBehavior:
    """Pin what `_classify_expression` actually permits.

    The comment above `_SAFE_EXPRESSION_HEADS` names two deliberate absences.
    One of them did not hold. `secrets.*` is absent from the safe-head set, but
    `_DERIVED_EXPRESSION_PREFIXES` eleven lines above carries `secrets.`, and
    that arm is checked too, so a secret interpolated into a `run:` block is
    waved through. A reader auditing the check from the comment alone would
    have built the opposite model.

    These tests pin both halves so the comment cannot drift from the code
    again without a red test.
    """

    @staticmethod
    def _classify(expression: str) -> str | None:
        return WorkflowValidator(Path("/nonexistent"))._classify_expression(expression, set())

    @pytest.mark.parametrize(
        "expression",
        ["github.ref", "github.ref_name", "github.head_ref", "github.base_ref"],
    )
    def test_branch_name_contexts_are_flagged(self, expression: str) -> None:
        """The comment's first claim: a fork author picks these, so they are unsafe."""
        assert self._classify(expression) is not None

    @pytest.mark.parametrize(
        "expression", ["secrets.MY_TOKEN", "secrets.GITHUB_TOKEN", "secrets.NPM_TOKEN"]
    )
    def test_secrets_are_permitted_by_this_check(self, expression: str) -> None:
        """The comment's second claim, corrected: `secrets.` is a derived prefix.

        Setting a secret needs repository admin, which already implies workflow
        write, so this check does not treat a secret value as attacker-supplied
        text. Flagging it instead would be a policy change across every
        workflow that passes a token to a `run:` block, not a comment fix.
        """
        assert self._classify(expression) is None

    @pytest.mark.parametrize(
        "expression", ["vars.FOO", "needs.a.outputs.b", "matrix.x", "runner.os"]
    )
    def test_the_other_derived_prefixes_are_permitted_too(self, expression: str) -> None:
        """Control: `secrets.` is permitted by the same arm as its siblings.

        `env.` was a sibling until it was found to launder taint. It is now
        flagged; TestEnvIsNotALaunderingHop owns that case.
        """
        assert self._classify(expression) is None

    @pytest.mark.parametrize(
        "expression", ["inputs.days", "github.event.issue.title", "github.event.pull_request.body"]
    )
    def test_attacker_supplied_text_is_still_flagged(self, expression: str) -> None:
        """Negative control: the check has not been widened into a rubber stamp."""
        assert self._classify(expression) is not None

    def test_secrets_prefix_is_the_reason_not_the_safe_head_set(self) -> None:
        """Edge: name the mechanism, so a fix to one list cannot silently pass.

        If someone removes `secrets.` from the derived prefixes, this test
        fails even though `test_secrets_are_permitted_by_this_check` would also
        fail; the pair localizes which list moved.
        """
        assert "secrets.MY_TOKEN" not in WorkflowValidator._SAFE_EXPRESSION_HEADS
        assert "secrets." in WorkflowValidator._DERIVED_EXPRESSION_PREFIXES


class TestEnvIsNotALaunderingHop:
    """`${{ env.X }}` in a `run:` block is the same injection as the source.

    `env.` sat in `_DERIVED_EXPRESSION_PREFIXES`, so the classifier called it
    a GitHub-generated value. Nothing generates it: a workflow author binds it,
    and the binding may read `inputs.*`. That made a two-line bypass of the
    whole check. Bind the tainted text into `env:`, interpolate the env context
    back into `run:`, and the direct form's error disappears while the shell
    still receives attacker text verbatim.

    `env.` differs from its former siblings in who writes it. `secrets.` and
    `vars.` need repository admin, which already implies workflow write, so
    this check does not treat them as attacker-supplied. Any workflow author
    writes `env:`.
    """

    @staticmethod
    def _check(tmp_path: Path, steps: Sequence[object], job_env: object = None) -> list[str]:
        job: dict[str, object] = {"runs-on": "ubuntu-latest", "steps": steps}
        if job_env is not None:
            job["env"] = job_env
        validator = WorkflowValidator(tmp_path)
        validator.validate_expression_injection(tmp_path / "wf.yml", {"jobs": {"a": job}})
        return validator.errors

    def test_the_bypass_is_flagged(self, tmp_path: Path) -> None:
        """Positive: the exact shape that laundered the taint now errors."""
        errors = self._check(
            tmp_path,
            [_run_step("${{ env.TITLE }}")],
            job_env={"TITLE": "${{ inputs.title }}"},
        )
        assert len(errors) == 1
        assert "env.TITLE" in errors[0]
        assert "not a GitHub-generated value" in errors[0]

    def test_the_bypass_and_its_source_are_flagged_alike(self, tmp_path: Path) -> None:
        """Positive: laundering through `env:` buys nothing over the direct form.

        Both spellings reach the shell as substituted text before it runs, so
        one error each is the only self-consistent answer.
        """
        direct = self._check(tmp_path, [_run_step("${{ inputs.title }}")])
        laundered = self._check(
            tmp_path,
            [_run_step("${{ env.TITLE }}")],
            job_env={"TITLE": "${{ inputs.title }}"},
        )
        assert len(direct) == len(laundered) == 1

    def test_the_documented_remediation_still_passes(self, tmp_path: Path) -> None:
        """Negative: the fix does not outlaw the cure it prescribes.

        The error text tells the author to bind through `env:` and read the
        quoted shell variable. `"$TITLE"` is a shell expansion, not a GitHub
        expression, so no `${{ }}` remains for the check to see.
        """
        errors = self._check(
            tmp_path,
            [{"env": {"TITLE": "${{ inputs.title }}"}, "run": 'echo "$TITLE"'}],
        )
        assert errors == []

    @pytest.mark.parametrize("expression", ["secrets.TOKEN", "vars.REGISTRY"])
    def test_admin_written_contexts_are_untouched(
        self, tmp_path: Path, expression: str
    ) -> None:
        """Negative control: this narrows one prefix, it does not tighten policy.

        Writing either needs repository admin, so neither is attacker-supplied
        text by the same argument that already exempts `secrets.`.
        """
        assert self._check(tmp_path, [_run_step("${{ " + expression + " }}")]) == []

    @pytest.mark.parametrize("expression", ["needs.a.outputs.b", "matrix.x", "runner.os"])
    def test_the_remaining_derived_prefixes_are_untouched(
        self, tmp_path: Path, expression: str
    ) -> None:
        """Negative control: only `env.` moved."""
        assert self._check(tmp_path, [_run_step("${{ " + expression + " }}")]) == []

    def test_env_is_gone_from_the_derived_prefixes(self) -> None:
        """Edge: name the mechanism so a list edit cannot silently reopen it.

        Without this, restoring `env.` to the tuple would be caught only by
        the behavioral tests above, and a reader of the tuple alone would see
        no reason it is absent.
        """
        assert "env." not in WorkflowValidator._DERIVED_EXPRESSION_PREFIXES
        assert "vars." in WorkflowValidator._DERIVED_EXPRESSION_PREFIXES

    def test_an_env_value_reading_env_does_not_itself_error(self, tmp_path: Path) -> None:
        """Edge: the `env:` scan feeds taint tracking, it does not report.

        Three repository workflows write `PR_NUMBER: ${{ env.PR_NUMBER }}` at
        step level. Narrowing the prefix marks those steps as reading an
        unsafe value, which matters only if the step also publishes to
        `$GITHUB_OUTPUT`. On its own it must stay silent.
        """
        errors = self._check(
            tmp_path,
            [{"env": {"PR_NUMBER": "${{ env.PR_NUMBER }}"}, "run": 'echo "$PR_NUMBER"'}],
        )
        assert errors == []

    def test_an_env_value_reading_env_taints_a_publishing_step(self, tmp_path: Path) -> None:
        """Edge: and when the step does publish, the taint propagates one hop."""
        errors = self._check(
            tmp_path,
            [
                {
                    "id": "p",
                    "env": {"T": "${{ env.TITLE }}"},
                    "run": 'printf "t=%s\\n" "$T" >> "$GITHUB_OUTPUT"',
                },
                _run_step("${{ steps.p.outputs.t }}"),
            ],
        )
        assert len(errors) == 1
        assert "steps.p.outputs.t" in errors[0]
