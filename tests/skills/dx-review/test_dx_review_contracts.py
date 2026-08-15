"""Contract validation tests for the dx-review skill.

Each contract validator checks a semantic property of the skill text.
Positive cases use the real SKILL.md. Negative cases feed mutated text
that re-introduces the unsafe pattern the contract guards against.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

SKILL_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "dx-review"
    / "SKILL.md"
)

_skill_text: str | None = None
EVIDENCE_METHOD_PLACEHOLDERS = frozenset({"[actual]", "TESTED", "PARTIAL", "INFERRED"})
TTHW_METHOD_PLACEHOLDERS = frozenset(
    {"[actual/N/A]", "N/A", "TESTED", "PARTIAL", "INFERRED"}
)
READ_ONLY_APPROVAL_PATTERN = re.compile(
    r"(?i)\bread-?only commands?\s+do not need approval\b"
)
TESTED_FILE_INSPECTION_PATTERN = re.compile(
    r"(?i)\bTESTED\b[^\n]*\b(file inspection|file read|fetched documentation|static inspection)\b"
)

PROVENANCE_REFERENCE_PATTERNS = (
    re.compile(r"(?im)^##\s+provenance\s*$"),
    re.compile(r"(?i)\bgstack\b"),
    re.compile(r"(?i)\bgarrytan\b"),
    re.compile(r"(?i)\bSKILL\.md\.tmpl\b"),
    re.compile(r"(?i)\badapted\b"),
    re.compile(r"\bd078622b73539fc1a7a27e709861e9b6b058ae98\b"),
)


def _load_skill() -> str:
    global _skill_text
    if _skill_text is None:
        _skill_text = SKILL_PATH.read_text(encoding="utf-8")
    return _skill_text


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Parse YAML frontmatter between ``---`` fences."""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def _extract_block(text: str, heading: str, stop_prefixes: tuple[str, ...]) -> str:
    """Return the body of a Markdown heading block, or an empty string."""
    start = text.find(heading)
    if start == -1:
        return ""
    body = text[start + len(heading) :].lstrip("\n")
    end = len(body)
    for prefix in stop_prefixes:
        marker = f"\n{prefix}"
        index = body.find(marker)
        if index != -1:
            end = min(end, index)
    return body[:end]


def _normalize_space(text: str) -> str:
    """Collapse all whitespace to single spaces."""
    return " ".join(text.split())


def _contains_any(text: str, fragments: tuple[str, ...]) -> bool:
    """Return True when any fragment appears in text."""
    return any(fragment in text for fragment in fragments)


def _scorecard_rows(text: str) -> list[list[str]]:
    """Parse rows from the DX scorecard code block."""
    start = text.find("DX AUDIT SCORECARD")
    if start == -1:
        return []
    end = text.find("```", start)
    if end == -1:
        return []

    rows: list[list[str]] = []
    for line in text[start:end].splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 4:
            continue
        if cells[0] == "Dimension" or set(cells[0]) == {"-"}:
            continue
        rows.append(cells)
    return rows


# ---------------------------------------------------------------------------
# Contract helpers
# ---------------------------------------------------------------------------


def check_no_bash_preapproved(text: str) -> bool:
    """Return True when Bash is absent from the allowed-tools frontmatter.

    Parses the YAML frontmatter with ``yaml.safe_load``. Handles block-list,
    inline-list, and scalar ``allowed-tools`` forms. Bash appearing only
    inside prose (e.g. code-fence language tags) does not count.
    """
    fm = _parse_frontmatter(text)
    tools = fm.get("allowed-tools")
    if tools is None:
        return True
    if isinstance(tools, str):
        return not any(tool.lower() == "bash" for tool in tools.split())
    if isinstance(tools, list):
        return not any(
            str(t).strip().lower() == "bash" for t in tools
        )
    return True


def check_every_command_approval(text: str) -> bool:
    """Return True when the text requires explicit user approval for every command.

    The contract requires both:
    1. A statement that every command needs explicit user approval.
    2. No language that limits approval to only some commands (e.g.
       "commands that write outside" or "cannot be undone").
    """
    if READ_ONLY_APPROVAL_PATTERN.search(text):
        return False
    step = _extract_block(
        text,
        "### Step 1: Getting Started / Onboarding Audit",
        ("### ", "## "),
    )
    if not step:
        return False
    lower = _normalize_space(step.lower())
    has_every = _contains_any(
        lower,
        ("every command", "every shell command", "all commands"),
    )
    has_approval = _contains_any(
        lower,
        ("explicit user approval", "explicit approval"),
    )
    has_subset_scoping = _contains_any(
        lower,
        (
            "any command that writes outside",
            "cannot be undone requires",
            "commands derived from",
        ),
    )
    return has_every and has_approval and not has_subset_scoping


