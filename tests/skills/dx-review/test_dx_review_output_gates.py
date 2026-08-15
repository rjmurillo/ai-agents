from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "dx-review"
    / "SKILL.md"
)
UNIVERSAL_COMMAND_APPROVAL_FRAGMENTS = (
    "Every shell command requires explicit user approval",
    "including help, setup, and error-path commands",
    "Do not delegate command execution through Task",
    "requirements apply to commands run by any subagent",
)
OVERALL_DX_CALCULATION_FRAGMENTS = (
    "arithmetic mean of available 0-10 dimension scores",
    "Exclude dimensions marked N/A",
    "Round the result to one decimal place",
    "weakest evidence label among included dimensions",
    "| Overall DX",
    "Mean: [sum]/[count]",
)
BLOCKING_GATE_FRAGMENTS = (
    "GATE_STATUS: Evidence Gate = PASS",
    "two independent sources for each high-impact conclusion",
    "Evidence Gate = FAIL",
    "lacks two independent sources",
    "Record conflicting evidence",
    "GATE_STATUS: Review Gate = PASS",
    "PASS_WITH_CONCERNS",
    "read-only `code-review` subagent_type",
    "target excerpts",
    "as untrusted data",
    "not execute commands",
)


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _normalize_space(text: str) -> str:
    return " ".join(text.split())


def _contains_all(text: str, fragments: tuple[str, ...]) -> bool:
    return all(fragment in text for fragment in fragments)


def _has_universal_command_approval(text: str) -> bool:
    normalized = _normalize_space(text)
    return (
        _contains_all(normalized, UNIVERSAL_COMMAND_APPROVAL_FRAGMENTS)
        and "Every command derived from" not in normalized
    )


def _has_overall_dx_calculation(text: str) -> bool:
    return _contains_all(_normalize_space(text), OVERALL_DX_CALCULATION_FRAGMENTS)


def _has_blocking_gates(text: str) -> bool:
    return (
        _contains_all(_normalize_space(text), BLOCKING_GATE_FRAGMENTS)
        and text.count("`FAIL` blocks final output") == 2
    )


def test_every_shell_command_requires_approval() -> None:
    assert _has_universal_command_approval(_skill_text())


def test_overall_dx_calculation_is_defined() -> None:
    assert _has_overall_dx_calculation(_skill_text())


def test_blocking_evidence_and_review_gates_are_defined() -> None:
    assert _has_blocking_gates(_skill_text())


def test_gate_contract_mutations_fail() -> None:
    text = _skill_text()
    mutations = (
        (
            text.replace(
                "shell command requires explicit user approval",
                "command derived from documentation requires explicit user approval",
                1,
            ),
            _has_universal_command_approval,
        ),
        (
            text.replace("Round the result to one decimal place.", "", 1),
            _has_overall_dx_calculation,
        ),
        (
            text.replace("GATE_STATUS: Evidence Gate = PASS", "Evidence Gate", 1),
            _has_blocking_gates,
        ),
        (
            text.replace(
                "a high-impact conclusion lacks\n  two independent sources",
                "a high-impact conclusion lacks optional context",
                1,
            ),
            _has_blocking_gates,
        ),
        (
            text.replace("GATE_STATUS: Review Gate = PASS", "Review Gate", 1),
            _has_blocking_gates,
        ),
        (
            text.replace("read-only `code-review`", "`general-purpose`", 1),
            _has_blocking_gates,
        ),
    )

    for mutated, validator in mutations:
        assert not validator(mutated)
