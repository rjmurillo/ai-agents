"""Tests for lint_skill_frontmatter.py: parse, size, artifact, and capability rules.

Each test builds a skill in tmp_path, runs `main` with `--format json`, and
asserts the exit code plus the rule status or message.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.skills.skillforge.lint_support import (  # noqa: F401
    _DESCRIPTION,
    _REPO_ROOT,
    _SKILLS_TREE,
    RULE_IDS,
    _lint,
    _messages,
    _skill_text,
    _write_skill,
    lint,
)


def test_clean_skill_exits_zero_with_no_failures_or_warnings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, rows = _lint(tmp_path, capsys, _skill_text(), "--strict")

    assert code == 0
    assert set(rows) == set(RULE_IDS)
    assert {row["status"] for row in rows.values()} <= {"PASS", "NOT_APPLICABLE"}


@pytest.mark.parametrize(
    "metadata",
    [
        "  capability: {kind: orchestrator}\n",
        "  inputs:\n    - artifact: x\n",
    ],
    ids=["flow-mapping", "mapping-inside-sequence"],
)
def test_subset_parse_fails_on_shapes_outside_the_subset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], metadata: str
) -> None:
    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 1
    assert rows["fm.subset-parse"]["status"] == "FAIL"
    assert "block mappings" in _messages(rows["fm.subset-parse"])
    assert rows["fm.artifacts.shape"]["status"] == "NOT_EVALUATED"


def test_size_bytes_fails_over_the_cap(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    text = _skill_text(body="x" * (lint.SKILL_BYTE_LIMIT + 10) + "\n")

    code, rows = _lint(tmp_path, capsys, text)

    assert code == 1
    assert rows["fm.size.bytes"]["status"] == "FAIL"
    assert str(lint.SKILL_BYTE_LIMIT) in _messages(rows["fm.size.bytes"])


def test_size_exception_makes_size_rules_not_applicable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _skill_text(
        body="x" * (lint.SKILL_BYTE_LIMIT + 10) + "\n", top_level="size-exception: true\n"
    )

    code, rows = _lint(tmp_path, capsys, text)

    assert code == 0
    assert rows["fm.size.bytes"]["status"] == "NOT_APPLICABLE"
    assert rows["fm.size.headroom"]["status"] == "NOT_APPLICABLE"


def _text_with_headroom(left: int) -> str:
    base = _skill_text(body="\n")
    pad = lint.SKILL_BYTE_LIMIT - left - len(base.encode("utf-8"))
    text = _skill_text(body="x" * pad + "\n")
    assert lint.SKILL_BYTE_LIMIT - len(text.encode("utf-8")) == left
    return text


def test_size_headroom_warns_under_the_margin_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, rows = _lint(tmp_path, capsys, _text_with_headroom(100))

    assert code == 0
    assert rows["fm.size.bytes"]["status"] == "PASS"
    assert rows["fm.size.headroom"]["status"] == "WARN"
    assert "100 bytes" in _messages(rows["fm.size.headroom"])


def test_size_headroom_warning_fails_under_strict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, rows = _lint(tmp_path, capsys, _text_with_headroom(100), "--strict")

    assert code == 1
    assert rows["fm.size.headroom"]["status"] == "WARN"


def test_size_headroom_passes_at_exactly_the_margin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, rows = _lint(tmp_path, capsys, _text_with_headroom(lint.SKILL_BYTE_HEADROOM), "--strict")

    assert code == 0
    assert rows["fm.size.headroom"]["status"] == "PASS"


def test_artifacts_keyed_shape_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    metadata = (
        "  inputs:\n"
        "    requirements-spec:\n"
        "      required: false\n"
        "      source: user\n"
        "    change-request:\n"
        "  outputs:\n"
        "    execution-plan:\n"
        "      path: plans/active/\n"
    )

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 0
    assert rows["fm.artifacts.shape"]["status"] == "PASS"


def test_artifacts_list_value_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    metadata = "  inputs:\n    - requirements-spec\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 1
    assert rows["fm.artifacts.shape"]["status"] == "FAIL"
    assert "mapping keyed by artifact name" in _messages(rows["fm.artifacts.shape"])


def test_artifacts_unknown_option_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    metadata = "  inputs:\n    requirements-spec:\n      optional: true\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 1
    assert rows["fm.artifacts.shape"]["status"] == "FAIL"
    assert "unknown option 'optional'" in _messages(rows["fm.artifacts.shape"])


@pytest.mark.parametrize("path", ["../x", "/etc", "a/../b", "C:\\x"])
def test_artifacts_hostile_output_path_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], path: str
) -> None:
    metadata = f"  outputs:\n    execution-plan:\n      path: '{path}'\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 1
    assert rows["fm.artifacts.shape"]["status"] == "FAIL"
    assert "relative to the artifact root" in _messages(rows["fm.artifacts.shape"])


def test_artifacts_required_must_be_boolean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = "  inputs:\n    requirements-spec:\n      required: maybe\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 1
    assert rows["fm.artifacts.shape"]["status"] == "FAIL"
    assert "required must be true or false" in _messages(rows["fm.artifacts.shape"])


def test_artifacts_source_must_be_in_the_closed_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = "  inputs:\n    requirements-spec:\n      source: network\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 1
    assert rows["fm.artifacts.shape"]["status"] == "FAIL"
    assert "'network'" in _messages(rows["fm.artifacts.shape"])


def test_artifacts_key_must_be_kebab_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = "  inputs:\n    Requirements_Spec:\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 1
    assert rows["fm.artifacts.shape"]["status"] == "FAIL"
    assert "kebab-case" in _messages(rows["fm.artifacts.shape"])


def test_artifacts_rule_not_applicable_without_inputs_or_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, rows = _lint(tmp_path, capsys, _skill_text())

    assert code == 0
    assert rows["fm.artifacts.shape"]["status"] == "NOT_APPLICABLE"


def test_capability_valid_block_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    metadata = "  capability:\n    kind: orchestrator\n    owns: planning\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 0
    assert rows["fm.capability.shape"]["status"] == "PASS"


def test_capability_unknown_key_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    metadata = "  capability:\n    kind: orchestrator\n    flavor: spicy\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 1
    assert rows["fm.capability.shape"]["status"] == "FAIL"
    assert "unknown key 'flavor'" in _messages(rows["fm.capability.shape"])


def test_capability_bad_kind_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    metadata = "  capability:\n    kind: wizard\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 1
    assert rows["fm.capability.shape"]["status"] == "FAIL"
    assert "capability.kind must be one of" in _messages(rows["fm.capability.shape"])


@pytest.mark.parametrize(
    ("path", "status"),
    [("123", "FAIL"), ("true", "FAIL"), ('"123"', "PASS"), ("plans/active/", "PASS")],
    ids=["plain-int", "plain-bool", "quoted-int", "real-path"],
)
def test_artifact_path_must_be_text_not_a_yaml_core_type(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], path: str, status: str
) -> None:
    metadata = f"  outputs:\n    scratch-note:\n      path: {path}\n"

    _code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert rows["fm.artifacts.shape"]["status"] == status
