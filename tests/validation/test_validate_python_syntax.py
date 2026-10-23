"""Tests for scripts/validation/validate_python_syntax.py (issue #2655).

Pins behaviour of the floor-aware parse gate that prevents the PR #2640
regression: PEP 758 ``except A, B:`` syntax is valid on the 3.14 dev target but
a ``SyntaxError`` on the 3.10-3.13 hosts the CLI may run under, so the gate must
parse against the declared support floor, not the host interpreter.

- pos: a tree that parses at the floor returns exit 0
- neg (floor): the exact regression shape (PEP 758 except) is rejected at the
  floor even though the host interpreter (3.14) would accept it
- neg (classic): an always-invalid syntax error is rejected
- edge: an invalid repo root returns exit 2 (config error per ADR-035)
- branch: the git-unavailable filesystem-walk fallback skips vendored dirs
- parallel (issue #6734): a tree large enough to fan out across worker
  interpreters yields the same failures, in the same order, as the serial path;
  a worker failure falls back to the serial verdict
- floor: ``support_floor`` returns the fixed hook-portability floor, and the
  gate stays at that floor even when ``requires-python`` is higher (issue #3008)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "validate_python_syntax.py"
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import validate_python_syntax as syntax_gate
from validate_python_syntax import (
    _read_python_source,
    _tracked_python_files,
    _walk_python_files,
    find_syntax_errors,
    support_floor,
    validate_python_syntax,
)

# PEP 758: valid on Python 3.14, SyntaxError on 3.13 and earlier.
_PEP758 = "try:\n    x = 1\nexcept OSError, ValueError:\n    pass\n"
# Always invalid on every Python 3.
_CLASSIC = "def broken(:\n    pass\n"
# Floor-clean equivalent.
_CLEAN = "try:\n    x = 1\nexcept (OSError, ValueError):\n    pass\n"

_FLOOR_310 = 'requires-python = ">=3.10"\n'


def _git_repo(root: Path) -> None:
    """Initialise a git repo and stage everything so git ls-files sees it."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)


