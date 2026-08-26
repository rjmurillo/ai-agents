"""Where bounded pytest-xdist parallelism may be applied, and where it must not.

Issue #4823. The pre-push gate runs the suite in four partitions
(``scripts/validation/git_hook_policy.py::_pytest_commands``). Bulk and
mutation run on workers. Process-sensitive modules stay serial:

* the safe-push and mutation-signal partition;
* the pr-autofix process-group partition;
* the two branch-coverage pin steps and the Windows path-contract step in
  ``.github/workflows/pytest.yml`` (asserted in
  ``tests/workflows/test_pytest_xdist_parallelism.py``, which owns the CI half
  of this contract).

The mechanism that keeps those serial is negative: ``-n`` and ``--dist`` are
passed at the call site, never in ``[tool.pytest.ini_options].addopts``. Global
addopts reach every pytest invocation in the repo, so a single ``-n auto`` there
would silently parallelize the pins, the safe-push partition, and every ad-hoc
``pytest tests/foo.py`` a developer runs. ``test_global_addopts_carries_no_``
``parallel_flags`` is the guard on that.

Direct calls and CI use ``auto``, xdist's own name for one worker per logical
CPU. The local pre-push job caps workers at four because it runs beside other
CPU-heavy jobs in one parallel Lefthook group. Low-core hosts use fewer.
``AI_AGENTS_PYTEST_WORKERS`` accepts ``auto`` or a positive integer and rejects
everything else. The parent consumes this control before starting pytest so
policy tests inside the child process still observe the default environment.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

from scripts.validation import git_hook_policy as policy

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Every spelling xdist accepts for the two flags this policy places by hand.
_WORKER_FLAGS = ("-n", "--numprocesses")
_DIST_FLAGS = ("--dist",)


def _flag_value(command: list[str], names: tuple[str, ...]) -> str | None:
    """Return the value passed to the first flag in ``names``, or None.

    Handles both the space-separated (``-n auto``) and inline (``--dist=loadfile``)
    argv forms, so a future rewrite from one to the other cannot slip past the
    assertions below by changing shape.
    """
    for index, token in enumerate(command):
        if token in names:
            return command[index + 1] if index + 1 < len(command) else ""
        for name in names:
            if token.startswith(f"{name}="):
                return token.split("=", 1)[1]
    return None


def _pytest_commands_by_partition(
    repo_root: Path,
) -> tuple[list[str], list[str], list[str], list[str]]:
    commands = policy._pytest_commands(repo_root)
    assert len(commands) == 4, f"expected four pre-push pytest commands, got {commands}"
    return commands[0], commands[1], commands[2], commands[3]


@pytest.mark.parametrize(
    ("workflow", "expects_no_full"),
    [
        (".github/workflows/pytest.yml", True),
        (".github/workflows/other.yml", False),
    ],
)
def test_workflow_local_avoids_duplicate_pytest_runtime(
    workflow: str,
    expects_no_full: bool,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        policy,
        "_select_pushed_workflows",
        lambda paths, root: [workflow],
    )

    def fake_run(command, repo_root, **kwargs):
        seen.extend(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(policy, "_run_command", fake_run)
    monkeypatch.setattr(policy, "_print_process_output", lambda result: None)

    assert policy.run_workflow_local([workflow], tmp_path) == 0
    assert ("--no-full" in seen) is expects_no_full


# --- The bulk partition is the only parallel one -------------------------------


def test_bulk_partition_runs_every_cpu_over_whole_files(tmp_path: Path) -> None:
    bulk, _mutation, _safe_push, _pr_autofix = _pytest_commands_by_partition(tmp_path)

    assert _flag_value(bulk, _WORKER_FLAGS) == "auto"
    assert _flag_value(bulk, _DIST_FLAGS) == policy.PYTEST_DIST_MODE == "loadfile"
    assert bulk[:3] == [sys.executable, "-m", "pytest"]
    assert str(tmp_path / "tests") in bulk


def test_bulk_partition_does_not_hard_code_a_worker_count(tmp_path: Path) -> None:
    """A literal count is wrong on every machine except the one it was measured on.

    This is the inverse of the flag assertion above: a regression that swaps
    ``auto`` for any number still passes "there is a ``-n``" but silently caps a
    48-thread host at whatever the author's laptop had.
    """
    bulk, _mutation, _safe_push, _pr_autofix = _pytest_commands_by_partition(tmp_path)

    workers = _flag_value(bulk, _WORKER_FLAGS)

    assert workers is not None
    assert not workers.lstrip("+-").isdigit(), (
        f"worker count must stay host-relative, got the literal {workers!r}"
    )


def test_process_sensitive_partitions_stay_serial(tmp_path: Path) -> None:
    _bulk, mutation, safe_push, pr_autofix = _pytest_commands_by_partition(tmp_path)

    assert _flag_value(mutation, _WORKER_FLAGS) == "auto"
    assert _flag_value(mutation, _DIST_FLAGS) == "loadfile"
    assert str(tmp_path / "tests" / "mutation") in mutation
    assert _flag_value(safe_push, _WORKER_FLAGS) is None
    assert _flag_value(safe_push, _DIST_FLAGS) is None
    assert str(tmp_path / "tests" / "test_safe_push_pr_branch.py") in safe_push
    assert str(tmp_path / "tests" / "test_mutation_workspace_signals.py") in safe_push
    assert _flag_value(pr_autofix, _WORKER_FLAGS) is None
    assert _flag_value(pr_autofix, _DIST_FLAGS) is None
    assert str(tmp_path / "tests" / "test_pr_autofix_late_live_state_gate.py") in pr_autofix


def test_bulk_and_mutation_pre_push_commands_are_parallel(tmp_path: Path) -> None:
    commands = policy._pytest_commands(tmp_path)

    parallel = [c for c in commands if _flag_value(c, _WORKER_FLAGS) is not None]

    assert parallel == commands[:2]


# --- Worker count: default, override, and rejection ----------------------------


def test_workers_default_to_auto() -> None:
    assert policy.PYTEST_WORKERS_DEFAULT == "auto"
    assert policy.parse_pytest_workers(None) == "auto"


@pytest.mark.parametrize("unset", ["", "   ", "\t\n"])
def test_blank_override_is_treated_as_unset(unset: str) -> None:
    assert policy.parse_pytest_workers(unset) == "auto"


@pytest.mark.parametrize("raw", ["auto", "AUTO", "Auto", " auto ", "\tauto\n"])
def test_auto_override_is_accepted_and_normalized(raw: str) -> None:
    """Accepting ``auto`` explicitly keeps the override honest.

    A developer who pins the default value should get the default behavior
    rather than a config error, and capitalization is not a meaningful choice.
    """
    assert policy.parse_pytest_workers(raw) == "auto"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", "1"), ("2", "2"), ("8", "8"), (" 12 ", "12"), ("+6", "6"), ("04", "4")],
)
def test_positive_integer_override_is_honored(raw: str, expected: str) -> None:
    """Integers round-trip through ``int`` so argv carries a canonical decimal."""
    assert policy.parse_pytest_workers(raw) == expected


@pytest.mark.parametrize("raw", ["0", "-1", "-4", " -2 "])
def test_non_positive_override_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        policy.parse_pytest_workers(raw)

    assert policy.PYTEST_WORKERS_ENV in str(excinfo.value)
    assert repr(raw) in str(excinfo.value)


@pytest.mark.parametrize("raw", ["logical", "4.5", "four", "2x", "0x4", "1,2", "auto2", "half"])
def test_unsupported_override_is_rejected(raw: str) -> None:
    """A typo must not silently become ``auto``.

    ``logical`` is in this list on purpose. xdist accepts it, but this gate
    takes exactly two forms, so a value that means something to pytest and
    nothing to this parser still fails loudly instead of running the whole
    machine while the developer believes they pinned something narrower.
    """
    with pytest.raises(ValueError) as excinfo:
        policy.parse_pytest_workers(raw)

    assert policy.PYTEST_WORKERS_ENV in str(excinfo.value)


def test_default_does_no_arithmetic_on_the_host_cpu_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No subtraction, no cap, no reserved core.

    xdist resolves ``auto`` itself. If this gate ever starts computing a count,
    a stubbed ``os.cpu_count`` leaks into the argv and this fails.
    """
    monkeypatch.setattr(os, "cpu_count", lambda: 64)

    assert policy.parse_pytest_workers(None) == "auto"

    bulk, _mutation, _safe_push, _pr_autofix = _pytest_commands_by_partition(tmp_path)

    assert _flag_value(bulk, _WORKER_FLAGS) == "auto"


