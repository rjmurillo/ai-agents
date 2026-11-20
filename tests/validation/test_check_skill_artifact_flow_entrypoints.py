"""Tests for the artifact flow gate's entry points.

Covers template read failures (exit 2), the `--report` and `--format json`
conflict, and the pre-PR adapter `checks_tooling.validate_skill_artifact_flow_declarations`.
Fixture trees are built in `tmp_path` by `artifact_flow_fixtures`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import checks_tooling
from scripts.validation.pre_pr import MissingScriptSkip
from tests.validation.artifact_flow_fixtures import _corpus, _run, gate


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    return _corpus(tmp_path)


def _template(root: Path, name: str) -> Path:
    return root / gate.TEMPLATE_DIR / f"{name}{gate.TEMPLATE_SUFFIX}"


# --- unreadable templates ---------------------------------------------------


def test_undecodable_template_exits_2_naming_the_file(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _template(corpus, "broken").write_bytes(b"---\nname: \xff\xfe\n---\n")

    code, _, err = _run(corpus, capsys)

    assert code == 2
    assert "broken.SKILL.md.tmpl: unreadable" in err


def test_template_that_is_a_directory_exits_2_naming_the_file(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _template(corpus, "broken").mkdir()

    code, _, err = _run(corpus, capsys)

    assert code == 2
    assert "broken.SKILL.md.tmpl: unreadable" in err


# --- --report and --format json ---------------------------------------------


def test_report_with_json_format_is_refused_with_exit_2(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        _run(corpus, capsys, "--report", "--format", "json")

    assert raised.value.code == 2
    assert "--report cannot be combined with --format json" in capsys.readouterr().err


def test_json_format_alone_still_runs(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(corpus, capsys, "--format", "json")

    assert code == 0, err
    assert '"artifacts"' in out


def test_report_with_text_format_still_runs(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(corpus, capsys, "--report", "--format", "text")

    assert code == 0, err
    assert "no consumer:" in out


# --- pre-PR adapter ---------------------------------------------------------


def test_adapter_returns_true_on_a_clean_corpus(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert checks_tooling.validate_skill_artifact_flow_declarations(corpus) is True
    assert "examined 7 skill templates" in capsys.readouterr().out


def test_adapter_returns_false_on_a_failing_corpus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path, {"build": {"inputs": ["execution-plan"]}})

    assert checks_tooling.validate_skill_artifact_flow_declarations(tmp_path) is False
    assert "inputs must be a mapping keyed by artifact name" in capsys.readouterr().err


def test_adapter_skips_when_templates_skills_is_absent(tmp_path: Path) -> None:
    assert not (tmp_path / "templates" / "skills").exists()

    with pytest.raises(MissingScriptSkip, match="templates/skills not present"):
        checks_tooling.validate_skill_artifact_flow_declarations(tmp_path)


def test_adapter_does_not_skip_an_empty_templates_dir(tmp_path: Path) -> None:
    """An empty tree is a config error, not a downstream install: it must not read as a SKIP."""
    (tmp_path / gate.TEMPLATE_DIR).mkdir(parents=True)

    with pytest.raises(gate.TreeError):
        checks_tooling.validate_skill_artifact_flow_declarations(tmp_path)
