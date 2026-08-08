"""Workflow, vendor, and dependency validation tests for pre-PR checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.pre_pr import validate_workflow_yaml


class TestValidateWorkflowYaml:
    """Workflow validation raises the shellcheck severity floor to warning (#2374)."""

    def test_returns_true_when_actionlint_missing(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        with patch("checks_tooling.shutil.which", return_value=None):
            assert validate_workflow_yaml(tmp_path) is True

    def test_returns_true_when_no_workflow_dir(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        with patch("checks_tooling.shutil.which", return_value="actionlint"):
            assert validate_workflow_yaml(tmp_path) is True

    def test_passes_shellcheck_severity_warning_env(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: ci\non: push\n")
        with patch("checks_tooling.shutil.which", return_value="actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                assert validate_workflow_yaml(tmp_path) is True

            env_kwarg = mock_run.call_args.kwargs["env"]
            assert "--severity=warning" in env_kwarg["SHELLCHECK_OPTS"]

    def test_preserves_existing_shellcheck_opts(self, tmp_path: Path) -> None:
        import os

        from scripts.validation.pre_pr import validate_workflow_yaml

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: ci\non: push\n")
        with patch.dict(os.environ, {"SHELLCHECK_OPTS": "--exclude=SC1091"}, clear=False):
            with patch(
                "checks_tooling.shutil.which", return_value="actionlint"
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_workflow_yaml(tmp_path) is True

                opts = mock_run.call_args.kwargs["env"]["SHELLCHECK_OPTS"]
                assert "--exclude=SC1091" in opts
                assert "--severity=warning" in opts

    def test_fails_when_actionlint_reports_warning(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_workflow_yaml

        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: ci\non: push\n")
        with patch("checks_tooling.shutil.which", return_value="actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (1, "ci.yml:1:1: SC2034 ... [shellcheck]", "")
                assert validate_workflow_yaml(tmp_path) is False


class TestValidateWorkflowYamlScope:
    """actionlint validates workflows only; composite action.yml files under
    .github/actions/ must never be passed to it (issue #2346)."""

    @staticmethod
    def _build_tree(root: Path) -> None:
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(
            "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps: []\n",
            encoding="utf-8",
        )
        actions = root / ".github" / "actions" / "composite"
        actions.mkdir(parents=True)
        # A composite action: actionlint would emit false errors if scanned.
        (actions / "action.yml").write_text(
            "name: composite\nruns:\n  using: composite\n  steps: []\n",
            encoding="utf-8",
        )

    def test_does_not_pass_composite_action_paths(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                assert validate_workflow_yaml(tmp_path) is True

        mock_run.assert_called_once()
        command = mock_run.call_args.args[0]
        assert command[0] == "actionlint"
        paths = command[1:]
        # No composite action path is ever handed to actionlint.
        assert all(".github/actions" not in p for p in paths)
        assert not any(p.endswith("action.yml") for p in paths)

    def test_passes_only_workflow_files(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch("checks_tooling._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                validate_workflow_yaml(tmp_path)

        command = mock_run.call_args.args[0]
        paths = command[1:]
        assert paths, "expected at least one workflow file to be scanned"
        workflows_prefix = str(tmp_path / ".github" / "workflows")
        assert all(p.startswith(workflows_prefix) for p in paths)

    def test_skips_when_actionlint_absent(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("checks_tooling.shutil.which", return_value=None):
            with patch("checks_tooling._run_subprocess") as mock_run:
                assert validate_workflow_yaml(tmp_path) is True
        mock_run.assert_not_called()


class TestWorkflowYamlTargets:
    """Unit tests for ``_workflow_yaml_targets``, the branch-scoping helper.

    Covers the scoping contract added for correctness-preserving scoping:
    changed subset and composite-action exclusion. The base-ref/command-
    failure scoping contract itself (shared by every gate that calls
    ``_changed_paths_since_base``) is proven once in
    ``tests/validation_pre_pr/test_changed_paths_since_base.py``, not
    re-verified here. The missing-from-disk hard-failure contract (item 2,
    round 2 review) is proven generically, once, in
    ``tests/validation_pre_pr/test_filtered_targets.py``;
    ``test_missing_from_disk_raises`` below only locks in that THIS gate's
    predicate (``.github/workflows/*.yml|yaml``) reaches that shared path.
    """

    @pytest.mark.parametrize(
        ("diff_stdout", "on_disk", "expected"),
        [
            (
                "README.md\0.github/workflows/ci.yml",
                ".github/workflows/ci.yml",
                [".github/workflows/ci.yml"],
            ),
            (".github/actions/composite/action.yml", ".github/actions/composite/action.yml", []),
        ],
        ids=["changed-subset-returned", "composite-action-excluded-2346"],
    )
    def test_filtering_contract(
        self,
        tmp_path: Path,
        diff_stdout: str,
        on_disk: str | None,
        expected: list[str],
    ) -> None:
        """Only ``.github/workflows/*.yml|yaml`` files qualify; a changed
        composite ``action.yml`` must never reach actionlint (#2346).

        ``diff_stdout`` is NUL-delimited (matching the ``-z`` flag the shared
        helper now always passes); ``mock_run.return_value`` applies
        uniformly to all four underlying git calls the helper makes, so the
        same changed-set surfaces via each of the four sources.
        """
        from checks_tooling import _workflow_yaml_targets

        if on_disk is not None:
            path = tmp_path / on_disk
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("stub\n", encoding="utf-8")
        with patch("checks_changed_paths._resolve_branch_base_ref", return_value="origin/main"):
            with patch("checks_changed_paths._run_subprocess") as mock_run:
                mock_run.return_value = (0, diff_stdout, "")
                with patch("checks_tooling._deleted_paths_since_base", return_value=[]):
                    assert _workflow_yaml_targets(tmp_path) == expected

    def test_missing_from_disk_raises(self, tmp_path: Path) -> None:
        """A path git reports as a changed workflow file (ACMR: Added,
        Copied, Modified, or Renamed -- never Deleted) but that is absent
        from the worktree must fail this gate loudly (item 2, round 2
        review), not be silently dropped and not fall back to validating
        every ``*.yml``/``*.yaml`` under ``.github/workflows/`` instead.
        """
        from checks_changed_paths import ChangedPathMissingError
        from checks_tooling import _workflow_yaml_targets

        with patch("checks_changed_paths._resolve_branch_base_ref", return_value="origin/main"):
            with patch("checks_changed_paths._run_subprocess") as mock_run:
                mock_run.return_value = (0, ".github/workflows/removed.yml", "")
                with patch("checks_tooling._deleted_paths_since_base", return_value=[]):
                    with pytest.raises(ChangedPathMissingError, match="removed.yml"):
                        _workflow_yaml_targets(tmp_path)

    def test_changed_action_metadata_invalidates_all_workflows(self, tmp_path: Path) -> None:
        from checks_tooling import _workflow_yaml_targets

        self._write_workflow(tmp_path, "ci.yml", "on: push\n")
        self._write_workflow(tmp_path, "release.yaml", "on: push\n")
        action = tmp_path / ".github" / "actions" / "setup" / "action.yml"
        action.parent.mkdir(parents=True)
        action.write_text("name: setup\nruns:\n  using: composite\n  steps: []\n")

        with patch(
            "checks_tooling._changed_paths_since_base",
            return_value=[".github/actions/setup/action.yml"],
        ):
            with patch("checks_tooling._deleted_paths_since_base", return_value=[]):
                assert _workflow_yaml_targets(tmp_path) == [
                    ".github/workflows/ci.yml",
                    ".github/workflows/release.yaml",
                ]

    def test_changed_reusable_workflow_includes_unchanged_callers(self, tmp_path: Path) -> None:
        from checks_tooling import _workflow_yaml_targets

        self._write_workflow(tmp_path, "called.yml", "on:\n  workflow_call:\n")
        self._write_workflow(
            tmp_path,
            "caller.yml",
            "jobs:\n  call:\n    uses: ./.github/workflows/called.yml\n",
        )
        self._write_workflow(tmp_path, "unrelated.yml", "on: push\n")

        with patch(
            "checks_tooling._changed_paths_since_base",
            return_value=[".github/workflows/called.yml"],
        ):
            with patch("checks_tooling._deleted_paths_since_base", return_value=[]):
                assert _workflow_yaml_targets(tmp_path) == [
                    ".github/workflows/called.yml",
                    ".github/workflows/caller.yml",
                ]

    def test_deleted_action_metadata_invalidates_all_workflows(self, tmp_path: Path) -> None:
        from checks_tooling import _workflow_yaml_targets

        self._write_workflow(tmp_path, "ci.yml", "on: push\n")
        with patch("checks_tooling._changed_paths_since_base", return_value=[]):
            with patch(
                "checks_tooling._deleted_paths_since_base",
                return_value=[".github/actions/setup/action.yml"],
            ):
                assert _workflow_yaml_targets(tmp_path) == [".github/workflows/ci.yml"]

    def test_reusable_workflow_rename_includes_old_path_consumers(self, tmp_path: Path) -> None:
        from checks_tooling import _workflow_yaml_targets

        self._write_workflow(tmp_path, "renamed.yml", "on:\n  workflow_call:\n")
        self._write_workflow(
            tmp_path,
            "caller.yml",
            "jobs:\n  call:\n    uses: ./.github/workflows/old.yml\n",
        )
        with patch(
            "checks_tooling._changed_paths_since_base",
            return_value=[".github/workflows/renamed.yml"],
        ):
            with patch(
                "checks_tooling._deleted_paths_since_base",
                return_value=[".github/workflows/old.yml"],
            ):
                assert _workflow_yaml_targets(tmp_path) == [
                    ".github/workflows/caller.yml",
                    ".github/workflows/renamed.yml",
                ]

    @staticmethod
    def _write_workflow(root: Path, name: str, content: str) -> None:
        path = root / ".github" / "workflows" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class TestWorkflowYamlTargetsWorktreeOnly:
    """Real-repo regression: a workflow file edited only in the worktree
    (never committed, and here not even staged) must still be scoped in.

    Guards the specific gate wiring (``_workflow_yaml_targets``'s extension
    and path filtering) against the union added to the shared
    ``_changed_paths_since_base`` helper; the union mechanics themselves are
    covered generically in ``test_changed_paths_since_base.py``.
    """

    def test_uncommitted_workflow_edit_is_scoped_in(
        self,
        tmp_path: Path,
        make_repo_with_base: Any,
        no_gh: None,
    ) -> None:
        from checks_tooling import _workflow_yaml_targets

        repo = make_repo_with_base(tmp_path)
        wf_dir = repo / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("on: push\n", encoding="utf-8")
        # Deliberately NOT committed and NOT staged: pure worktree edit.

        assert _workflow_yaml_targets(repo) == [".github/workflows/ci.yml"]


class TestValidateWorkflowYamlScoping:
    """Wiring tests: ``validate_workflow_yaml`` honors the three scope outcomes."""

    def test_empty_scope_passes_without_invoking_actionlint(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("on: push\n", encoding="utf-8")
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch("checks_tooling._workflow_yaml_targets", return_value=[]):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    assert validate_workflow_yaml(tmp_path) is True
        mock_run.assert_not_called()

    def test_scoped_subset_is_passed_to_actionlint(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("on: push\n", encoding="utf-8")
        (wf_dir / "release.yml").write_text("on: push\n", encoding="utf-8")
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch(
                "checks_tooling._workflow_yaml_targets",
                return_value=[".github/workflows/ci.yml"],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_workflow_yaml(tmp_path) is True

        command = mock_run.call_args.args[0]
        assert command == ["actionlint", str(tmp_path / ".github/workflows/ci.yml")]

    def test_none_scope_falls_back_to_full_directory_glob(self, tmp_path: Path) -> None:
        """An unproven scope (no base ref / diff failure) must not skip the check."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("on: push\n", encoding="utf-8")
        (wf_dir / "release.yml").write_text("on: push\n", encoding="utf-8")
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch("checks_tooling._workflow_yaml_targets", return_value=None):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_workflow_yaml(tmp_path) is True

        command = mock_run.call_args.args[0]
        assert command[0] == "actionlint"
        assert len(command) == 3  # actionlint + both workflow files

    def test_scoped_command_failure_still_fails(self, tmp_path: Path) -> None:
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("on: push\n", encoding="utf-8")
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch(
                "checks_tooling._workflow_yaml_targets",
                return_value=[".github/workflows/ci.yml"],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (1, "ci.yml:1:1: some error [syntax-check]", "")
                    assert validate_workflow_yaml(tmp_path) is False

    def test_scoped_path_with_space_is_quoted_as_a_single_argv_element(
        self, tmp_path: Path
    ) -> None:
        """A path with a space must survive as one argv element, not split.

        ``_run_subprocess`` invokes actionlint via ``subprocess.run`` with a
        list (no shell), so this is really a test that the file list is built
        from ``repo_root / path`` without any shell-style joining that could
        split on whitespace.
        """
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        weird = wf_dir / "release notes.yml"
        weird.write_text("on: push\n", encoding="utf-8")
        with patch("checks_tooling.shutil.which", return_value="/usr/bin/actionlint"):
            with patch(
                "checks_tooling._workflow_yaml_targets",
                return_value=[".github/workflows/release notes.yml"],
            ):
                with patch("checks_tooling._run_subprocess") as mock_run:
                    mock_run.return_value = (0, "", "")
                    assert validate_workflow_yaml(tmp_path) is True

        command = mock_run.call_args.args[0]
        assert command == ["actionlint", str(tmp_path / ".github/workflows/release notes.yml")]
        # Exactly one argv element for the file, not two from a whitespace split.
        assert len(command) == 2


class TestValidateVendorPortability:
    """The vendor-portability gate wraps check_vendor_portability.py (#2050).

    Exit-code contract mirrored from the wrapped script:
    0 (no new offenders / no scan roots) -> pass, 1 (new offender) -> fail,
    2 (config error) -> fail. A missing wrapped script raises MissingScriptSkip.
    """

    def _make_repo(self, tmp_path: Path) -> Path:
        (tmp_path / "scripts" / "validation").mkdir(parents=True)
        (tmp_path / "scripts" / "validation" / "check_vendor_portability.py").write_text(
            "# stub\n", encoding="utf-8"
        )
        return tmp_path

    def test_passes_when_checker_exits_zero(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (0, "[PASS] No new vendor-portability offenders.\n", "")
            assert validate_vendor_portability(repo) is True

    def test_fails_on_new_offender_exit_one(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (1, "[FAIL] 1 new vendor-portability offender(s).\n", "")
            assert validate_vendor_portability(repo) is False

    def test_fails_on_config_error_exit_two(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (2, "", "[FAIL] repo root not found")
            assert validate_vendor_portability(repo) is False

    def test_missing_script_raises_skip(self, tmp_path: Path) -> None:
        import pytest

        from scripts.validation.pre_pr import (
            MissingScriptSkip,
            validate_vendor_portability,
        )

        with pytest.raises(MissingScriptSkip):
            validate_vendor_portability(tmp_path)

    def test_passes_repo_root_to_checker(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("checks_spec._run_subprocess") as mock_run:
            mock_run.return_value = (0, "", "")
            validate_vendor_portability(repo)

        mock_run.assert_called_once()
        command = mock_run.call_args.args[0]
        repo_root_index = command.index("--repo-root")
        assert command[repo_root_index + 1] == str(repo)


class TestValidateCiDependencyPinsSkipsBeforeImporting:
    """The skip path must survive a tree that cannot import the checker.

    ``check_ci_dependency_pins`` imports ``packaging``. A downstream install
    with no ``.github/`` tree is also the install least likely to carry dev
    dependencies, so importing before the existence check would raise
    ImportError on exactly the tree the function is written to skip. Issue #3377.
    """

    @staticmethod
    def _block_import(monkeypatch: Any) -> None:
        import sys

        # A None entry makes ``import check_ci_dependency_pins`` raise
        # ImportError, which is what a missing ``packaging`` looks like from
        # the caller's side.
        monkeypatch.setitem(sys.modules, "check_ci_dependency_pins", None)

    def test_an_absent_github_tree_skips_without_importing(
        self,
        tmp_path: Path,
        monkeypatch: Any
    ) -> None:
        from checks_tooling import validate_ci_dependency_pins

        from scripts.validation.pre_pr import MissingScriptSkip

        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n', encoding="utf-8")
        self._block_import(monkeypatch)
        with pytest.raises(MissingScriptSkip):
            validate_ci_dependency_pins(tmp_path)

    def test_an_absent_pyproject_skips_without_importing(
        self,
        tmp_path: Path,
        monkeypatch: Any
    ) -> None:
        from checks_tooling import validate_ci_dependency_pins

        from scripts.validation.pre_pr import MissingScriptSkip

        (tmp_path / ".github").mkdir()
        self._block_import(monkeypatch)
        with pytest.raises(MissingScriptSkip):
            validate_ci_dependency_pins(tmp_path)

    def test_a_present_tree_still_imports_and_runs(self, tmp_path: Path) -> None:
        """Negative control: a bad pin returns False, proving the checker ran."""
        from checks_tooling import validate_ci_dependency_pins

        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "w.yml").write_text(
            "run: pip install pytest==8.0.0\n", encoding="utf-8"
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname="x"\ndependencies=["pytest>=9.0.3"]\n', encoding="utf-8"
        )
        assert validate_ci_dependency_pins(tmp_path) is False
