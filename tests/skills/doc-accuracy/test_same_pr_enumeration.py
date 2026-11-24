"""R2 requires two distinct members before it checks an enumeration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import edit_files_and_commit, make_repo, run_same_pr

SCANNER = "scripts/assess.py"
HOOKS = "hooks.json"
SOURCE = """\
PYTHON = Grammar(language_name="Python")
CSHARP = Grammar(language_name="C#")
TYPESCRIPT = Grammar(language_name="TypeScript")


def parse(grammar):
    raise grammar.error(f"{grammar.language_name} interpreter failed to start")
"""


@pytest.mark.parametrize(
    ("languages", "expected_missing"),
    [
        ("Python", []),
        ("Python or Python", []),
        ("Python or C#", ["TypeScript"]),
        ("Python, C#, or TypeScript", []),
    ],
)
def test_r2_checks_only_incomplete_lists_of_distinct_members(
    tmp_path: Path, languages: str, expected_missing: list[str]
) -> None:
    repo = make_repo(tmp_path, {SCANNER: SOURCE, HOOKS: "{}\n"})
    hooks = f'{{\n  "command": "{languages} interpreter failed to start"\n}}\n'
    edit_files_and_commit(repo, {SCANNER: SOURCE + "\n", HOOKS: hooks})

    code, findings, _ = run_same_pr(repo, tmp_path, "--phases", "1")

    hits = [finding for finding in findings["findings"] if finding["rule"] == "R2"]
    assert code == (10 if expected_missing else 0)
    assert [hit["evidence"]["missing"] for hit in hits] == (
        [expected_missing] if expected_missing else []
    )
