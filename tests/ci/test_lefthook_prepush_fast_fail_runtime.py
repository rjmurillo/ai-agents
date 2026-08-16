"""Runtime scheduling semantics behind the pre-push fast-fail staging (issue #5066).

Split from ``test_lefthook_prepush_fast_fail.py`` along the structural/runtime
seam to hold the file-size taste rule; that module pins the committed
``lefthook.yml`` shape, this one drives the real lefthook binary against a
fixture repository to pin the two scheduling facts the staging relies on:

1. A failure inside a ``parallel: true`` group under a ``piped: true`` hook
   skips every later top-level entry.
2. A top-level ``use_stdin: true`` job placed after groups still receives the
   full ref-update payload, which is why security-scan can sit between the
   stages without violating ci-scripts.md MUST-21 (no ``use_stdin`` inside a
   ``parallel: true`` group).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_LEFTHOOK_BIN = shutil.which("lefthook")

# lefthook executes `run:` strings through sh even on Windows, where a native
# sys.executable path has its backslashes eaten. as_posix() is a no-op on
# POSIX (same rationale as tests/test_lefthook_integration.py, refs #3289).
_PYTHON_POSIX = Path(sys.executable).as_posix()

_requires_lefthook = pytest.mark.skipif(
    _LEFTHOOK_BIN is None, reason="requires the lefthook binary"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _write_fixture_repo(
    repo: Path,
    fail_fast_stage: bool,
    fail_stdin_gate: bool = False,
) -> None:
    """Build a minimal repo whose pre-push mirrors the staged shape.

    ``marker.py`` appends its argument to ``jobs.log`` so the test can read
    which jobs ran; ``capture.py`` copies stdin to a file so the test can
    read what payload a stdin consumer received. The fixture carries both
    fast-stage halves: a piped stdin group first (mirroring the cheap
    ref-payload policies), then a parallel group (mirroring the ratchets).
    """
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.com")
    # O_APPEND, one short write per process: atomic on POSIX for writes under
    # PIPE_BUF, so two parallel jobs cannot lose each other's entry the way a
    # read-modify-write can (observed once as a lost `fast-peer` line under
    # full-suite contention).
    (repo / "marker.py").write_text(
        "import sys\n"
        "with open('jobs.log', 'a', encoding='utf-8') as log:\n"
        "    log.write(sys.argv[1] + '\\n')\n"
        "sys.exit(int(sys.argv[2]) if len(sys.argv) > 2 else 0)\n",
        encoding="utf-8",
        newline="\n",
    )
    (repo / "capture.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(sys.stdin.read())\n"
        "sys.exit(int(sys.argv[2]) if len(sys.argv) > 2 else 0)\n",
        encoding="utf-8",
        newline="\n",
    )
    fast_exit = "1" if fail_fast_stage else "0"
    stdin_exit = "1" if fail_stdin_gate else "0"
    config = {
        "pre-push": {
            "piped": True,
            "jobs": [
                {
                    "group": {
                        "piped": True,
                        "jobs": [
                            {
                                "name": "stdin-gate",
                                "run": (
                                    f'"{_PYTHON_POSIX}" capture.py '
                                    f"stdin-gate.txt {stdin_exit}"
                                ),
                                "use_stdin": True,
                            },
                        ],
                    }
                },
                {
                    "group": {
                        "parallel": True,
                        "jobs": [
                            {
                                "name": "fast-gate",
                                "run": f'"{_PYTHON_POSIX}" marker.py fast-gate {fast_exit}',
                            },
                            {
                                "name": "fast-peer",
                                "run": f'"{_PYTHON_POSIX}" marker.py fast-peer',
                            },
                        ],
                    }
                },
                {
                    "name": "late-stdin",
                    "run": f'"{_PYTHON_POSIX}" capture.py payload.txt',
                    "use_stdin": True,
                },
                {
                    "group": {
                        "parallel": True,
                        "jobs": [
                            {
                                "name": "expensive",
                                "run": f'"{_PYTHON_POSIX}" marker.py expensive',
                            }
                        ],
                    }
                },
            ],
        }
    }
    (repo / "lefthook.yml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8", newline="\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")


# Two ref updates, the shape `git push origin a b` hands the hook. Every
# serialized stdin consumer must receive both lines.
_REF_PAYLOAD = (
    "refs/heads/main aaaa refs/heads/main bbbb\n"
    "refs/heads/next cccc refs/heads/next dddd\n"
)


def _run_fixture_hook(repo: Path) -> subprocess.CompletedProcess[str]:
    assert _LEFTHOOK_BIN is not None
    return subprocess.run(
        [_LEFTHOOK_BIN, "run", "pre-push"],
        cwd=repo,
        input=_REF_PAYLOAD,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


@_requires_lefthook
class TestRuntimeFastFail:
    """Pin the lefthook semantics the staged config relies on."""

    def test_a_fast_stage_failure_skips_the_later_entries(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _write_fixture_repo(repo, fail_fast_stage=True)

        result = _run_fixture_hook(repo)

        assert result.returncode != 0
        ran = (repo / "jobs.log").read_text(encoding="utf-8").splitlines()
        assert "fast-gate" in ran, "the failing gate itself must have run"
        assert "expensive" not in ran, (
            "a fast-stage failure must skip the expensive group; lefthook "
            "no longer pipes group failures and the staging is broken:\n"
            f"{result.stdout}\n{result.stderr}"
        )
        assert not (repo / "payload.txt").exists(), (
            "the later top-level stdin job must be skipped too"
        )

    def test_a_stdin_gate_failure_skips_the_later_entries(self, tmp_path: Path) -> None:
        # The other fast-stage half: the piped stdin group (push-ref-policy,
        # session-json-validation and friends in the real config) must also
        # abort everything downstream when it fails.
        repo = tmp_path / "repo"
        _write_fixture_repo(repo, fail_fast_stage=False, fail_stdin_gate=True)

        result = _run_fixture_hook(repo)

        assert result.returncode != 0
        assert (repo / "stdin-gate.txt").exists(), (
            "the failing stdin gate itself must have run"
        )
        assert not (repo / "jobs.log").exists(), (
            "a stdin-group failure must skip the parallel fast group and the "
            f"expensive group:\n{result.stdout}\n{result.stderr}"
        )
        assert not (repo / "payload.txt").exists(), (
            "the later top-level stdin job must be skipped too"
        )

    def test_a_clean_fast_stage_lets_everything_run_with_full_stdin(
        self, tmp_path: Path
    ) -> None:
        # Positive control: without it, the tests above pass on a harness
        # where nothing after the first group ever runs.
        repo = tmp_path / "repo"
        _write_fixture_repo(repo, fail_fast_stage=False)

        result = _run_fixture_hook(repo)

        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        ran = (repo / "jobs.log").read_text(encoding="utf-8").splitlines()
        assert {"fast-gate", "fast-peer", "expensive"} <= set(ran)
        # Both serialized stdin consumers, one inside the piped group and one
        # at the top level after a parallel group, must receive the full
        # multi-line ref-update payload; security-scan depends on this.
        for consumer in ("stdin-gate.txt", "payload.txt"):
            payload = (repo / consumer).read_text(encoding="utf-8")
            assert payload == _REF_PAYLOAD, (
                f"{consumer} received a truncated or reordered payload"
            )
