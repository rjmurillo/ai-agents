"""Tests for the K3 and K4 emission-point wrappers (REQ-008-09).

K3: scripts/metrics/check_vendored_install.py runs the vendored-install
suite and emits K3 on failure. The pytest subprocess boundary is mocked.

K4: scripts/metrics/emit_verdict_mismatch.py compares a local and a CI
verdict and emits K4 on divergence. The emit_event boundary is mocked.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_METRICS_DIR = _PROJECT_ROOT / "scripts" / "metrics"


def _load(module_name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        module_name, _METRICS_DIR / filename
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["pytest"], returncode=returncode, stdout=stdout, stderr=stderr
    )


# --- K3: check_vendored_install ------------------------------------------


def test_k3_no_emit_when_vendored_suite_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load("check_vendored_install", "check_vendored_install.py")
    emitted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module, "_run_vendored_suite", lambda: _fake_completed(0, "5 passed")
    )
    monkeypatch.setattr(
        module, "emit_event", lambda kind, detail: emitted.append((kind, detail))
    )

    rc = module.main()

    assert rc == 0
    assert emitted == []


def test_k3_emitted_when_vendored_suite_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load("check_vendored_install", "check_vendored_install.py")
    emitted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module,
        "_run_vendored_suite",
        lambda: _fake_completed(1, "1 failed, 4 passed"),
    )
    monkeypatch.setattr(
        module, "emit_event", lambda kind, detail: emitted.append((kind, detail))
    )

    rc = module.main()

    assert rc == 1
    assert len(emitted) == 1
    assert emitted[0][0] == "K3"
    assert "vendored install breakage" in emitted[0][1]


def test_k3_returns_three_when_suite_cannot_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load("check_vendored_install", "check_vendored_install.py")
    emitted: list[tuple[str, str]] = []

    def boom() -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("pytest missing")

    monkeypatch.setattr(module, "_run_vendored_suite", boom)
    monkeypatch.setattr(
        module, "emit_event", lambda kind, detail: emitted.append((kind, detail))
    )

    rc = module.main()

    assert rc == 3
    assert emitted == []


# --- K4: emit_verdict_mismatch -------------------------------------------


@pytest.mark.parametrize(
    ("local", "ci"),
    [("PASS", "PASS"), ("PASS", "pass"), ("  WARN ", "warn")],
)
def test_k4_verdicts_match_is_case_and_whitespace_insensitive(
    local: str, ci: str
) -> None:
    module = _load("emit_verdict_mismatch", "emit_verdict_mismatch.py")

    assert module.verdicts_match(local, ci) is True


@pytest.mark.parametrize(
    ("local", "ci"),
    [("PASS", "WARN"), ("WARN", "CRITICAL_FAIL"), ("", "PASS")],
)
def test_k4_verdicts_mismatch_detected(local: str, ci: str) -> None:
    module = _load("emit_verdict_mismatch", "emit_verdict_mismatch.py")

    assert module.verdicts_match(local, ci) is False


def test_k4_no_emit_when_verdicts_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load("emit_verdict_mismatch", "emit_verdict_mismatch.py")
    emitted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module, "emit_event", lambda kind, detail: emitted.append((kind, detail))
    )

    rc = module.main(["--commit", "abc123", "--local", "PASS", "--ci", "pass"])

    assert rc == 0
    assert emitted == []


def test_k4_emitted_when_verdicts_diverge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load("emit_verdict_mismatch", "emit_verdict_mismatch.py")
    emitted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module, "emit_event", lambda kind, detail: emitted.append((kind, detail))
    )

    rc = module.main(["--commit", "abc123", "--local", "PASS", "--ci", "WARN"])

    assert rc == 1
    assert len(emitted) == 1
    assert emitted[0][0] == "K4"
    assert "commit=abc123" in emitted[0][1]
    assert "local=PASS" in emitted[0][1]
    assert "ci=WARN" in emitted[0][1]