def test_env_override_reaches_the_bulk_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(policy.PYTEST_WORKERS_ENV, "8")

    bulk, mutation, safe_push, pr_autofix = _pytest_commands_by_partition(tmp_path)

    assert _flag_value(bulk, _WORKER_FLAGS) == "8"
    assert _flag_value(mutation, _WORKER_FLAGS) == "8"
    assert _flag_value(safe_push, _WORKER_FLAGS) is None, (
        "the override must not make the safe-push partition parallel"
    )
    assert _flag_value(pr_autofix, _WORKER_FLAGS) is None


@pytest.mark.parametrize(("visible_cpus", "expected"), [(1, "1"), (2, "2"), (4, "4"), (64, "4")])
def test_local_worker_cap_never_exceeds_visible_cpus(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    visible_cpus: int,
    expected: str,
) -> None:
    monkeypatch.delenv(policy.PYTEST_WORKERS_ENV, raising=False)
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, "4")
    monkeypatch.setattr(policy, "_visible_cpu_count", lambda: visible_cpus)

    bulk, mutation, _safe_push, _pr_autofix = _pytest_commands_by_partition(tmp_path)

    assert _flag_value(bulk, _WORKER_FLAGS) == expected
    assert _flag_value(mutation, _WORKER_FLAGS) == expected


