"""CLI-level tests for the decision-record validator (issue #5387).

Split from ``test_validation_record.py`` (taste-lints file-size gate) once the
record-shape and rule tests there passed 500 lines. This file covers the
subprocess entry point, `main()`, `load_trigger()`, and the vendored-install
smoke test; the rule-level tests driving `validate()` directly stay in the
sibling file.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validation_record_fixtures import (
    make_record,
    make_target,
    make_unknown_owner_target,
    make_vendor_target,
    mod,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = PROJECT_ROOT / ".claude" / "skills"
COPILOT_SKILLS_ROOT = PROJECT_ROOT / "src" / "copilot-cli" / "skills"
_TIMEOUT_S = 60
_RECORD_SCRIPT = SKILLS_ROOT / "validation-authority" / "scripts" / "validation_record.py"


def _run(script: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_S,
        check=False,
    )


def _write_record(tmp_path: Path, record: dict[str, Any]) -> Path:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_cli_exits_0_on_a_passing_record(tmp_path: Path) -> None:
    record_path = _write_record(tmp_path, make_record(make_target()))
    result = _run(_RECORD_SCRIPT, PROJECT_ROOT, "--record", str(record_path))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_cli_exits_1_on_a_defective_record(tmp_path: Path) -> None:
    record_path = _write_record(tmp_path, make_record(make_unknown_owner_target()))
    result = _run(_RECORD_SCRIPT, PROJECT_ROOT, "--record", str(record_path))
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["defects"]


def test_cli_exits_2_on_a_missing_record_file(tmp_path: Path) -> None:
    result = _run(_RECORD_SCRIPT, PROJECT_ROOT, "--record", str(tmp_path / "nope.json"))
    assert result.returncode == 2
    assert result.stdout == ""


def test_cli_exits_2_on_invalid_json(tmp_path: Path) -> None:
    record_path = tmp_path / "record.json"
    record_path.write_text("{not json", encoding="utf-8")
    result = _run(_RECORD_SCRIPT, PROJECT_ROOT, "--record", str(record_path))
    assert result.returncode == 2
    assert "not valid JSON" in result.stderr


def test_cli_reruns_the_changed_path_rules(tmp_path: Path) -> None:
    """/test Gate 4 and /review Stage 1 re-run the record with --changed-path."""
    record_path = _write_record(tmp_path, make_record(make_vendor_target()))
    result = _run(
        _RECORD_SCRIPT,
        PROJECT_ROOT,
        "--record",
        str(record_path),
        "--changed-path",
        "vendor/lint/rule.py",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any("must not be a changed path" in d for d in payload["defects"])


def test_cli_exits_2_when_the_trigger_sibling_is_missing_but_needed(tmp_path: Path) -> None:
    """A changed-path run needs the sibling trigger module to check rule 8a."""
    record_path = _write_record(tmp_path, make_record(make_target()))
    result = _run(
        _RECORD_SCRIPT,
        tmp_path,
        "--record",
        str(record_path),
        "--changed-path",
        "scripts/validation/check_x.py",
        "--trigger",
        str(tmp_path / "nope.py"),
    )
    assert result.returncode == 2
    assert "trigger" in result.stderr.lower()


def test_load_trigger_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        mod.load_trigger(tmp_path / "missing.py")


def test_load_trigger_rejects_an_unloadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "validation_trigger.py"
    target.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod.importlib.util, "spec_from_file_location", lambda *a, **k: None)
    with pytest.raises(ImportError, match="cannot load validation trigger"):
        mod.load_trigger(target)


def test_main_prints_the_summary_as_json(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_path = _write_record(tmp_path, make_record(make_target()))
    assert mod.main(["--record", str(record_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["targets"] == 1


def test_main_returns_2_and_prints_nothing_for_a_missing_record(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert mod.main(["--record", str(tmp_path / "nope.json")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot read input" in captured.err


def test_main_returns_2_for_invalid_json(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_path = tmp_path / "record.json"
    record_path.write_text("{not json", encoding="utf-8")
    assert mod.main(["--record", str(record_path)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_main_returns_2_when_the_trigger_cannot_load(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_path = _write_record(tmp_path, make_record(make_target()))
    assert (
        mod.main(
            [
                "--record",
                str(record_path),
                "--changed-path",
                "scripts/validation/check_x.py",
                "--trigger",
                str(tmp_path / "nope.py"),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot load sibling trigger" in captured.err


@pytest.fixture(params=["vendored-copy", "copilot-generated"])
def shipped_script(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """The record validator as a consumer gets it, with its sibling build skill."""
    if request.param == "copilot-generated":
        return COPILOT_SKILLS_ROOT / "validation-authority" / "scripts" / "validation_record.py"
    from tests.lib.vendored_copy import copy_vendored_entry

    plugin_skills = tmp_path / "plugin" / "skills"
    plugin_skills.mkdir(parents=True)
    for name in ("validation-authority", "build"):
        copy_vendored_entry(SKILLS_ROOT / name, plugin_skills / name)
    return plugin_skills / "validation-authority" / "scripts" / "validation_record.py"


def test_cli_runs_standalone_in_a_vendored_install(shipped_script: Path, tmp_path: Path) -> None:
    record_path = _write_record(tmp_path, make_record(make_target()))
    result = _run(shipped_script, tmp_path, "--record", str(record_path))
    assert result.returncode == 0, result.stderr
