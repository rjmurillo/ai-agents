"""The `count-ratchets` pre-push subcommand of git_hook_policy (issue #7070).

The job moved behind `git_hook_policy.py` so a managed container bounds it.
These tests pin the handler's contract:

- positive: a passing registry exits 0 and receives the clamped deadline.
- negative: a failing registry exits 1.
- edge: an absent `uv` (MissingScriptSkip) exits 2, matching
  `checks_ratchet.main`; outside a container the deadline is unchanged.
- registry: an explicit deadline reaches the concurrent runner, and None
  falls back to `_AGGREGATE_TIMEOUT_SECONDS` read at call time.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import checks_ratchet
import git_hook_policy
from checks_common import MissingScriptSkip


def _run(argv: list[str]) -> int:
    args = git_hook_policy.build_parser().parse_args(argv)
    return int(args.handler(args))


class TestCountRatchetsHandler:
    def test_passing_registry_exits_zero_with_the_clamped_deadline(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        seen: list[tuple[Path, float | None]] = []

        def fake_validate(root: Path, deadline: float | None = None) -> bool:
            seen.append((root, deadline))
            return True

        monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda _s: 150.0)
        monkeypatch.setattr(checks_ratchet, "validate_count_ratchets", fake_validate)

        assert _run(["--repo-root", str(tmp_path), "count-ratchets"]) == 0
        assert seen == [(tmp_path.resolve(), 150.0)]

    def test_outside_a_container_the_deadline_is_the_registry_constant(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        seen: list[float | None] = []

        def fake_validate(_root: Path, deadline: float | None = None) -> bool:
            seen.append(deadline)
            return True

        monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda s: s)
        monkeypatch.setattr(checks_ratchet, "validate_count_ratchets", fake_validate)

        assert _run(["--repo-root", str(tmp_path), "count-ratchets"]) == 0
        assert seen == [float(checks_ratchet._AGGREGATE_TIMEOUT_SECONDS)]

    def test_failing_registry_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda s: s)
        monkeypatch.setattr(
            checks_ratchet, "validate_count_ratchets", lambda _root, _deadline=None: False
        )

        assert _run(["--repo-root", str(tmp_path), "count-ratchets"]) == 1

    def test_missing_uv_exits_two_and_names_the_cause(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def raise_skip(_root: Path, _deadline: float | None = None) -> bool:
            raise MissingScriptSkip("uv is not on PATH")

        monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda s: s)
        monkeypatch.setattr(checks_ratchet, "validate_count_ratchets", raise_skip)

        assert _run(["--repo-root", str(tmp_path), "count-ratchets"]) == 2
        assert "uv is not on PATH" in capsys.readouterr().err

    def test_the_container_clamp_is_below_the_job_cap(self) -> None:
        """In a container the deadline must fire before the watchdog does."""
        clamped = min(
            float(checks_ratchet._AGGREGATE_TIMEOUT_SECONDS),
            git_hook_policy.CONTAINER_SUBPROCESS_CEILING_SECONDS,
        )
        assert clamped < git_hook_policy.CONTAINER_PROCESS_CEILING_SECONDS


class TestRegistryDeadlineParameter:
    @pytest.fixture
    def stubbed(self, monkeypatch: pytest.MonkeyPatch) -> list[float]:
        monkeypatch.setattr(checks_ratchet.shutil, "which", lambda _name: "/usr/bin/uv")
        monkeypatch.setattr(checks_ratchet, "_prepare_base_oid", lambda _root: "a" * 40)
        deadlines: list[float] = []

        def fake_run(_root: Path, _oid: str, deadline_seconds: float) -> dict:
            deadlines.append(deadline_seconds)
            return {r.job_name: (0, "", "") for r in checks_ratchet.RATCHETS}

        monkeypatch.setattr(checks_ratchet, "_run_ratchets", fake_run)
        return deadlines

    def test_explicit_deadline_reaches_the_runner(self, stubbed: list[float]) -> None:
        assert checks_ratchet.validate_count_ratchets(REPO_ROOT, 42.0) is True
        assert stubbed == [42.0]

    def test_none_falls_back_to_the_patched_constant(
        self, stubbed: list[float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(checks_ratchet, "_AGGREGATE_TIMEOUT_SECONDS", 7)
        assert checks_ratchet.validate_count_ratchets(REPO_ROOT) is True
        assert stubbed == [7]