@pytest.mark.parametrize(("visible_cpus", "expected"), [(2, 2)])
def test_visible_cpu_count_uses_process_affinity(
    monkeypatch: pytest.MonkeyPatch,
    visible_cpus: int | None,
    expected: int,
) -> None:
    monkeypatch.setattr(os, "process_cpu_count", lambda: visible_cpus)

    assert policy._visible_cpu_count() == expected


def test_visible_cpu_count_falls_back_to_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "process_cpu_count", lambda: None)
    monkeypatch.delattr(os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: None)

    assert policy._visible_cpu_count() == 1


def test_visible_cpu_count_uses_sched_affinity_on_python_310(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 10))
    monkeypatch.delattr(os, "process_cpu_count", raising=False)
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: {0, 1}, raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 64)

    assert policy._visible_cpu_count() == 2


def test_explicit_worker_override_wins_over_local_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(policy.PYTEST_WORKERS_ENV, "8")
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, "4")

    bulk, mutation, _safe_push, _pr_autofix = _pytest_commands_by_partition(tmp_path)

    assert _flag_value(bulk, _WORKER_FLAGS) == "8"
    assert _flag_value(mutation, _WORKER_FLAGS) == "8"


@pytest.mark.parametrize("raw", ["", "auto", "0", "-1", "four"])
def test_invalid_local_worker_cap_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    raw: str,
) -> None:
    monkeypatch.delenv(policy.PYTEST_WORKERS_ENV, raising=False)
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, raw)

    if not raw.strip():
        bulk, _mutation, _safe_push, _pr_autofix = _pytest_commands_by_partition(tmp_path)
        assert _flag_value(bulk, _WORKER_FLAGS) == "auto"
        return

    with pytest.raises(ValueError, match=policy.PYTEST_WORKER_CAP_ENV):
        _pytest_commands_by_partition(tmp_path)


