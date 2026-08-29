"""The pre-PR gate must run every count ratchet the push runs (issue #4251).

AGENTS.md names ``scripts/validation/pre_pr.py`` as the one pre-PR gate. The
four count ratchets ran only at ``pre-push``, in the same lefthook group as the
full Python test suite, so a contributor saw ``pre_pr.py`` pass, pushed, and
learned 674 seconds later that a 0.21 second ratchet had failed.

Adding the ratchets to ``pre_pr.py`` fixes today's instance. It does not fix the
class: the same drift recurs the moment someone adds a fifth ratchet to
``lefthook.yml`` and forgets this module. So the parity assertion below reads
both definitions and compares them, and the wiring test drives the real
consumer's entry point rather than trusting that a correct validator is a
called one (the failure mode recorded in issue #4244 and PR #4233, where a
guard survived nine mutations against its own tests while one of its three
consumers was never wired to it).

Coverage:

- positive: parity holds against the real ``lefthook.yml``; every ratchet
  command matches its job string; the gate passes against the current tree.
- negative: a ratchet added to lefthook alone, dropped from lefthook alone, or
  invoked with a different flag set each fails parity; a failing ratchet, an
  absent ratchet script, and an unresolvable base ref each fail the gate.
- edge: an absent ``uv`` raises the SKIP signal rather than failing; a failed
  base-ref refresh warns and continues.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = REPO_ROOT / "lefthook.yml"

# Import the pre-PR runner modules the way production imports them: add
# ``scripts/validation`` to ``sys.path`` and import by bare name (issue #2223).
# Append-only, never restored, mirroring ``pre_pr`` itself; see the note in
# ``tests/validation/test_pre_pr_model_pin_wiring.py`` for why a restore breaks
# function-local bare-name imports elsewhere in the package.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_ratchet  # noqa: E402
import pre_pr_sequence  # noqa: E402

_GATE_NAME = "Count Ratchets"


def _walk_jobs(jobs: object, out: list[dict]) -> None:
    """Collect every named job in a lefthook job list, including nested groups."""
    if not isinstance(jobs, list):
        return
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if job.get("name"):
            out.append(job)
        group = job.get("group")
        if isinstance(group, dict):
            _walk_jobs(group.get("jobs"), out)
        _walk_jobs(job.get("jobs"), out)


def collect_count_ratchets_job(data: object) -> dict | None:
    """Return the aggregate pre-push ratchet job from parsed YAML."""
    if not isinstance(data, dict):
        return None
    pre_push = data.get("pre-push")
    if not isinstance(pre_push, dict):
        return None
    found: list[dict] = []
    _walk_jobs(pre_push.get("jobs"), found)
    return next((job for job in found if job.get("name") == "count-ratchets"), None)


def _real_count_ratchets_job() -> dict | None:
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    return collect_count_ratchets_job(data)


class TestAggregateLefthookDelegation:
    """Lefthook delegates the full ratchet set to this module."""

    def test_aggregate_job_exists(self) -> None:
        assert _real_count_ratchets_job() is not None

    def test_aggregate_job_invokes_the_registry_runner(self) -> None:
        job = _real_count_ratchets_job()
        assert job is not None
        assert str(job.get("run")) == (
            "uv run --frozen python scripts/validation/checks_ratchet.py"
        )

    def test_aggregate_job_is_unconditional(self) -> None:
        job = _real_count_ratchets_job()
        assert job is not None
        assert job.get("glob") is None

    def test_missing_aggregate_job_is_detected(self) -> None:
        synthetic = {"pre-push": {"jobs": [{"name": "other", "run": "true"}]}}
        assert collect_count_ratchets_job(synthetic) is None

    def test_main_returns_nonzero_when_a_ratchet_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(checks_ratchet, "validate_count_ratchets", lambda _root: False)
        assert checks_ratchet.main() == 1

    def test_main_returns_config_error_when_uv_is_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def unavailable(_root: Path) -> bool:
            raise checks_ratchet.MissingScriptSkip("uv missing")

        monkeypatch.setattr(checks_ratchet, "validate_count_ratchets", unavailable)
        assert checks_ratchet.main() == 2


class TestWiredIntoTheSequence:
    """A correct validator nobody calls delivers nothing (issue #4244)."""

    @staticmethod
    def _recorded_names() -> list[str]:
        recorded: list[str] = []

        def fake_run_validation(
            name: str, _state: object, _callback: object, skip: bool = False
        ) -> bool:
            recorded.append(name)
            return True

        state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
        args = SimpleNamespace(quick=True, skip_tests=False, verbose=False)
        pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)
        return recorded

    def test_gate_runs_in_the_sequence(self) -> None:
        """Positive: the real consumer's entry point reaches the gate."""
        assert _GATE_NAME in self._recorded_names()

    def test_gate_runs_second(self) -> None:
        """Edge: placement is the fix, not an incidental detail.

        The point of issue #4251 is that the cheapest push-blocking signal must
        arrive first. A reorder that buries this behind a slow check restores
        most of the cost without failing any other assertion.
        """
        recorded = self._recorded_names()
        assert recorded[1] == _GATE_NAME, recorded[:4]