def check_tested_excludes_file_inspection(text: str) -> bool:
    """Return True when TESTED is defined as execution/observation, not file reads.

    The TESTED label must mean the auditor executed the interaction or command
    and observed the result. File-only inspection is INFERRED.
    """
    if TESTED_FILE_INSPECTION_PATTERN.search(text):
        return False
    labels = _extract_block(text, "## Evidence Labels", ("## ",))
    if not labels:
        return False
    tested_row = next(
        (line for line in labels.lower().splitlines() if line.startswith("| tested |")),
        "",
    )
    return bool(tested_row) and (
        "executed the interaction or command" in tested_row
        and "observed the result" in tested_row
        and "file inspection" not in tested_row
        and "file read" not in tested_row
    )


def check_tthw_not_hardcoded_tested(text: str) -> bool:
    """Return True when TTHW cannot be hardcoded as TESTED.

    Two checks:
    1. The skill contains prose prohibiting hardcoded TESTED for TTHW.
    2. The TTHW scorecard row does not contain a literal TESTED label.
    """
    lower = text.lower()
    has_prohibition = (
        "never hardcode tested" in lower
        or "never hardcode tested for tthw" in lower
    )
    if not has_prohibition:
        return False
    for row in _scorecard_rows(text):
        if row[0] != "TTHW":
            continue
        return row[3] in TTHW_METHOD_PLACEHOLDERS and row[3] != "TESTED"
    return True


def check_scorecard_rows_have_methods(text: str) -> bool:
    """Return True when every scorecard row carries a method label column."""
    rows = _scorecard_rows(text)
    if not rows:
        return False
    for dimension, _score, _summary, method in rows:
        placeholders = (
            TTHW_METHOD_PLACEHOLDERS
            if dimension == "TTHW"
            else EVIDENCE_METHOD_PLACEHOLDERS
        )
        if method not in placeholders:
            return False
    return True


def check_no_provenance_or_source_references(text: str) -> bool:
    """Return True when the skill omits upstream provenance prose."""
    return not any(pattern.search(text) for pattern in PROVENANCE_REFERENCE_PATTERNS)


# ---------------------------------------------------------------------------
# Positive cases: real skill passes all contracts
# ---------------------------------------------------------------------------


class TestRealSkillContracts:
    """The real SKILL.md must pass every contract validator."""

    def test_no_bash_preapproved(self) -> None:
        assert check_no_bash_preapproved(_load_skill())

    def test_every_command_approval(self) -> None:
        assert check_every_command_approval(_load_skill())

    def test_tested_excludes_file_inspection(self) -> None:
        assert check_tested_excludes_file_inspection(_load_skill())

    def test_tthw_not_hardcoded_tested(self) -> None:
        assert check_tthw_not_hardcoded_tested(_load_skill())

    def test_scorecard_rows_have_method_labels(self) -> None:
        assert check_scorecard_rows_have_methods(_load_skill())

    def test_omits_provenance_and_gstack_references(self) -> None:
        assert check_no_provenance_or_source_references(_load_skill())


# ---------------------------------------------------------------------------
# Mutation cases: each mutation must fail the matching validator
# ---------------------------------------------------------------------------


def _inject_bash_block_list(text: str) -> str:
    """Re-add Bash to the allowed-tools block list."""
    return text.replace(
        "  - AskUserQuestion",
        "  - Bash\n  - AskUserQuestion",
    )


def _inject_bash_inline_list(text: str) -> str:
    """Replace allowed-tools with an inline list containing Bash."""
    return re.sub(
        r"allowed-tools:\n(?:  - \w+\n)+",
        "allowed-tools: [Read, Bash, Grep]\n",
        text,
        count=1,
    )


def _inject_bash_scalar(text: str) -> str:
    """Replace allowed-tools with a scalar value of Bash."""
    return re.sub(
        r"allowed-tools:\n(?:  - \w+\n)+",
        "allowed-tools: Bash\n",
        text,
        count=1,
    )


def _inject_bash_multi_tool_scalar(text: str) -> str:
    """Replace allowed-tools with a multi-tool scalar containing Bash."""
    return re.sub(
        r"allowed-tools:\n(?:  - \w+\n)+",
        "allowed-tools: Read Grep Glob Bash\n",
        text,
        count=1,
    )


def _weaken_approval_to_subset(text: str) -> str:
    """Replace every-command approval with subset-only approval."""
    return re.sub(
        r"Every\s+shell command requires explicit user approval via "
        r"AskUserQuestion before\s+execution",
        "Any command that writes outside the temporary directory, "
        "changes shared state,\n"
        "or cannot be undone requires\n"
        "explicit user approval",
        text,
        count=1,
    )


