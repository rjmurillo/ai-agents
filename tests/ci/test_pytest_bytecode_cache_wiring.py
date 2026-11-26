"""Wiring tests for the pytest assertion-rewrite bytecode cache in pytest.yml.

The cache is a performance cache only. pytest validates every rewritten .pyc
against the source hash (`_pytest/assertion/rewrite.py`, `_read_pyc`) and
recompiles a mismatch, so a stale restore costs time and never changes a test
outcome. These tests pin the design that depends on that property: no hash of
tests/ in the key, one save from the primary leg on a main push, and a prefix
outside the checkout that the pytest child really inherits.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from scripts.ci import run_pytest_non_tmp
from tests.ci import pytest_split_collect_helpers as collect_helpers
from tests.ci.pytest_split_workflow_helpers import WORKFLOW, steps_using, workflow_jobs

REPO_ROOT = Path(__file__).resolve().parents[2]
KEY_PREFIX = "pytest-bytecode-"
CACHE_SHA = "55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
RUNNER_TEMP = "${{ runner.temp }}"
PREFIX = f"{RUNNER_TEMP}/pytest-bytecode-cache"
WORKSPACE = "${{ github.workspace }}"
PYTHON_VERSION_OUTPUT = "steps.setup-code-env.outputs.python-version"
UNIQUE_SUFFIX = "${{ github.run_id }}-${{ github.run_attempt }}"
HASH_FILES = re.compile(r"hashFiles\(([^)]*)\)")
PINNED_USES = re.compile(r"^\s*(?:-\s*)?uses:\s+\S+@[0-9a-f]{40}\s+#\s+\S+")


def _steps() -> list[dict[str, Any]]:
    return workflow_jobs()["test"]["steps"]


def _names() -> list[str | None]:
    return [step.get("name") for step in _steps()]


def _step(name: str) -> dict[str, Any]:
    return next(step for step in _steps() if step.get("name") == name)


def _bytecode(action: str, job: str = "test") -> list[dict[str, Any]]:
    return [s for s in steps_using(job, action) if s["with"]["key"].startswith(KEY_PREFIX)]


def _restore() -> dict[str, Any]:
    (step,) = _bytecode("actions/cache/restore")
    return step


def _save() -> dict[str, Any]:
    (step,) = _bytecode("actions/cache/save")
    return step


def _key_hashes_test_sources(key: str) -> bool:
    return any("tests" in arg for arg in HASH_FILES.findall(key))


def _key_tracks_python(key: str) -> bool:
    return PYTHON_VERSION_OUTPUT in key


def _is_inside(path: str, root: Path) -> bool:
    return Path(path).resolve().is_relative_to(root.resolve())


def _is_pinned(line: str) -> bool:
    return PINNED_USES.match(line) is not None


class TestPrefixOutsideTheCheckout:
    def test_run_pytest_sets_the_prefix_under_runner_temp(self) -> None:
        assert _step("Run pytest")["env"]["PYTHONPYCACHEPREFIX"] == PREFIX

    def test_the_prefix_is_not_defined_at_job_level(self) -> None:
        """Job-level env cannot read `runner`; actionlint rejects it and the workflow fails."""
        assert "PYTHONPYCACHEPREFIX" not in workflow_jobs()["test"].get("env", {})

    def test_restore_and_save_share_one_path(self) -> None:
        """Both steps must name one path, or a save would never reach a later restore."""
        assert _restore()["with"]["path"] == _save()["with"]["path"]

    def test_the_cached_path_is_the_checkout_subtree_of_the_prefix(self) -> None:
        """Python stores a pyc at the prefix plus the absolute source path.

        The prefix root also holds pycs for mutation worktrees and temp dirs that
        no later run can read, so the cache path stops at the checkout subtree.
        """
        prefix = _step("Run pytest")["env"]["PYTHONPYCACHEPREFIX"]
        assert prefix == PREFIX
        assert _restore()["with"]["path"] == f"{prefix}{WORKSPACE}"
        assert _save()["with"]["path"] == f"{prefix}{WORKSPACE}"

    def test_the_test_job_runs_on_a_posix_runner(self) -> None:
        """Plain concatenation of prefix and workspace is only valid for a POSIX path."""
        assert str(workflow_jobs()["test"]["runs-on"]).startswith("ubuntu-")

    @pytest.mark.skipif(sys.platform == "win32", reason="the workflow job is POSIX only")
    def test_python_places_checkout_bytecode_under_prefix_plus_workspace(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(sys, "pycache_prefix", str(tmp_path))
        source = REPO_ROOT / "scripts" / "ci" / "probe.py"
        pyc = Path(importlib.util.cache_from_source(str(source)))
        assert pyc.is_relative_to(Path(f"{tmp_path}{REPO_ROOT}"))

    def test_the_prefix_never_references_the_workspace(self) -> None:
        assert "github.workspace" not in PREFIX
        assert "github.workspace" not in _step("Run pytest")["env"]["PYTHONPYCACHEPREFIX"]

    def test_the_expanded_prefix_is_outside_the_repository(self, tmp_path: Path) -> None:
        expanded = PREFIX.replace(RUNNER_TEMP, str(tmp_path))
        assert not _is_inside(expanded, REPO_ROOT)

    def test_the_outside_check_flags_a_prefix_inside_the_checkout(self) -> None:
        """Negative control: a workspace-relative prefix must trip the same predicate."""
        inside = f"{REPO_ROOT}/.pytest-bytecode-cache"
        assert _is_inside(inside, REPO_ROOT)


class TestPytestChildInheritsThePrefix:
    def test_the_non_tmp_runner_copies_the_environment(self, monkeypatch, tmp_path) -> None:
        prefix = tmp_path / "bytecode-cache"
        monkeypatch.setenv("PYTEST_NON_TMP_ROOT", str(tmp_path / "pytest-root"))
        monkeypatch.setenv("PYTHONPYCACHEPREFIX", str(prefix))
        completed = SimpleNamespace(returncode=0)

        with mock.patch.object(run_pytest_non_tmp.subprocess, "run", return_value=completed) as run:
            assert run_pytest_non_tmp.main(["--version"]) == 0

        assert run.call_args.kwargs["env"]["PYTHONPYCACHEPREFIX"] == str(prefix)

    def test_the_split_collect_helper_copies_the_environment(self, monkeypatch) -> None:
        prefix = "/outside-the-checkout/bytecode-cache"
        monkeypatch.setenv("PYTHONPYCACHEPREFIX", prefix)
        completed = SimpleNamespace(stdout="", stderr="", returncode=0)

        with mock.patch.object(collect_helpers.subprocess, "run", return_value=completed) as run:
            collect_helpers.collect_with_code([])

        assert run.call_args.kwargs["env"]["PYTHONPYCACHEPREFIX"] == prefix

    def test_a_real_pytest_child_writes_rewritten_bytecode_under_the_prefix(
        self, monkeypatch, tmp_path
    ) -> None:
        prefix = tmp_path / "bytecode-cache"
        suite = tmp_path / "suite"
        suite.mkdir()
        (suite / "test_probe.py").write_text("def test_probe():\n    assert 1 + 1 == 2\n")
        empty_ini = tmp_path / "pytest.ini"
        empty_ini.write_text("[pytest]\n")
        monkeypatch.setenv("PYTEST_NON_TMP_ROOT", str(tmp_path / "pytest-root"))
        monkeypatch.setenv("PYTHONPYCACHEPREFIX", str(prefix))
        monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)

        code = run_pytest_non_tmp.main(
            ["-c", str(empty_ini), "--rootdir", str(suite), "-p", "no:cacheprovider", str(suite)]
        )

        written = [p.name for p in prefix.rglob("*.pyc") if "pytest" in p.name]
        assert code == 0
        assert any(name.startswith("test_probe.") for name in written), written
        assert not list(suite.rglob("*.pyc")), "bytecode leaked next to the sources"


class TestRestoreOnEveryLeg:
    def test_the_restore_uses_the_pinned_cache_action(self) -> None:
        assert _restore()["uses"] == f"actions/cache/restore@{CACHE_SHA}"

    def test_the_restore_has_no_condition_so_every_matrix_leg_restores(self) -> None:
        assert "if" not in _restore()

    def test_every_matrix_leg_reaches_run_pytest_unconditionally(self) -> None:
        legs = workflow_jobs()["test"]["strategy"]["matrix"]["include"]
        assert len(legs) >= 2
        assert "if" not in _step("Run pytest")

    def test_the_restore_runs_after_setup_and_before_pytest(self) -> None:
        names = _names()
        assert _step("Setup code environment")["id"] == "setup-code-env"
        assert (
            names.index("Setup code environment")
            < names.index("Restore pytest bytecode cache")
            < names.index("Run pytest")
        )

    def test_exactly_one_bytecode_restore_exists(self) -> None:
        assert len(_bytecode("actions/cache/restore")) == 1

    def test_restore_keys_are_a_stable_prefix_without_run_or_lock_identity(self) -> None:
        restore_keys = _restore()["with"]["restore-keys"]
        assert restore_keys.startswith(KEY_PREFIX)
        assert restore_keys.endswith("-")
        assert PYTHON_VERSION_OUTPUT in restore_keys
        assert "run_id" not in restore_keys
        assert "hashFiles" not in restore_keys
        assert _restore()["with"]["key"].startswith(restore_keys)


class TestKeyDesign:
    def test_the_key_tracks_os_arch_interpreter_and_lock_file(self) -> None:
        key = _restore()["with"]["key"]
        assert "runner.os" in key
        assert "runner.arch" in key
        assert _key_tracks_python(key)
        assert HASH_FILES.findall(key) == ["'uv.lock'"]

    def test_the_key_ignores_test_sources_because_pytest_validates_source_hashes(self) -> None:
        """A test edit must not rotate the key.

        pytest compares each rewritten .pyc with the source hash and rewrites only the
        stale file, so keying on tests/ would discard a valid cache on every commit.
        """
        for step in (_restore(), _save()):
            assert not _key_hashes_test_sources(step["with"]["key"])
        assert not _key_hashes_test_sources(_restore()["with"]["restore-keys"])

    def test_the_key_detector_flags_a_key_that_hashes_tests(self) -> None:
        """Negative control: the predicate above is not vacuous."""
        assert _key_hashes_test_sources(f"{KEY_PREFIX}{{{{ hashFiles('tests/**/*.py') }}}}")
        assert _key_hashes_test_sources(f"{KEY_PREFIX}{{{{ hashFiles('uv.lock', 'tests/**') }}}}")
        assert not _key_hashes_test_sources(f"{KEY_PREFIX}{{{{ hashFiles('uv.lock') }}}}")

    def test_the_key_detector_flags_a_key_without_the_python_version(self) -> None:
        """Negative control: a key without the interpreter would mix magic-number-bound files."""
        assert not _key_tracks_python(f"{KEY_PREFIX}{{{{ runner.os }}}}-{UNIQUE_SUFFIX}")
        assert _key_tracks_python(_restore()["with"]["key"])

    def test_the_key_is_unique_per_run_and_attempt(self) -> None:
        assert _restore()["with"]["key"].endswith(UNIQUE_SUFFIX)
        assert _save()["with"]["key"].endswith(UNIQUE_SUFFIX)

    def test_save_and_restore_keys_are_identical(self) -> None:
        assert _save()["with"]["key"] == _restore()["with"]["key"]


class TestSaveFromThePrimaryLegOnMain:
    def test_exactly_one_bytecode_save_exists_across_the_workflow(self) -> None:
        saves = [
            (job, step["name"])
            for job in workflow_jobs()
            for step in _bytecode("actions/cache/save", job)
        ]
        assert saves == [("test", "Save pytest bytecode cache")]

    def test_the_save_condition_is_exactly_primary_push_main_success(self) -> None:
        condition = " ".join(str(_save()["if"]).split())
        assert "||" not in condition
        assert set(condition.split(" && ")) == {
            "matrix.primary",
            "github.event_name == 'push'",
            "github.ref == 'refs/heads/main'",
            "steps.run-pytest.outcome == 'success'",
        }

    def test_the_save_never_runs_for_pull_requests(self) -> None:
        condition = str(_save()["if"])
        for event in ("pull_request", "merge_group", "workflow_dispatch", "schedule"):
            assert event not in condition

    def test_the_primary_leg_is_unique_and_collects_the_whole_split_pool(self) -> None:
        legs = workflow_jobs()["test"]["strategy"]["matrix"]["include"]
        primary = [leg for leg in legs if leg.get("primary")]
        assert [leg["partition"] for leg in primary] == ["split-1"]

    def test_the_save_runs_after_pytest_and_uses_the_pinned_action(self) -> None:
        assert _names().index("Run pytest") < _names().index("Save pytest bytecode cache")
        assert _save()["uses"] == f"actions/cache/save@{CACHE_SHA}"


class TestPruneBeforeCacheSave:
    @staticmethod
    def _prune() -> dict[str, Any]:
        return _step("Prune pytest bytecode cache")

    def test_exactly_one_prune_step_exists(self) -> None:
        assert _names().count("Prune pytest bytecode cache") == 1

    def test_the_prune_script_is_checked_in(self) -> None:
        assert (REPO_ROOT / "scripts" / "ci" / "prune_bytecode_cache.py").is_file()

    def test_the_prune_runs_directly_before_the_save(self) -> None:
        names = _names()
        assert names.index("Prune pytest bytecode cache") + 1 == names.index(
            "Save pytest bytecode cache"
        )

    def test_the_prune_uses_the_same_launcher_as_run_pytest(self) -> None:
        pytest_command = " ".join(str(_step("Run pytest")["run"]).split())
        prune_command = " ".join(str(self._prune()["run"]).split())
        assert pytest_command.startswith("uv run --frozen python ")
        assert prune_command.startswith(
            "uv run --frozen python scripts/ci/prune_bytecode_cache.py "
        )

    def test_the_prune_condition_matches_the_save_condition_exactly(self) -> None:
        assert self._prune()["if"] == _save()["if"]

    def test_the_prune_targets_the_saved_path_inside_the_workspace(self) -> None:
        command = " ".join(str(self._prune()["run"]).split())
        assert '--workspace "${{ github.workspace }}"' in command
        assert (
            '--cache-root "${{ runner.temp }}/pytest-bytecode-cache${{ github.workspace }}"'
            in command
        )

    def test_the_prune_and_save_failures_are_not_ignored(self) -> None:
        assert "continue-on-error" not in self._prune()
        assert "continue-on-error" not in _save()
        assert "always()" not in str(_save()["if"])


class TestPermissionsAndPinningUnchanged:
    def test_the_test_job_keeps_read_only_contents_permission(self) -> None:
        assert workflow_jobs()["test"]["permissions"] == {"contents": "read"}

    def test_the_new_steps_reuse_the_pin_the_durations_cache_already_uses(self) -> None:
        durations = [
            step
            for action in ("actions/cache/restore", "actions/cache/save")
            for step in steps_using("test-durations", action) + steps_using("test", action)
            if step["with"]["key"].startswith("pytest-split-durations-")
        ]
        assert durations
        assert {step["uses"].split("@")[1] for step in durations} == {CACHE_SHA}

    def test_every_external_uses_line_is_a_pinned_sha_with_a_version_comment(self) -> None:
        offenders = [
            line.strip()
            for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
            if line.lstrip().lstrip("- ").startswith("uses:")
            and "./" not in line.split("uses:", 1)[1].split()[0]
            and not _is_pinned(line)
        ]
        assert offenders == []

    @pytest.mark.parametrize(
        "line",
        [
            "        uses: actions/cache/save@v4",
            "        uses: actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
            "        uses: actions/cache/save@55cc83 # v6",
        ],
    )
    def test_the_pin_detector_rejects_unpinned_references(self, line: str) -> None:
        """Negative control for the pinning predicate."""
        assert not _is_pinned(line)

    def test_the_pin_detector_accepts_the_cache_pin(self) -> None:
        assert _is_pinned(f"        uses: actions/cache/save@{CACHE_SHA} # v6")
