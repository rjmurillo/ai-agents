"""Tests for aggregate_session_verdicts.py consumer script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the consumer script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("aggregate_session_verdicts")
main = _mod.main
build_parser = _mod.build_parser

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_output(tmp_path: Path, monkeypatch) -> Path:
    output_file = tmp_path / "output"
    output_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    return output_file


def _read_outputs(output_file: Path) -> dict[str, str]:
    lines = output_file.read_text().strip().splitlines()
    result = {}
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
    return result


def _create_verdict_file(results_dir: Path, name: str, verdict: str) -> None:
    (results_dir / f"{name}-verdict.txt").write_text(verdict)
    _create_must_file(results_dir, name, "0")


def _create_must_file(results_dir: Path, name: str, content: str) -> None:
    (results_dir / f"{name}-must-failures.txt").write_text(content)


def _run(
    results_dir: Path,
    expected_results: int | None = None,
    expected_artifacts: dict[str, str] | None = None,
) -> int:
    expected = expected_results
    if expected is None:
        expected = max(1, len(list(results_dir.glob("*-verdict.txt"))))
    artifacts = expected_artifacts
    if artifacts is None:
        artifacts = {
            path.name[: -len("-verdict.txt")]: str(
                results_dir.parent / "expected" / f"{path.stem}.json"
            )
            for path in results_dir.glob("*-verdict.txt")
        }
    return main(
        [
            "--results-dir",
            str(results_dir),
            "--expected-results",
            str(expected),
            "--expected-artifacts",
            json.dumps(artifacts),
        ]
    )


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_default_results_dir(self):
        args = build_parser().parse_args([])
        assert args.results_dir == "validation-results"
        assert args.expected_results == 0

    def test_custom_results_dir(self):
        args = build_parser().parse_args(
            [
                "--results-dir",
                "/custom/path",
                "--expected-results",
                "2",
                "--expected-artifacts",
                '{"one":"a.json","two":"b.json"}',
            ]
        )
        assert args.results_dir == "/custom/path"
        assert args.expected_results == 2
        assert args.expected_artifacts == '{"one":"a.json","two":"b.json"}'


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_verdict_files_returns_critical_fail(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        rc = _run(results_dir, expected_results=1)
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_all_pass_returns_pass(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_verdict_file(results_dir, "session-2", "PASS")
        rc = _run(results_dir)
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "PASS"

    def test_critical_fail_verdict_propagates(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_verdict_file(results_dir, "session-2", "CRITICAL_FAIL")
        rc = _run(results_dir)
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_rejected_verdict_propagates(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "REJECTED")
        rc = _run(results_dir)
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_warn_verdict_upgrades_pass_to_warn(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_verdict_file(results_dir, "session-2", "WARN")
        rc = _run(results_dir)
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "WARN"

    def test_skipped_verdict_is_pass_equivalent(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "deleted-session", "SKIPPED")

        assert _run(results_dir) == 0

        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "PASS"

    def test_skipped_existing_session_is_critical_fail(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "sessions-existing", "SKIPPED")
        session_file = tmp_path / "sessions" / "existing.json"
        session_file.parent.mkdir()
        session_file.write_text("{}", encoding="utf-8")

        assert _run(
            results_dir,
            expected_artifacts={"sessions-existing": str(session_file)},
        ) == 0

        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_must_failures_override_to_critical_fail(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_must_file(results_dir, "session-1", "3")
        rc = _run(results_dir)
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"
        assert outputs["must_failures"] == "3"

    def test_zero_must_failures_no_override(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_must_file(results_dir, "session-1", "0")
        rc = _run(results_dir)
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "PASS"

    def test_must_failures_with_text_suffix_is_critical_fail(
        self, tmp_path, monkeypatch
    ):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_must_file(results_dir, "session-1", "2 failures found")
        rc = _run(results_dir)
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"
        assert outputs["must_failures"] == "0"

    def test_non_compliant_verdict_is_critical_fail(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "NON_COMPLIANT")
        rc = _run(results_dir)
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_missing_one_verdict_is_critical_fail(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")

        assert _run(results_dir, expected_results=2) == 0

        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_missing_one_must_file_is_critical_fail(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_verdict_file(results_dir, "session-2", "PASS")
        (results_dir / "session-2-must-failures.txt").unlink()

        assert _run(results_dir, expected_results=2) == 0

        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    @pytest.mark.parametrize("verdict", ["", "UNKNOWN", "FOOBAR"])
    def test_invalid_verdict_is_critical_fail(
        self, tmp_path, monkeypatch, verdict: str
    ):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", verdict)

        assert _run(results_dir) == 0

        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_malformed_must_count_is_critical_fail(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "COMPLIANT")
        _create_must_file(results_dir, "session-1", "0 trailing text")

        assert _run(results_dir) == 0

        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_disjoint_artifact_stems_are_critical_fail(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "COMPLIANT")
        (results_dir / "session-1-must-failures.txt").unlink()
        _create_must_file(results_dir, "session-2", "0")

        assert _run(results_dir, expected_results=1) == 0

        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_unexpected_paired_artifacts_are_critical_fail(
        self, tmp_path, monkeypatch
    ):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "sessions-unexpected", "COMPLIANT")

        assert _run(
            results_dir,
            expected_artifacts={
                "sessions-expected": str(
                    tmp_path / "sessions" / "expected.json"
                )
            },
        ) == 0

        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"
