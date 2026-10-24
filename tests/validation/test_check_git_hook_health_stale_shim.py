"""A shim older than the ``lefthook:`` runner key is refused (issue #6896).

Lefthook embeds the configured ``lefthook:`` command in each shim when it
installs. With ``no_auto_install: true`` nothing refreshes a shim afterward, so
a clone installed before the key landed keeps calling Lefthook directly and
never reaches ``lefthook_runner.py``. Every shim still ends in the same
dispatch line, so the dispatch check alone reports that clone healthy.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_git_hook_health
import lefthook_inventory

# Reuse the scratch-repo helpers of the sibling gate suite without importing it
# as a package member, the way test_check_git_hook_health_environment.py does.
_helpers = runpy.run_path(str(Path(__file__).with_name("test_check_git_hook_health.py")))
_make_repo = _helpers["_make_repo"]
_run_cli = _helpers["_run_cli"]
_install_prepush = _helpers["_install_prepush"]

RUNNER = "python3 scripts/validation/lefthook_runner.py"
RUNNER_CONFIG = (
    f"lefthook: {RUNNER}\n"
    "pre-push:\n  commands:\n    noop:\n      run: true\n"
    "commit-msg:\n  commands:\n    noop:\n      run: true\n"
)
NO_RUNNER_CONFIG = (
    "pre-push:\n  commands:\n    noop:\n      run: true\n"
    "commit-msg:\n  commands:\n    noop:\n      run: true\n"
)


def _shim(hook_name: str, *, runner: str | None) -> str:
    """The shape Lefthook installs, reduced to the lines this gate reads."""
    branch = ""
    if runner is not None:
        branch = f'  elif test -n "{runner}"\n  then\n    {runner} "$@"\n'
    return (
        "#!/bin/sh\ncall_lefthook()\n{\n"
        '  if test -n "$LEFTHOOK_BIN"\n  then\n    "$LEFTHOOK_BIN" "$@"\n'
        f'{branch}  elif lefthook -h >/dev/null 2>&1\n  then\n    lefthook "$@"\n  fi\n}}\n'
        f'call_lefthook run "{hook_name}" "$@"\n'
    )


def _install(hooks_dir: Path, name: str, body: str) -> None:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / name
    hook.write_text(body, encoding="utf-8")
    hook.chmod(0o755)


def _repo(tmp_path: Path, config: str) -> Path:
    repo = _make_repo(tmp_path, "repo")
    (repo / "lefthook.yml").write_text(config, encoding="utf-8")
    return repo


class TestStaleShim:
    def test_a_shim_without_the_runner_line_fails(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, RUNNER_CONFIG)
        hooks = repo / ".git" / "hooks"
        _install(hooks, "pre-push", _shim("pre-push", runner=None))
        _install(hooks, "commit-msg", _shim("commit-msg", runner=RUNNER))

        result = _run_cli(repo)

        assert result.returncode == 1
        assert check_git_hook_health._STALE_SHIM_PREFIX in result.stderr
        assert "pre-push" in result.stderr
        assert RUNNER in result.stderr
        assert "skip the repository's Lefthook runner" in result.stderr
        assert check_git_hook_health.REMEDY in result.stderr

    def test_only_the_stale_hooks_are_named(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, RUNNER_CONFIG)
        hooks = repo / ".git" / "hooks"
        _install(hooks, "pre-push", _shim("pre-push", runner=RUNNER))
        _install(hooks, "commit-msg", _shim("commit-msg", runner=None))

        reason = check_git_hook_health.diagnose(repo)

        assert reason is not None
        assert "a shim for commit-msg that" in reason
        assert "pre-push" not in reason.split("configured lefthook command")[0]

    def test_every_stale_hook_is_named_together(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, RUNNER_CONFIG)
        hooks = repo / ".git" / "hooks"
        for name in ("pre-push", "commit-msg"):
            _install(hooks, name, _shim(name, runner=None))

        reason = check_git_hook_health.diagnose(repo)

        assert reason is not None
        assert "shims for commit-msg, pre-push" in reason

    def test_shims_that_carry_the_runner_pass(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, RUNNER_CONFIG)
        hooks = repo / ".git" / "hooks"
        for name in ("pre-push", "commit-msg"):
            _install(hooks, name, _shim(name, runner=RUNNER))

        result = _run_cli(repo)

        assert result.returncode == 0
        assert "2 of 2 found" in result.stdout

    def test_a_shim_built_for_a_different_runner_fails(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, RUNNER_CONFIG)
        hooks = repo / ".git" / "hooks"
        for name in ("pre-push", "commit-msg"):
            _install(hooks, name, _shim(name, runner="uv run --frozen lefthook"))

        reason = check_git_hook_health.diagnose(repo)

        assert reason is not None
        assert reason.startswith(check_git_hook_health._STALE_SHIM_PREFIX)

    def test_a_comment_quoting_the_runner_does_not_satisfy_the_check(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, RUNNER_CONFIG)
        hooks = repo / ".git" / "hooks"
        for name in ("pre-push", "commit-msg"):
            body = _shim(name, runner=None).replace(
                "call_lefthook()", f'# {RUNNER} "$@"\ncall_lefthook()'
            )
            _install(hooks, name, body)

        reason = check_git_hook_health.diagnose(repo)

        assert reason is not None
        assert reason.startswith(check_git_hook_health._STALE_SHIM_PREFIX)

    def test_a_repository_without_a_runner_key_accepts_an_older_shim(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, NO_RUNNER_CONFIG)
        hooks = repo / ".git" / "hooks"
        for name in ("pre-push", "commit-msg"):
            _install(hooks, name, _shim(name, runner=None))

        assert _run_cli(repo).returncode == 0

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX execute bits")
    def test_a_missing_shim_keeps_its_own_diagnosis(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, RUNNER_CONFIG)
        _install(repo / ".git" / "hooks", "pre-push", _shim("pre-push", runner=RUNNER))

        reason = check_git_hook_health.diagnose(repo)

        assert reason is not None
        assert "no live shim for configured hook type commit-msg" in reason
        assert check_git_hook_health._STALE_SHIM_PREFIX not in reason

    def test_an_unreadable_shim_counts_as_stale(self, tmp_path: Path) -> None:
        hook = tmp_path / "pre-push"
        hook.write_bytes(b"\xff\xfe\x00 not utf-8")

        assert check_git_hook_health._runner_failure(hook, RUNNER) is True

    def test_a_dispatch_check_alone_passes_the_stale_shim(self, tmp_path: Path) -> None:
        """Pins why a second check exists: the dispatch line cannot see the gap."""
        hook = tmp_path / "pre-push"
        hook.write_text(_shim("pre-push", runner=None), encoding="utf-8")

        assert check_git_hook_health._dispatch_failure(hook, "pre-push") is None
        assert check_git_hook_health._runner_failure(hook, RUNNER) is True


class TestFallbackCollision:
    """The shim's built-in fallbacks must not satisfy the configured-runner check."""

    @pytest.mark.parametrize("runner", ["uv run lefthook", "pnpm lefthook", "bundle exec lefthook"])
    def test_a_runner_equal_to_a_builtin_fallback_is_still_stale(
        self, tmp_path: Path, runner: str
    ) -> None:
        stale_with_fallbacks = (
            "#!/bin/sh\ncall_lefthook()\n{\n"
            '  if test -n "$LEFTHOOK_BIN"\n  then\n    "$LEFTHOOK_BIN" "$@"\n'
            f'  elif {runner} -h >/dev/null 2>&1\n  then\n    {runner} "$@"\n  fi\n}}\n'
            'call_lefthook run "pre-push" "$@"\n'
        )
        hook = tmp_path / "pre-push"
        hook.write_text(stale_with_fallbacks, encoding="utf-8")

        assert check_git_hook_health._runner_failure(hook, runner) is True

    def test_the_same_runner_in_its_own_branch_passes(self, tmp_path: Path) -> None:
        hook = tmp_path / "pre-push"
        hook.write_text(_shim("pre-push", runner="uv run lefthook"), encoding="utf-8")

        assert check_git_hook_health._runner_failure(hook, "uv run lefthook") is False


