#!/usr/bin/env python3
"""Behavioral tests for the pre-commit yamllint staged-file scoping.

Regression guard for #3031. The yamllint step used to lint the entire working
tree (``yamllint -f parsable .``), which walked thousands of files under
gitignored tool bundles (``.codeql/cli`` alone vendors 5000+ YAMLs) and hung
the commit for minutes whenever any YAML was staged. The fix scopes the lint to
the staged YAML files via a bash-3-safe array build that also rejects symlinks
(MEDIUM-002) and skips paths no longer on disk.

To avoid duplicating the loop (which would drift from the hook), these tests
extract the exact ``YAML_FILES`` array-build block from ``.githooks/pre-commit``
and run it under bash against controlled inputs, plus a structural assertion
that the whole-tree scan is gone.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"


def _hook_text() -> str:
    return PRE_COMMIT.read_text(encoding="utf-8")


def _extract_target_block() -> str:
    """Return the YAML_FILES array-build loop from the hook.

    Extracts from the ``YAML_FILES=()`` line through the terminating
    ``done <<< "$STAGED_YAML_FILES"`` line, inclusive.
    """
    lines = _hook_text().splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "YAML_FILES=()":
            start = i
            break
    assert start is not None, "YAML_FILES=() array init not found in hook"
    end = None
    for j in range(start, len(lines)):
        if 'done <<< "$STAGED_YAML_FILES"' in lines[j]:
            end = j
            break
    assert end is not None, "array-build terminator not found in hook"
    return "\n".join(lines[start : end + 1])


def _run_block(paths: list[str], cwd: Path) -> list[str]:
    """Run the extracted array-build block and return the selected targets.

    ``paths`` becomes the newline-joined ``STAGED_YAML_FILES`` value. The hook
    function ``echo_warning`` is stubbed. Returns the resulting ``YAML_FILES``
    entries, one per line.
    """
    block = _extract_target_block()
    value = "\n".join(paths)
    script = (
        "echo_warning() { :; }\n"
        f'STAGED_YAML_FILES="{value}"\n'
        f"{block}\n"
        'if [ ${#YAML_FILES[@]} -gt 0 ]; then printf "%s\\n" "${YAML_FILES[@]}"; fi\n'
    )
    bash = shutil.which("bash")
    assert bash is not None, "bash interpreter required for this test"
    result = subprocess.run(
        [bash, "-c", script],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return [ln for ln in result.stdout.splitlines() if ln]


# --- Positive: staged YAML files are selected ------------------------------


def test_selects_staged_yaml_files(tmp_path: Path) -> None:
    (tmp_path / "a.yml").write_text("k: v\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("k: v\n", encoding="utf-8")

    selected = _run_block(["a.yml", "b.yaml"], cwd=tmp_path)

    assert selected == ["a.yml", "b.yaml"]


def test_preserves_nested_paths(tmp_path: Path) -> None:
    nested = tmp_path / ".github" / "actions" / "x"
    nested.mkdir(parents=True)
    (nested / "action.yml").write_text("runs:\n", encoding="utf-8")

    selected = _run_block([".github/actions/x/action.yml"], cwd=tmp_path)

    assert selected == [".github/actions/x/action.yml"]


# --- Negative / edge cases -------------------------------------------------


def test_empty_input_selects_nothing(tmp_path: Path) -> None:
    selected = _run_block([], cwd=tmp_path)

    assert selected == []


def test_skips_symlinks(tmp_path: Path) -> None:
    real = tmp_path / "real.yml"
    real.write_text("k: v\n", encoding="utf-8")
    link = tmp_path / "link.yml"
    link.symlink_to(real)

    selected = _run_block(["link.yml", "real.yml"], cwd=tmp_path)

    # Symlink rejected (MEDIUM-002); only the real path survives.
    assert selected == ["real.yml"]


def test_skips_paths_not_on_disk(tmp_path: Path) -> None:
    (tmp_path / "present.yml").write_text("k: v\n", encoding="utf-8")

    selected = _run_block(["present.yml", "ghost.yml"], cwd=tmp_path)

    assert selected == ["present.yml"]


# --- Structural: the whole-tree scan must not return -----------------------


def test_hook_has_no_whole_tree_yamllint_scan() -> None:
    text = _hook_text()
    assert "yamllint -f parsable ." not in text, (
        "whole-tree yamllint scan reintroduced (#3031); "
        "scope to staged files instead"
    )


def test_hook_scopes_yamllint_to_array() -> None:
    text = _hook_text()
    assert 'yamllint -f parsable "${YAML_FILES[@]}"' in text, (
        "yamllint must lint the staged-file array, not the whole tree"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