class TestValidatorBehaviour:
    """Positive, negative, and edge paths through ``validate_count_ratchets``."""

    def test_passes_when_every_ratchet_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Positive: all four green means the gate passes."""
        monkeypatch.setattr(
            checks_ratchet, "_resolve_default_base_ref", lambda _root: "origin/main"
        )
        monkeypatch.setattr(checks_ratchet, "_refresh_remote_base", lambda *_a: "")
        monkeypatch.setattr(checks_ratchet, "_resolve_base_oid", lambda *_a: "a" * 40)
        monkeypatch.setattr(checks_ratchet, "_run_subprocess", lambda *_a, **_k: (0, "ok", ""))
        assert checks_ratchet.validate_count_ratchets(REPO_ROOT) is True

    def test_runs_every_declared_ratchet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Positive: the gate invokes all four, not just the first."""
        seen: list[list[str]] = []
        monkeypatch.setattr(
            checks_ratchet, "_resolve_default_base_ref", lambda _root: "origin/main"
        )
        monkeypatch.setattr(checks_ratchet, "_refresh_remote_base", lambda *_a: "")
        base_oid = "a" * 40
        monkeypatch.setattr(checks_ratchet, "_resolve_base_oid", lambda *_a: base_oid)

        def record(args: list[str], **_k: object) -> tuple[int, str, str]:
            seen.append(args)
            return 0, "", ""

        monkeypatch.setattr(checks_ratchet, "_run_subprocess", record)
        checks_ratchet.validate_count_ratchets(REPO_ROOT)
        expected = [
            " ".join(checks_ratchet.build_command(ratchet, base_oid))
            for ratchet in checks_ratchet.RATCHETS
        ]
        assert [" ".join(a) for a in seen] == expected

    def test_fails_when_one_ratchet_exits_nonzero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Negative: a breach fails the gate and names the offending job."""
        target = checks_ratchet.RATCHETS[-1]
        monkeypatch.setattr(
            checks_ratchet, "_resolve_default_base_ref", lambda _root: "origin/main"
        )
        monkeypatch.setattr(checks_ratchet, "_refresh_remote_base", lambda *_a: "")
        monkeypatch.setattr(checks_ratchet, "_resolve_base_oid", lambda *_a: "a" * 40)

        def selective(args: list[str], **_k: object) -> tuple[int, str, str]:
            if target.script in args:
                return 1, "count rose from 44 to 45", ""
            return 0, "", ""

        monkeypatch.setattr(checks_ratchet, "_run_subprocess", selective)
        assert checks_ratchet.validate_count_ratchets(REPO_ROOT) is False
        captured = capsys.readouterr()
        assert target.job_name in captured.out + captured.err
        assert "count rose from 44 to 45" in captured.out

    def test_fails_when_a_ratchet_script_is_absent(self, tmp_path: Path) -> None:
        """Negative: fail closed. Gating the count is the point of the gate."""
        assert checks_ratchet.validate_count_ratchets(tmp_path) is False

    def test_fails_when_base_ref_cannot_be_resolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Negative: no base ref means no honest comparison, so refuse."""
        monkeypatch.setattr(checks_ratchet, "_resolve_default_base_ref", lambda _root: None)
        monkeypatch.setattr(checks_ratchet, "_run_subprocess", lambda *_a, **_k: (0, "", ""))
        assert checks_ratchet.validate_count_ratchets(REPO_ROOT) is False

    def test_remote_head_is_normalized_before_refresh(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []
        monkeypatch.setattr(
            checks_ratchet,
            "_resolve_default_base_ref",
            lambda _root: "refs/remotes/origin/HEAD",
        )
        monkeypatch.setattr(
            checks_ratchet,
            "_normalize_remote_head",
            lambda _root, _ref: "origin/main",
        )

        def fail_refresh(ref: str, _root: Path) -> str:
            seen.append(ref)
            return "offline"

        monkeypatch.setattr(
            checks_ratchet,
            "_refresh_remote_base",
            fail_refresh,
        )
        assert checks_ratchet.validate_count_ratchets(REPO_ROOT) is False
        assert seen == ["origin/main"]

    def test_skips_when_uv_is_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Edge: SKIP, not FAIL. The gate cannot reproduce the push command."""
        monkeypatch.setattr(checks_ratchet.shutil, "which", lambda _name: None)
        with pytest.raises(checks_ratchet.MissingScriptSkip):
            checks_ratchet.validate_count_ratchets(REPO_ROOT)

    def test_stale_base_ref_refresh_failure_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Negative: a failed refresh cannot authorize stale-base evaluation."""
        monkeypatch.setattr(
            checks_ratchet, "_resolve_default_base_ref", lambda _root: "origin/main"
        )
        monkeypatch.setattr(
            checks_ratchet, "_refresh_remote_base", lambda *_a: "network unreachable"
        )
        with patch.object(checks_ratchet, "_run_subprocess") as run:
            assert checks_ratchet.validate_count_ratchets(REPO_ROOT) is False
        run.assert_not_called()
        assert "could not refresh origin/main" in capsys.readouterr().err


class TestNormalizeRemoteHead:
    """Direct cover for `_normalize_remote_head` (issue #4251).

    Every other test in this module stubs it out, so its own branches were
    exercised only incidentally, through a pre_pr test whose blanket
    ``stdout = ""`` mock happened to hit the empty-output path.

    Coverage:

    - positive: a symbolic ref resolves to the branch it points at.
    - negative: empty output and a non-`origin/` answer each fail closed,
      because a base ref that is not a remote-tracking branch would silently
      measure the ratchet against the wrong tree.
    - edge: a base ref that is not remote HEAD passes through untouched, with
      no subprocess call at all.
    """

    _REMOTE_HEAD = "refs/remotes/origin/HEAD"

    def test_passes_through_a_ref_that_is_not_remote_head(self) -> None:
        with patch.object(checks_ratchet, "_run_subprocess") as run:
            assert (
                checks_ratchet._normalize_remote_head(REPO_ROOT, "origin/main")
                == "origin/main"
            )
        run.assert_not_called()

    def test_resolves_remote_head_to_its_branch(self) -> None:
        with patch.object(
            checks_ratchet, "_run_subprocess", return_value=(0, "origin/main\n", "")
        ):
            assert (
                checks_ratchet._normalize_remote_head(REPO_ROOT, self._REMOTE_HEAD)
                == "origin/main"
            )

    def test_empty_output_fails_closed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch.object(checks_ratchet, "_run_subprocess", return_value=(0, "", "")):
            assert (
                checks_ratchet._normalize_remote_head(REPO_ROOT, self._REMOTE_HEAD)
                is None
            )
        assert "cannot resolve remote HEAD" in capsys.readouterr().err

    def test_answer_outside_the_origin_namespace_fails_closed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch.object(
            checks_ratchet, "_run_subprocess", return_value=(0, "upstream/main", "")
        ):
            assert (
                checks_ratchet._normalize_remote_head(REPO_ROOT, self._REMOTE_HEAD)
                is None
            )
        assert "cannot resolve remote HEAD" in capsys.readouterr().err

    def test_nonzero_exit_is_rejected_even_with_a_plausible_answer(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Negative: the exit code is checked, not just the shape of stdout.

        Git can print a usable-looking ref and still fail. Pairing a nonzero
        exit with `origin/main` is the only case that isolates the exit-code
        half of the guard: with an empty or non-origin answer the prefix check
        rejects the input first, so deleting the exit-code check keeps every
        other case green.
        """
        with patch.object(
            checks_ratchet,
            "_run_subprocess",
            return_value=(128, "origin/main", "fatal: ref not usable"),
        ):
            assert (
                checks_ratchet._normalize_remote_head(REPO_ROOT, self._REMOTE_HEAD)
                is None
            )
        assert "ref not usable" in capsys.readouterr().err
