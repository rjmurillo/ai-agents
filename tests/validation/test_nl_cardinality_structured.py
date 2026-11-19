"""Structured-data form of the derived-cardinality check, and its staged hook.

A count word inside a string value restates the length of a sibling array in the
same object. PR #7311 shipped `"these two PRs"` beside a three-item
`pull_requests` list in `.project-toolkit/pr-checks/dispositions.json`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import nl_cardinality as card

from scripts.validation import git_hook_policy as policy

# Trimmed from the wrong state of PR #7311 (commit 96798c2f56).
PR_7311_ENTRY = {
    "Verify dispatch closure against base": {
        "disposition": "tracked-issue",
        "reason": (
            "PR #7240 edits three files on purpose. The owner approved this waiver "
            "for these two PRs on 2026-11-11."
        ),
        "expires": "2026-11-18",
        "pull_requests": [7240, 7244, 7306],
    }
}

# Trimmed from the current .project-toolkit/pr-checks/dispositions.json.
RENOVATE_ENTRY = {
    "Renovate": {
        "disposition": "infrastructure",
        "reason": "The owner approved this waiver for these two PRs only.",
        "expires": "2026-11-19",
        "pull_requests": [7045, 6982],
    }
}


def _claims(data: object, kind: str = "json") -> list[card.StructuredClaim]:
    text = json.dumps(data, indent=2) if kind == "json" else str(data)
    return card.structured_count_claims(text, kind)


def test_pr_7311_two_prs_beside_three_item_list_is_flagged() -> None:
    claims = _claims(PR_7311_ENTRY)

    assert [(c.stated, c.actual, c.array_key) for c in claims] == [(2, 3, "pull_requests")]
    assert claims[0].path.endswith("reason")


def test_renovate_two_prs_beside_two_item_list_is_clean() -> None:
    assert _claims(RENOVATE_ENTRY) == []


def test_numeral_form_is_checked_like_the_word_form() -> None:
    data = {"reason": "Waived for 2 PRs.", "pull_requests": [1, 2, 3]}

    assert [(c.stated, c.actual) for c in _claims(data)] == [(2, 3)]


def test_multi_array_object_matches_noun_to_key_by_token() -> None:
    data = {
        "reason": "Applies to these three files.",
        "files": ["a.py", "b.py"],
        "pull_requests": [1, 2, 3],
    }

    claims = _claims(data)

    assert [(c.stated, c.actual, c.array_key) for c in claims] == [(3, 2, "files")]


def test_multi_array_object_matches_initialism_to_key() -> None:
    data = {
        "reason": "Waived for these two PRs.",
        "files": ["a.py", "b.py", "c.py"],
        "pull_requests": [1, 2, 3],
    }

    claims = _claims(data)

    assert [(c.stated, c.actual, c.array_key) for c in claims] == [(2, 3, "pull_requests")]


def test_multi_array_object_with_unmatched_noun_is_left_alone() -> None:
    data = {"reason": "Run the two checks.", "files": ["a"], "pull_requests": [1, 2, 3]}

    assert _claims(data) == []


def test_single_sibling_array_with_unrelated_noun_is_left_alone() -> None:
    data = {"reason": "Edits three files on purpose.", "pull_requests": [1, 2]}

    assert _claims(data) == []


def test_object_with_no_sibling_array_is_left_alone() -> None:
    data = {"reason": "Waived for these two PRs.", "owner": "someone"}

    assert _claims(data) == []


def test_empty_sibling_array_is_left_alone() -> None:
    assert _claims({"reason": "Waived for these two PRs.", "pull_requests": []}) == []


@pytest.mark.parametrize(
    "phrase",
    ["at least two PRs", "exactly two PRs", "no more than two PRs", "up to two PRs"],
)
def test_contractual_phrase_is_not_flagged(phrase: str) -> None:
    data = {"rule": f"Requires {phrase}.", "pull_requests": [1, 2, 3]}

    assert _claims(data) == []


def test_nested_object_checks_siblings_at_its_own_level() -> None:
    data = {"outer": {"note": "Covers these two PRs.", "pull_requests": [1, 2, 3]}}

    claims = _claims(data)

    assert [c.path for c in claims] == ["outer.note"]


def test_array_of_objects_is_walked() -> None:
    data = {"entries": [{"note": "Covers two PRs.", "pull_requests": [1, 2, 3]}]}

    assert [c.path for c in _claims(data)] == ["entries[0].note"]


def test_yaml_form_is_flagged() -> None:
    text = (
        "entry:\n"
        "  reason: Waived for these two PRs.\n"
        "  pull_requests:\n"
        "    - 7240\n"
        "    - 7244\n"
        "    - 7306\n"
    )

    claims = card.structured_count_claims(text, "yaml")

    assert [(c.stated, c.actual, c.array_key) for c in claims] == [(2, 3, "pull_requests")]
    assert claims[0].line == 2


def test_yaml_matching_count_is_clean() -> None:
    text = "reason: Waived for these two PRs.\npull_requests: [1, 2]\n"

    assert card.structured_count_claims(text, "yaml") == []


def test_unparseable_document_yields_no_claims() -> None:
    assert card.structured_count_claims("{not json", "json") == []
    assert card.structured_count_claims("a: [unclosed", "yaml") == []


def test_claim_line_points_at_the_string_value() -> None:
    claims = _claims(PR_7311_ENTRY)

    assert claims[0].line == 4


# -- staged hook ----------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _stage(tmp_path: Path, name: str, text: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    if not (repo / ".git").exists():
        _git(repo, "init", "-q", "--initial-branch=main")
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    return repo


def _run_hook(repo: Path, *paths: str) -> int:
    return policy.main(["--repo-root", str(repo), "staged-structured-cardinality", *paths])


def test_hook_fails_on_contradicted_count_in_staged_json(tmp_path: Path, capsys) -> None:
    repo = _stage(tmp_path, "d.json", json.dumps(PR_7311_ENTRY, indent=2))

    code = _run_hook(repo, "d.json")

    assert code == 1
    err = capsys.readouterr().err
    assert "d.json" in err and "pull_requests" in err


def test_hook_passes_on_matching_count(tmp_path: Path) -> None:
    repo = _stage(tmp_path, "d.json", json.dumps(RENOVATE_ENTRY, indent=2))

    assert _run_hook(repo, "d.json") == 0


def test_hook_checks_yaml_files(tmp_path: Path) -> None:
    repo = _stage(
        tmp_path, "d.yml", "reason: Waived for these two PRs.\npull_requests: [1, 2, 3]\n"
    )

    assert _run_hook(repo, "d.yml") == 1


def test_hook_reads_the_index_not_the_working_tree(tmp_path: Path) -> None:
    repo = _stage(tmp_path, "d.json", json.dumps(PR_7311_ENTRY, indent=2))
    (repo / "d.json").write_text(json.dumps(RENOVATE_ENTRY), encoding="utf-8")

    assert _run_hook(repo, "d.json") == 1


def test_hook_skips_other_extensions_and_empty_input(tmp_path: Path) -> None:
    repo = _stage(tmp_path, "notes.md", "Waived for these two PRs.\n")

    assert _run_hook(repo, "notes.md") == 0
    assert _run_hook(repo) == 0


def test_hook_rejects_unsafe_path(tmp_path: Path) -> None:
    repo = _stage(tmp_path, "d.json", "{}")

    assert _run_hook(repo, "../d.json") == 2