class TestRunnerNormalization:
    """Lefthook rewrites the value before embedding it; the gate must agree."""

    def test_a_multiline_runner_is_matched_as_lefthook_joins_it(self, tmp_path: Path) -> None:
        # `lefthook dump` prints "cd sub\npnpm lefthook\n"; the installed shim
        # holds `cd sub;pnpm lefthook "$@"` (measured on Lefthook 2.2.2).
        hook = tmp_path / "pre-push"
        hook.write_text(_shim("pre-push", runner="cd sub;pnpm lefthook"), encoding="utf-8")

        assert check_git_hook_health._runner_failure(hook, "cd sub\npnpm lefthook\n") is False

    def test_a_windows_path_runner_is_matched_in_slash_form(self, tmp_path: Path) -> None:
        hook = tmp_path / "pre-push"
        hook.write_text(_shim("pre-push", runner="C:/Tools/lefthook.exe"), encoding="utf-8")

        assert check_git_hook_health._runner_failure(hook, "C:\\Tools\\lefthook.exe") is False

    def test_surrounding_whitespace_in_the_value_is_ignored(self, tmp_path: Path) -> None:
        hook = tmp_path / "pre-push"
        hook.write_text(_shim("pre-push", runner=RUNNER), encoding="utf-8")

        assert check_git_hook_health._runner_failure(hook, f"  {RUNNER}\n") is False

    def test_a_different_multiline_runner_is_still_stale(self, tmp_path: Path) -> None:
        hook = tmp_path / "pre-push"
        hook.write_text(_shim("pre-push", runner="cd sub;pnpm lefthook"), encoding="utf-8")

        assert check_git_hook_health._runner_failure(hook, "cd other\npnpm lefthook\n") is True


class TestRunnerInventory:
    def test_the_runner_is_read_from_the_dump(self) -> None:
        dump = f'{{"lefthook": "{RUNNER}", "pre-push": {{"jobs": []}}}}'

        inventory = lefthook_inventory._parse_inventory(dump)

        assert inventory.runner == RUNNER
        assert inventory.hook_types == frozenset({"pre-push"})

    @pytest.mark.parametrize(
        "dump", ['{"pre-push": {"jobs": []}}', '{"lefthook": "  "}', '{"lefthook": 3}']
    )
    def test_an_absent_blank_or_non_string_key_is_no_runner(self, dump: str) -> None:
        assert lefthook_inventory._parse_inventory(dump).runner is None

    def test_a_non_mapping_dump_is_still_a_config_error(self) -> None:
        with pytest.raises(lefthook_inventory.LefthookConfigError):
            lefthook_inventory._parse_inventory("[]")