def test_run_pytest_consumes_worker_override_before_child_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # This test is about the flags the executing partitions carry, so it opts
    # into local execution. Without the opt-in, `run_pytest` on a tmp_path with
    # no resolvable diff builds the collection stand-in, which takes no worker
    # flags at all and so has nothing to say about worker policy (ADR-104).
    monkeypatch.setenv(policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setenv(policy.PYTEST_WORKERS_ENV, "3")
    monkeypatch.setenv(policy.PYTEST_WORKER_CAP_ENV, "4")
    seen_commands: list[list[str]] = []
    seen_envs: list[dict[str, str]] = []

    def capture_run(
        command: list[str],
        repo_root: Path,
        *,
        process_env: dict[str, str],
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        del repo_root, timeout_seconds
        seen_commands.append(command)
        seen_envs.append(process_env.copy())
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(policy, "_run_command", capture_run)
    monkeypatch.setattr(policy, "_print_process_output", lambda result: None)

    assert policy.run_pytest(tmp_path) == 0

    assert _flag_value(seen_commands[0], _WORKER_FLAGS) == "3"
    assert all(policy.PYTEST_WORKER_CAP_ENV not in env for env in seen_envs)
    assert all(policy.PYTEST_WORKERS_ENV not in env for env in seen_envs)
    # Every control `run_pytest` consumes has to be stripped, not just the two
    # that were there first. The opt-in leaking through makes a child test that
    # invokes this policy take the full-suite path it did not ask for, so the
    # test passes while exercising the wrong branch (PR #5319).
    assert all(policy.PYTEST_FULL_SUITE_LOCALLY_ENV not in env for env in seen_envs), (
        "the full-suite opt-in reached the child environment. A pytest child "
        "that runs this policy again would inherit =1 and skip selection."
    )


def test_unset_env_produces_the_default_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(policy.PYTEST_WORKERS_ENV, raising=False)
    monkeypatch.delenv(policy.PYTEST_WORKER_CAP_ENV, raising=False)

    bulk, _mutation, _safe_push, _pr_autofix = _pytest_commands_by_partition(tmp_path)

    assert _flag_value(bulk, _WORKER_FLAGS) == "auto"


def test_run_pytest_reports_a_config_error_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit code 2 is the AGENTS.md config-error contract.

    The gate must not fall through to a default run: the developer asked for a
    specific worker count and did not get it.
    """
    monkeypatch.setenv(policy.PYTEST_WORKERS_ENV, "logical")
    ran: list[object] = []

    def fail_if_called(*args: object, **kwargs: object) -> None:
        ran.append(args)

    monkeypatch.setattr(policy, "_run_command", fail_if_called)

    assert policy.run_pytest(tmp_path) == 2

    assert ran == []
    stderr = capsys.readouterr().err
    assert policy.PYTEST_WORKERS_ENV in stderr
    assert "'auto' or a positive integer" in stderr


# --- The negative half: no global parallelism ----------------------------------


def test_global_addopts_carries_no_parallel_flags() -> None:
    """``addopts`` reaches every pytest run in the repo, so it must stay serial.

    Verbatim contract as of this commit:
    ``addopts = "-v --tb=short --import-mode=importlib --timeout=120"``.
    Moving ``-n``/``--dist`` here would parallelize the two branch-coverage pin
    steps, the safe-push partition, and every ad-hoc single-file run, none of
    which were measured for it.
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    addopts = data["tool"]["pytest"]["ini_options"]["addopts"]

    for flag in (*_WORKER_FLAGS, *_DIST_FLAGS):
        assert flag not in addopts.split(), (
            f"{flag} must be passed at the call site, not in global addopts"
        )
    assert "-p xdist" not in addopts
