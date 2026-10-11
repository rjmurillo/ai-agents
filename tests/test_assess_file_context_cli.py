"""Per-file threshold context through the assess.py CLI (issue #6166).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ruff: noqa: E402
from assess_file_context_helpers import CONFIG, ChangedFile, FileAssessment, assess_main, assessment


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    assessment: FileAssessment,
    *extra: str,
    regression: bool,
) -> int:
    cfg = tmp_path / "qualityrc.json"
    cfg.write_text(json.dumps(CONFIG), encoding="utf-8")
    path = Path(assessment.file_path)
    argv = ["--target", ".", "--format", "json", "--config", str(cfg), *extra]
    if regression:
        argv += ["--changed-only", "--base", "origin/main"]
        monkeypatch.setattr(
            "assess.get_changed_files",
            lambda *_a, **_k: [ChangedFile("A", None, path)],
        )
        monkeypatch.setattr("assess.resolve_comparison_base", lambda base: base)
    monkeypatch.setattr("assess.get_files_to_assess", lambda *_a: [path])
    monkeypatch.setattr("assess.assess_file", lambda *_a: assessment)
    return assess_main(argv)


class TestCli:
    @pytest.mark.parametrize("regression", [False, True])
    def test_new_test_file_passes_without_context_flag(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, regression: bool
    ) -> None:
        a = assessment("tests/test_new.py", "test")
        assert _run_main(monkeypatch, tmp_path, a, regression=regression) == 0

    @pytest.mark.parametrize("regression", [False, True])
    def test_explicit_production_still_fails_test_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, regression: bool
    ) -> None:
        a = assessment("tests/test_new.py", "test")
        rc = _run_main(monkeypatch, tmp_path, a, "--context", "production", regression=regression)
        assert rc == 11

    @pytest.mark.parametrize("regression", [False, True])
    def test_authored_file_fails_without_context_flag(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, regression: bool
    ) -> None:
        a = assessment("src/mod.py", "authored")
        assert _run_main(monkeypatch, tmp_path, a, regression=regression) == 11

    @pytest.mark.parametrize("bad", ["prod", "Test", ""])
    def test_invalid_context_is_rejected(self, bad: str) -> None:
        with pytest.raises(SystemExit):
            assess_main(["--target", ".", "--context", bad])