def _remove_every_command(text: str) -> str:
    """Remove the 'every command' phrase entirely."""
    return re.sub(r"Every\s+shell command", "Some shell commands", text, count=1)


def _make_tested_include_file_inspection(text: str) -> str:
    """Redefine TESTED to include file inspection."""
    return text.replace(
        "The auditor executed the interaction or command "
        "and observed the result",
        "The auditor executed the interaction or file inspection "
        "and observed the result",
    )


def _hardcode_tthw_prose(text: str) -> str:
    """Remove the never-hardcode-TESTED-for-TTHW prose guard."""
    return text.replace(
        "Never hardcode TESTED for TTHW.",
        "TTHW is always TESTED.",
    )


def _hardcode_tthw_scorecard_row(text: str) -> str:
    """Hardcode TESTED in the TTHW scorecard row."""
    return text.replace(
        "[actual/N/A]",
        "TESTED",
    )


def _insert_gstack_provenance(text: str) -> str:
    """Re-introduce the removed upstream provenance block."""
    provenance = (
        "## Provenance\n\n"
        "Adapted from gstack at "
        "d078622b73539fc1a7a27e709861e9b6b058ae98.\n\n"
    )
    return text.replace("## Triggers", provenance + "## Triggers", 1)


def _append_read_only_contradiction(text: str) -> str:
    """Append a contradiction that exempts read-only commands from approval."""
    return text + "\nRead-only commands do not need approval.\n"


def _append_tested_file_inspection_contradiction(text: str) -> str:
    """Append a contradiction that broadens TESTED to file inspection."""
    return text + "\nTESTED includes file inspection.\n"


def _remove_overall_dx_method(text: str) -> str:
    """Blank the Overall DX method column in the scorecard."""
    return text.replace(
        "| Overall DX           | __/10  | Mean: [sum]/[count]    | [actual]     |",
        "| Overall DX           | __/10  | Mean: [sum]/[count]    |              |",
    )


class TestMutationsBash:
    """Mutations that re-add Bash must fail check_no_bash_preapproved."""

    def test_bash_in_block_list(self) -> None:
        mutated = _inject_bash_block_list(_load_skill())
        assert not check_no_bash_preapproved(mutated)

    def test_bash_in_inline_list(self) -> None:
        mutated = _inject_bash_inline_list(_load_skill())
        assert not check_no_bash_preapproved(mutated)

    def test_bash_as_scalar(self) -> None:
        mutated = _inject_bash_scalar(_load_skill())
        assert not check_no_bash_preapproved(mutated)

    def test_bash_in_multi_tool_scalar(self) -> None:
        mutated = _inject_bash_multi_tool_scalar(_load_skill())
        assert not check_no_bash_preapproved(mutated)


class TestMutationsApproval:
    """Mutations that weaken every-command approval must fail."""

    def test_subset_only_approval(self) -> None:
        mutated = _weaken_approval_to_subset(_load_skill())
        assert not check_every_command_approval(mutated)

    def test_remove_every_command(self) -> None:
        mutated = _remove_every_command(_load_skill())
        assert not check_every_command_approval(mutated)

    def test_read_only_approval_contradiction(self) -> None:
        mutated = _append_read_only_contradiction(_load_skill())
        assert not check_every_command_approval(mutated)


class TestMutationsTested:
    """Mutations that broaden TESTED to include file inspection must fail."""

    def test_tested_includes_file_inspection(self) -> None:
        mutated = _make_tested_include_file_inspection(_load_skill())
        assert not check_tested_excludes_file_inspection(mutated)

    def test_appended_tested_file_inspection_contradiction(self) -> None:
        mutated = _append_tested_file_inspection_contradiction(_load_skill())
        assert not check_tested_excludes_file_inspection(mutated)


class TestMutationsTthw:
    """Mutations that hardcode TTHW as TESTED must fail."""

    def test_hardcode_tthw_prose(self) -> None:
        mutated = _hardcode_tthw_prose(_load_skill())
        assert not check_tthw_not_hardcoded_tested(mutated)

    def test_hardcode_tthw_scorecard_row(self) -> None:
        mutated = _hardcode_tthw_scorecard_row(_load_skill())
        assert not check_tthw_not_hardcoded_tested(mutated)


class TestMutationsScorecard:
    """Mutations that drop scorecard methods must fail."""

    def test_remove_overall_dx_method(self) -> None:
        mutated = _remove_overall_dx_method(_load_skill())
        assert not check_scorecard_rows_have_methods(mutated)


class TestMutationsProvenance:
    """Mutations that restore upstream provenance must fail."""

    def test_gstack_provenance_is_absent(self) -> None:
        mutated = _insert_gstack_provenance(_load_skill())
        assert not check_no_provenance_or_source_references(mutated)
