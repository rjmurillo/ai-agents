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


def collect_ratchet_jobs(data: object) -> dict[str, str]:
    """Map ``pre-push`` job name to ``run`` string for every ``*-ratchet`` job.

    Takes parsed YAML rather than reading the file so the negative controls can
    feed synthetic trees through the same code path the positive test uses.
    """
    if not isinstance(data, dict):
        return {}
    pre_push = data.get("pre-push")
    if not isinstance(pre_push, dict):
        return {}
    found: list[dict] = []
    _walk_jobs(pre_push.get("jobs"), found)
    return {
        job["name"]: str(job.get("run", ""))
        for job in found
        if str(job["name"]).endswith("-ratchet")
    }


def _real_ratchet_jobs() -> dict[str, str]:
    return collect_ratchet_jobs(yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8")))


def _declared_commands() -> dict[str, str]:
    """Map job name to the command string ``checks_ratchet`` would run."""
    return {
        ratchet.job_name: " ".join(checks_ratchet.build_command(ratchet, "origin/main"))
        for ratchet in checks_ratchet.RATCHETS
    }


class TestParityWithLefthook:
    """The two definitions of "which ratchets gate a push" must agree."""

    def test_lefthook_declares_ratchet_jobs(self) -> None:
        """Guard the guard: an empty parse would make every parity test vacuous."""
        assert _real_ratchet_jobs(), (
            "No *-ratchet jobs found under pre-push in lefthook.yml. Either the "
            "jobs were removed or the traversal broke; every parity assertion "
            "below passes vacuously until this does."
        )

    def test_job_names_match(self) -> None:
        """Positive: lefthook's ratchet set equals the set the pre-PR gate runs."""
        assert set(_real_ratchet_jobs()) == {r.job_name for r in checks_ratchet.RATCHETS}

    def test_commands_match(self) -> None:
        """Positive: each command matches its job string flag for flag.

        Catches the subtler half of the drift. Both sides can name the same four
        jobs while one drops ``--extra dev`` (the ruff ratchets shell out to a
        bare ``ruff``, so without it the gate reports "command not found", a
        false failure) or ``--base-ref`` (which silently changes what the count
        is measured against).
        """
        assert _declared_commands() == _real_ratchet_jobs()

    def test_detects_a_ratchet_added_to_lefthook_only(self) -> None:
        """Negative control: the exact drift this parity test exists to catch."""
        synthetic = {
            "pre-push": {
                "jobs": [{"name": name, "run": run} for name, run in _real_ratchet_jobs().items()]
                + [{"name": "new-count-ratchet", "run": "uv run --frozen python x.py"}]
            }
        }
        assert set(collect_ratchet_jobs(synthetic)) != {r.job_name for r in checks_ratchet.RATCHETS}

    def test_detects_a_ratchet_dropped_from_lefthook(self) -> None:
        """Negative control: drift in the other direction is caught too."""
        jobs = list(_real_ratchet_jobs().items())[1:]
        synthetic = {"pre-push": {"jobs": [{"name": n, "run": r} for n, r in jobs]}}
        assert set(collect_ratchet_jobs(synthetic)) != {r.job_name for r in checks_ratchet.RATCHETS}

    def test_detects_a_changed_flag_set(self) -> None:
        """Negative control: same names, different flags, still caught."""
        mutated = {
            name: run.replace(" --extra dev", "").replace(" --base-ref origin/main", "")
            for name, run in _real_ratchet_jobs().items()
        }
        assert _declared_commands() != mutated

    def test_a_commented_out_job_is_not_counted(self) -> None:
        """Edge: YAML parsing, not text search, so a commented job disappears.

        A substring search over raw YAML treats a commented-out job as present.
        Parsing means the key is simply gone, which is what parity should see.
        """
        text = _LEFTHOOK.read_text(encoding="utf-8")
        assert "taste-count-ratchet" in text
        commented = "\n".join(
            f"# {line}" if "taste-count-ratchet" in line else line for line in text.splitlines()
        )
        assert "taste-count-ratchet" not in collect_ratchet_jobs(yaml.safe_load(commented))


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
