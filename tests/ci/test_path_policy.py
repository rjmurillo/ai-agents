"""`scripts/ci/path_policy.py` loads the one list `pytest.yml` hands to `dorny/paths-filter`.

Coverage:

- positive: the shipped policy loads as a non-empty tuple of strings.
- negative: a document with no `python` key, an empty list, a scalar value, or
  a non-mapping root raises instead of returning an empty tuple.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import path_policy


def _write_policy(tmp_path: Path, text: str) -> Path:
    policy = tmp_path / "policy.yml"
    policy.write_text(text, encoding="utf-8")
    return policy


def test_the_shipped_policy_loads_a_non_empty_tuple_of_globs() -> None:
    patterns = path_policy.load_patterns()
    assert patterns
    assert all(isinstance(pattern, str) for pattern in patterns)


def test_a_custom_policy_file_is_read_in_declaration_order(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path, "python:\n  - 'b/**'\n  - 'a/**'\n")
    assert path_policy.load_patterns(policy) == ("b/**", "a/**")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("javascript:\n  - '**/*.js'\n", "declares no 'python' filter"),
        ("- '**/*.py'\n", "declares no 'python' filter"),
        ("python: []\n", "empty 'python' filter"),
        ("python: '**/*.py'\n", "empty 'python' filter"),
    ],
)
def test_a_malformed_policy_raises(tmp_path: Path, text: str, message: str) -> None:
    policy = _write_policy(tmp_path, text)
    with pytest.raises(ValueError, match=message):
        path_policy.load_patterns(policy)
