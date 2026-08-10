"""Where bounded pytest-xdist parallelism may be applied, and where it must not.

Issue #4823. The pre-push gate runs the suite in two partitions
(``scripts/validation/git_hook_policy.py::_pytest_commands``). Exactly one of
them, the bulk ``not integration`` partition, runs on workers. Everything else
in the repository stays serial:

* the safe-push partition (second pre-push command), which targets one module;
* the two branch-coverage pin steps and the Windows path-contract step in
  ``.github/workflows/pytest.yml`` (asserted in
  ``tests/workflows/test_pytest_xdist_parallelism.py``, which owns the CI half
  of this contract).

The mechanism that keeps those serial is negative: ``-n`` and ``--dist`` are
passed at the call site, never in ``[tool.pytest.ini_options].addopts``. Global
addopts reach every pytest invocation in the repo, so a single ``-n 4`` there
would silently parallelize the pins, the safe-push partition, and every ad-hoc
``pytest tests/foo.py`` a developer runs. ``test_global_addopts_carries_no_``
``parallel_flags`` is the guard on that.

Worker count is a measured constant, four, not a function of the host. Issue
#4491's closing comment ruled out ``-n auto`` for this gate: several concurrent
pushes on one shared machine each scale to the full CPU count, so contention
gets worse rather than better. ``AI_AGENTS_PYTEST_WORKERS`` exists only so a
developer can re-measure locally.
"""

from __future__ import annotations

import os
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

    Handles both the space-separated (``-n 4``) and inline (``--dist=loadfile``)
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


def _bulk_and_safe_push_commands(repo_root: Path) -> tuple[list[str], list[str]]:
    commands = policy._pytest_commands(repo_root)
    assert len(commands) == 2, f"expected two pre-push pytest commands, got {commands}"
    return commands[0], commands[1]


# --- The bulk partition is the only parallel one -------------------------------


def test_bulk_partition_runs_four_workers_over_whole_files(tmp_path: Path) -> None:
    bulk, _safe_push = _bulk_and_safe_push_commands(tmp_path)

    assert _flag_value(bulk, _WORKER_FLAGS) == "4"
    assert _flag_value(bulk, _DIST_FLAGS) == policy.PYTEST_DIST_MODE == "loadfile"
    assert bulk[:3] == [sys.executable, "-m", "pytest"]
    assert str(tmp_path / "tests") in bulk


def test_bulk_partition_never_asks_the_host_how_many_workers_to_use(
    tmp_path: Path,
) -> None:
    """``-n auto`` is out of scope for this gate (issue #4491's closing decision).

    The literal string is the regression this guards: ``-n auto`` reads the
    host CPU count, so N concurrent pushes on one machine request N times the
    cores and collapse into contention.
    """
    bulk, _safe_push = _bulk_and_safe_push_commands(tmp_path)

    assert "auto" not in bulk
    assert _flag_value(bulk, _WORKER_FLAGS) != "auto"


def test_safe_push_partition_stays_serial(tmp_path: Path) -> None:
    """The second command targets exactly one module.

    ``--dist loadfile`` routes a whole file to a single worker, so distributing
    a one-file partition buys no parallelism and pays worker startup anyway.
    """
    _bulk, safe_push = _bulk_and_safe_push_commands(tmp_path)

    assert _flag_value(safe_push, _WORKER_FLAGS) is None
    assert _flag_value(safe_push, _DIST_FLAGS) is None
    assert str(tmp_path / "tests" / "test_safe_push_pr_branch.py") in safe_push


def test_exactly_one_pre_push_command_is_parallel(tmp_path: Path) -> None:
    commands = policy._pytest_commands(tmp_path)

    parallel = [c for c in commands if _flag_value(c, _WORKER_FLAGS) is not None]

    assert len(parallel) == 1, f"exactly one partition may be parallel, got {commands}"


# --- Worker count: default, override, and rejection ----------------------------


def test_worker_count_defaults_to_the_measured_four() -> None:
    assert policy.PYTEST_WORKER_COUNT_DEFAULT == 4
    assert policy.parse_pytest_worker_count(None) == 4


@pytest.mark.parametrize("unset", ["", "   ", "\t\n"])
def test_blank_override_is_treated_as_unset(unset: str) -> None:
    assert policy.parse_pytest_worker_count(unset) == 4


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", 1), ("2", 2), ("8", 8), (" 12 ", 12), ("+6", 6), ("04", 4)],
)
def test_positive_integer_override_is_honored(raw: str, expected: int) -> None:
    assert policy.parse_pytest_worker_count(raw) == expected


@pytest.mark.parametrize("raw", ["0", "-1", "-4", " -2 "])
def test_non_positive_override_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        policy.parse_pytest_worker_count(raw)

    assert policy.PYTEST_WORKER_COUNT_ENV in str(excinfo.value)
    assert repr(raw) in str(excinfo.value)


@pytest.mark.parametrize("raw", ["auto", "logical", "4.5", "four", "2x", "0x4", "1,2"])
def test_non_integer_override_is_rejected(raw: str) -> None:
    """A typo must not silently become the default.

    The variable exists to measure a worker count other than four. Falling back
    would report a four-worker run as the calibration the developer asked for,
    which is the one wrong answer that looks right.
    """
    with pytest.raises(ValueError) as excinfo:
        policy.parse_pytest_worker_count(raw)

    assert policy.PYTEST_WORKER_COUNT_ENV in str(excinfo.value)


def test_default_ignores_the_host_cpu_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "cpu_count", lambda: 64)

    assert policy.parse_pytest_worker_count(None) == 4


def test_env_override_reaches_the_bulk_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(policy.PYTEST_WORKER_COUNT_ENV, "8")

    bulk, safe_push = _bulk_and_safe_push_commands(tmp_path)

    assert _flag_value(bulk, _WORKER_FLAGS) == "8"
    assert _flag_value(safe_push, _WORKER_FLAGS) is None, (
        "the override must not make the safe-push partition parallel"
    )


def test_unset_env_produces_the_default_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(policy.PYTEST_WORKER_COUNT_ENV, raising=False)

    bulk, _safe_push = _bulk_and_safe_push_commands(tmp_path)

    assert _flag_value(bulk, _WORKER_FLAGS) == "4"


def test_run_pytest_reports_a_config_error_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit code 2 is the AGENTS.md config-error contract.

    The gate must not fall through to a four-worker run: the developer asked
    for a different measurement and did not get it.
    """
    monkeypatch.setenv(policy.PYTEST_WORKER_COUNT_ENV, "auto")
    ran: list[object] = []

    def fail_if_called(*args: object, **kwargs: object) -> None:
        ran.append(args)

    monkeypatch.setattr(policy, "_run_command", fail_if_called)

    assert policy.run_pytest(tmp_path) == 2

    assert ran == []
    stderr = capsys.readouterr().err
    assert policy.PYTEST_WORKER_COUNT_ENV in stderr
    assert "positive integer" in stderr


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
