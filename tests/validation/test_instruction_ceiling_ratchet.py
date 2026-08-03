"""The always-on instruction ceilings may only fall.

Issue #4345, acceptance criterion 3. ``DEFAULT_CEILINGS_BYTES`` in
``scripts/validation/instruction_budget_constants.py`` is a non-regression
ratchet. Its own comment says so: "seeded just above current measured values ...
Lower these as the corpus shrinks." Nothing enforced the direction, so on
2026-08-03 commit ``501150e2f4`` raised ``.md`` from 83000 to 84000 as a bare
one-line change inside a PR titled "extend portability ratchet to
.claude/commands and templates/agents". No rationale was recorded anywhere.

That is the failure this module closes. A ceiling raise absorbs corpus growth
into the gate that exists to make corpus growth visible, which is the same shape
as the skipped-job defect this issue opened on, one level up.

The policy matches the count ratchets (``scripts/ci/count_ratchet.py``): the
baseline may only fall. Lowering passes. Adding a language passes. Removing one
passes. Raising blocks, and the reader is told to reclaim bytes or to record why
the raise is justified.

Comparison is against ``origin/main`` and uses ``ast.literal_eval`` on the
parsed assignment rather than importing the base revision, because importing a
file read out of git history would execute it.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

CONSTANTS_PATH = "scripts/validation/instruction_budget_constants.py"
CEILING_NAME = "DEFAULT_CEILINGS_BYTES"
BASE_REF = "origin/main"


def extract_ceilings(source: str) -> dict[str, int]:
    """Return the ``DEFAULT_CEILINGS_BYTES`` mapping declared in ``source``.

    Parses rather than imports. Raises ``ValueError`` when the assignment is
    absent or is not a literal mapping, so a silently-empty result can never be
    mistaken for "no ceilings changed".
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == CEILING_NAME for t in targets):
            continue
        if node.value is None:
            break
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"{CEILING_NAME} is not a literal mapping") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{CEILING_NAME} is not a mapping")
        return {str(k): int(v) for k, v in value.items()}
    raise ValueError(f"{CEILING_NAME} not found")


def find_raised_ceilings(
    base: dict[str, int], head: dict[str, int]
) -> list[tuple[str, int, int]]:
    """Return ``(ext, base_value, head_value)`` for every ceiling that rose.

    A key absent from ``base`` is a newly-tracked language and cannot be a
    regression. A key absent from ``head`` was retired and cannot be either.
    """
    return [
        (ext, base[ext], head[ext])
        for ext in sorted(head)
        if ext in base and head[ext] > base[ext]
    ]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _base_source() -> str | None:
    """Return the constants file at ``origin/main``, or None when unavailable.

    A shallow clone, a fork without the upstream remote, or a first commit that
    creates the file all legitimately have no base revision to compare against.
    """
    result = subprocess.run(
        ["git", "-C", str(_repo_root()), "show", f"{BASE_REF}:{CONSTANTS_PATH}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


class TestExtractCeilings:
    def test_reads_a_plain_assignment(self) -> None:
        source = f"{CEILING_NAME} = {{'.md': 83_000, '.py': 99_000}}\n"
        assert extract_ceilings(source) == {".md": 83000, ".py": 99000}

    def test_reads_an_annotated_assignment(self) -> None:
        source = f"{CEILING_NAME}: dict[str, int] = {{'.md': 84_000}}\n"
        assert extract_ceilings(source) == {".md": 84000}

    def test_ignores_a_similarly_named_binding(self) -> None:
        source = f"OTHER = {{'.md': 1}}\n{CEILING_NAME} = {{'.md': 2}}\n"
        assert extract_ceilings(source) == {".md": 2}

    def test_missing_assignment_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            extract_ceilings("X = 1\n")

    def test_non_literal_value_raises(self) -> None:
        with pytest.raises(ValueError, match="not a literal mapping"):
            extract_ceilings(f"{CEILING_NAME} = dict(md=1)\n")

    def test_non_mapping_literal_raises(self) -> None:
        with pytest.raises(ValueError, match="not a mapping"):
            extract_ceilings(f"{CEILING_NAME} = [1, 2]\n")

    def test_bare_annotation_without_value_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            extract_ceilings(f"{CEILING_NAME}: dict[str, int]\n")


class TestFindRaisedCeilings:
    def test_identical_is_clean(self) -> None:
        same = {".md": 83000, ".py": 99000}
        assert find_raised_ceilings(same, dict(same)) == []

    def test_a_raise_is_reported_with_both_values(self) -> None:
        assert find_raised_ceilings({".md": 83000}, {".md": 84000}) == [
            (".md", 83000, 84000)
        ]

    def test_a_lower_is_clean(self) -> None:
        assert find_raised_ceilings({".md": 84000}, {".md": 83000}) == []

    def test_a_new_language_is_clean(self) -> None:
        assert find_raised_ceilings({".md": 83000}, {".md": 83000, ".rs": 99000}) == []

    def test_a_retired_language_is_clean(self) -> None:
        assert find_raised_ceilings({".md": 83000, ".rs": 1}, {".md": 83000}) == []

    def test_reports_every_raised_key_not_just_the_first(self) -> None:
        base = {".md": 10, ".py": 10, ".cs": 10}
        head = {".md": 11, ".py": 10, ".cs": 12}
        assert find_raised_ceilings(base, head) == [(".cs", 10, 12), (".md", 10, 11)]

    def test_a_one_byte_raise_is_a_raise(self) -> None:
        assert find_raised_ceilings({".md": 83000}, {".md": 83001}) == [
            (".md", 83000, 83001)
        ]


class TestTheShippedCeilingsDidNotRise:
    def test_no_ceiling_rose_against_the_base_ref(self) -> None:
        base_source = _base_source()
        if base_source is None:
            pytest.skip(f"{BASE_REF}:{CONSTANTS_PATH} is not available")
        head_source = (_repo_root() / CONSTANTS_PATH).read_text(encoding="utf-8")
        raised = find_raised_ceilings(
            extract_ceilings(base_source), extract_ceilings(head_source)
        )
        assert not raised, (
            "An always-on instruction ceiling was raised: "
            + ", ".join(f"{ext} {was} -> {now}" for ext, was, now in raised)
            + f". {CEILING_NAME} is a non-regression ratchet and may only fall. "
            "Reclaim bytes by narrowing a rule's applyTo or moving situational "
            "content into a task-invoked skill (issue #3419). If a raise is "
            "genuinely justified, say why in the commit body so the next reader "
            "can weigh it (issue #4345)."
        )

    def test_the_shipped_constants_parse(self) -> None:
        head_source = (_repo_root() / CONSTANTS_PATH).read_text(encoding="utf-8")
        ceilings = extract_ceilings(head_source)
        assert ceilings
        assert all(v > 0 for v in ceilings.values())