def _run_cli(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(repo_root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_floor_clean_tree_passes(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    (tmp_path / "ok.py").write_text(_CLEAN, encoding="utf-8")
    _git_repo(tmp_path)

    result = _run_cli(tmp_path)

    assert result.returncode == 0, result.stderr
    assert find_syntax_errors(tmp_path) == []


def test_pep758_rejected_at_floor(tmp_path: Path) -> None:
    # Guards against the exact regression: valid on the 3.14 host running this
    # test, but the gate must reject it because the floor is 3.10.
    (tmp_path / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    (tmp_path / "broken.py").write_text(_PEP758, encoding="utf-8")
    _git_repo(tmp_path)

    result = _run_cli(tmp_path)

    assert result.returncode == 1
    assert "broken.py" in result.stderr
    assert "except expressions without parentheses" in result.stderr


def test_classic_syntax_error_rejected(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    (tmp_path / "classic.py").write_text(_CLASSIC, encoding="utf-8")
    _git_repo(tmp_path)

    failures = find_syntax_errors(tmp_path)

    assert any(p.name == "classic.py" for p, _ in failures)


def test_tracked_file_deleted_from_worktree_is_parsed_from_index(
    tmp_path: Path,
) -> None:
    deleted = tmp_path / "deleted.py"
    deleted.write_text(_CLEAN, encoding="utf-8")
    _git_repo(tmp_path)
    deleted.unlink()

    assert find_syntax_errors(tmp_path) == []


def test_index_read_has_a_bounded_git_timeout(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing.py"

    def timeout_git(command: list[str], **kwargs: Any) -> None:
        assert kwargs["timeout"] == 10
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout_git)

    with pytest.raises(subprocess.TimeoutExpired):
        _read_python_source(tmp_path, missing)


def test_tracked_file_discovery_has_a_bounded_git_timeout(tmp_path: Path, monkeypatch) -> None:
    def timeout_git(command: list[str], **kwargs: Any) -> None:
        assert command[-2:] == ["ls-files", "*.py"]
        assert kwargs["timeout"] == 10
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout_git)

    with pytest.raises(RuntimeError, match="git ls-files timed out"):
        _tracked_python_files(tmp_path)


def test_staged_broken_file_missing_from_worktree_is_rejected(
    tmp_path: Path,
) -> None:
    broken = tmp_path / "broken.py"
    broken.write_text(_CLASSIC, encoding="utf-8")
    _git_repo(tmp_path)
    broken.unlink()

    failures = find_syntax_errors(tmp_path)

    assert any(path.name == "broken.py" for path, _ in failures)


def test_git_discovery_failure_falls_back_to_worktree_walk(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tracked = tmp_path / "fallback.py"
    tracked.write_text(_CLEAN, encoding="utf-8")

    def fail_git(*args: Any, **kwargs: Any) -> None:
        raise OSError("git unavailable")

    monkeypatch.setattr(subprocess, "run", fail_git)

    assert find_syntax_errors(tmp_path) == []


def test_invalid_repo_root_returns_config_error(tmp_path: Path) -> None:
    result = _run_cli(tmp_path / "does-not-exist")

    assert result.returncode == 2


def test_walk_fallback_skips_vendored_and_finds_broken(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text(_PEP758, encoding="utf-8")
    vendored = tmp_path / ".venv" / "lib"
    vendored.mkdir(parents=True)
    (vendored / "alsobroken.py").write_text(_PEP758, encoding="utf-8")

    found = {p.name for p in _walk_python_files(tmp_path)}

    assert "broken.py" in found
    assert "alsobroken.py" not in found


def test_support_floor_is_hook_portability_floor() -> None:
    # The gate floor is the fixed hook-execution portability floor, not the
    # pyproject install contract. It ignores repo state entirely.
    assert support_floor() == (3, 10)


def test_floor_independent_of_requires_python(tmp_path: Path) -> None:
    # Regression guard for issue #3008: raising requires-python (here 3.14) must
    # NOT relax the gate. PEP 758 stays rejected because the hook-portability
    # floor is pinned independently of the install contract.
    (tmp_path / "pyproject.toml").write_text('requires-python = ">=3.14"\n', encoding="utf-8")
    (tmp_path / "broken.py").write_text(_PEP758, encoding="utf-8")
    _git_repo(tmp_path)

    result = _run_cli(tmp_path)

    assert result.returncode == 1
    assert "broken.py" in result.stderr
    assert "except expressions without parentheses" in result.stderr


def test_validate_function_returns_false_on_floor_violation(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    (tmp_path / "broken.py").write_text(_PEP758, encoding="utf-8")
    _git_repo(tmp_path)

    assert validate_python_syntax(tmp_path) is False


def test_repo_itself_parses_at_floor() -> None:
    # The live repository must pass its own gate.
    assert find_syntax_errors(REPO_ROOT) == []


def _mixed_tree(root: Path) -> list[str]:
    """Build a tree where good and bad files interleave; return bad names in order.

    Ten files so a round-robin deal over three workers puts failures in every
    shard at non-adjacent positions. A reassembly bug would misattribute them.
    """
    (root / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    plan = {
        "f00_ok.py": _CLEAN,
        "f01_pep758.py": _PEP758,
        "f02_ok.py": _CLEAN,
        "f03_ok.py": _CLEAN,
        "f04_classic.py": _CLASSIC,
        "f05_pep758.py": _PEP758,
        "f06_ok.py": _CLEAN,
        "f07_ok.py": _CLEAN,
        "f08_ok.py": _CLEAN,
        "f09_classic.py": _CLASSIC,
    }
    for name, text in plan.items():
        (root / name).write_text(text, encoding="utf-8")
    (root / "f10_notutf8.py").write_bytes(b"x = '\xff'\n")
    _git_repo(root)
    (root / "f05_pep758.py").unlink()  # still indexed, parsed from the index
    return [
        "f01_pep758.py",
        "f04_classic.py",
        "f05_pep758.py",
        "f09_classic.py",
        "f10_notutf8.py",
    ]


@pytest.fixture
def fan_out(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Force the worker path on a small tree; record each fan-out width."""
    widths: list[int] = []
    real = syntax_gate._parse_in_workers

    def spy(items: list[tuple[str, str]], floor: tuple[int, int], workers: int):
        widths.append(workers)
        return real(items, floor, workers)

    monkeypatch.setattr(syntax_gate, "_PARALLEL_MIN_FILES", 2)
    monkeypatch.setattr(os, "process_cpu_count", lambda: 3)
    monkeypatch.setattr(syntax_gate, "_parse_in_workers", spy)
    return widths


def test_parallel_matches_serial_on_mixed_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fan_out: list[int]
) -> None:
    expected_names = _mixed_tree(tmp_path)

    parallel = find_syntax_errors(tmp_path)
    assert fan_out == [3], "the worker path never ran, so this test proves nothing"

    monkeypatch.setattr(syntax_gate, "_PARALLEL_MIN_FILES", 10_000)
    serial = find_syntax_errors(tmp_path)
    assert fan_out == [3], "serial run must not fan out"

    assert parallel == serial
    assert [p.name for p, _ in parallel] == expected_names
    by_name = {p.name: m for p, m in parallel}
    assert "except expressions without parentheses" in by_name["f01_pep758.py"]
    assert "except expressions without parentheses" in by_name["f05_pep758.py"]
    assert by_name["f10_notutf8.py"].startswith("read error:")


def test_parallel_workers_parse_at_the_floor_not_the_host(
    tmp_path: Path, fan_out: list[int]
) -> None:
    # A worker that fell back to the host grammar (3.14) would accept PEP 758.
    (tmp_path / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    for index in range(4):
        (tmp_path / f"ok{index}.py").write_text(_CLEAN, encoding="utf-8")
    (tmp_path / "late.py").write_text(_PEP758, encoding="utf-8")
    _git_repo(tmp_path)

    failures = find_syntax_errors(tmp_path)

    assert fan_out == [3]
    assert [p.name for p, _ in failures] == ["late.py"]


def test_parallel_clean_tree_passes(tmp_path: Path, fan_out: list[int]) -> None:
    (tmp_path / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    for index in range(6):
        (tmp_path / f"ok{index}.py").write_text(_CLEAN, encoding="utf-8")
    _git_repo(tmp_path)

    assert find_syntax_errors(tmp_path) == []
    assert fan_out == [3]
    assert validate_python_syntax(tmp_path) is True


@pytest.mark.parametrize("failure", ["oserror", "crash", "short", "garbage"])
def test_worker_failure_falls_back_to_the_serial_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fan_out: list[int], failure: str
) -> None:
    expected_names = _mixed_tree(tmp_path)

    def broken_worker(payload: str) -> list[str | None]:
        if failure == "oserror":
            raise OSError("cannot start interpreter")
        if failure == "crash":
            raise subprocess.CalledProcessError(1, ["python"])
        if failure == "short":
            return []
        raise json.JSONDecodeError("bad", "", 0)

    monkeypatch.setattr(syntax_gate, "_run_parse_worker", broken_worker)

    failures = find_syntax_errors(tmp_path)

    assert fan_out == [3]
    assert [p.name for p, _ in failures] == expected_names


def test_small_tree_stays_in_process(tmp_path: Path, fan_out: list[int], monkeypatch) -> None:
    monkeypatch.setattr(syntax_gate, "_PARALLEL_MIN_FILES", 256)
    (tmp_path / "broken.py").write_text(_PEP758, encoding="utf-8")
    _git_repo(tmp_path)

    assert [p.name for p, _ in find_syntax_errors(tmp_path)] == ["broken.py"]
    assert fan_out == []


@pytest.mark.parametrize(
    ("files", "cpus", "expected"),
    [
        (10, 8, 1),
        (255, 8, 1),
        (256, 8, 8),
        (256, 1, 1),
        (10_000, 128, 32),
        (256, None, 1),
    ],
)
def test_worker_count(
    monkeypatch: pytest.MonkeyPatch, files: int, cpus: int | None, expected: int
) -> None:
    monkeypatch.setattr(os, "process_cpu_count", lambda: cpus)

    assert syntax_gate._worker_count(files) == expected


def test_worker_entry_point_reports_floor_violations() -> None:
    payload = json.dumps(
        {
            "floor": [3, 10],
            "items": [["ok.py", _CLEAN], ["pep758.py", _PEP758], ["bad.py", _CLASSIC]],
        }
    )

    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--parse-worker"],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    messages = json.loads(result.stdout)
    assert messages[0] is None
    assert "except expressions without parentheses" in messages[1]
    assert messages[2] is not None
