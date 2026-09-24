"""Tests for scripts/metrics/sg_diff_reference.py (#5856, REQ-4, REQ-6).

Prompt construction, byte capping, repository identity, and diff-line
semantics. The content-addressed artifact store (write/prune/resolve/produce)
lives in ``scripts/metrics/sg_diff_artifact.py`` and is tested in the sibling
``tests/metrics/test_sg_diff_artifact.py``; this split mirrors the source
split, which was made to satisfy the taste-lints file-size gate.

Two evidence tiers for the prompt-format claim:

1. A literal expected string, transcribed by hand from ``llm.py``'s
   ``agentic_review`` (installed plugin, not this module), proves
   ``build_inline_prompt`` matches the real hook path independent of this
   module's own helper.
2. When the plugin is installed, an ``importlib`` comparison against
   ``review_api.cap_diff_for_prompt`` proves the capping logic matches the
   plugin's own importable capper. That test is skipped, not failed, when the
   plugin directory is absent (CI has no local Claude plugin cache).
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

from scripts.metrics import sg_diff_reference as sgd
from tests.gc_real_git import git

_PLUGIN_HOOKS_DIR = (
    Path.home()
    / ".claude"
    / "plugins"
    / "cache"
    / "claude-plugins-official"
    / "security-guidance"
    / "2.0.8"
    / "hooks"
)


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test User")


def _commit_one_file(root: Path) -> str:
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    git(root, "add", "a.txt")
    git(root, "commit", "-q", "-m", "init")
    return git(root, "rev-parse", "HEAD").stdout.strip()


# --- build_inline_prompt: literal-format and installed-plugin comparisons ---


def test_build_inline_prompt_matches_llm_py_literal_format() -> None:
    """Hand-transcribed from llm.py:1210-1222; not derived from this module's helper."""
    touched_paths = ["a.py"]
    diff_files = [("a.py", "+x\n")]
    context_note = ""

    expected = (
        "Review this change for security vulnerabilities.\n\n"
        + "Changed files (you may Read these and any other file in the repo):\n"
        + "  - a.py"
        + ""
        + "\n\nUnified diff (only + lines are new):\n\n"
        + "=== DIFF: a.py ===\n+x\n"
        + "\n\nInvestigate per the method in your instructions, then return "
        "the findings list."
    )

    actual = sgd.build_inline_prompt(touched_paths, diff_files, context_note)

    assert actual == expected


def test_build_inline_prompt_multi_file_join_and_context_note_literal() -> None:
    """Two files (blank-line join) and a non-empty context_note, still hand-transcribed."""
    touched_paths = ["a.py", "b.py"]
    diff_files = [("a.py", "+x\n"), ("b.py", "-y\n")]
    context_note = "\n\nNOTE: checkout mismatch\n"

    expected = (
        "Review this change for security vulnerabilities.\n\n"
        + "Changed files (you may Read these and any other file in the repo):\n"
        + "  - a.py\n  - b.py"
        + "\n\nNOTE: checkout mismatch\n"
        + "\n\nUnified diff (only + lines are new):\n\n"
        + "=== DIFF: a.py ===\n+x\n\n\n=== DIFF: b.py ===\n-y\n"
        + "\n\nInvestigate per the method in your instructions, then return "
        "the findings list."
    )

    actual = sgd.build_inline_prompt(touched_paths, diff_files, context_note)

    assert actual == expected


def test_capped_diff_text_public_accessor_matches_inline_diff_section() -> None:
    diff_text, dropped = sgd.capped_diff_text([("a.py", "+x\n")])

    assert diff_text == "=== DIFF: a.py ===\n+x\n"
    assert dropped == 0


def test_build_inline_prompt_caps_more_than_50_touched_paths() -> None:
    touched_paths = [f"file{i}.py" for i in range(60)]
    actual = sgd.build_inline_prompt(touched_paths, [], "")
    assert "file49.py" in actual
    assert "file50.py" not in actual


_plugin_review_api = None
if _PLUGIN_HOOKS_DIR.is_dir():
    _spec = importlib.util.spec_from_file_location(
        "sg_diff_reference_plugin_review_api", _PLUGIN_HOOKS_DIR / "review_api.py"
    )
    if _spec is not None and _spec.loader is not None:
        _module = importlib.util.module_from_spec(_spec)
        _hooks_dir_str = str(_PLUGIN_HOOKS_DIR)
        _inserted = _hooks_dir_str not in sys.path
        if _inserted:
            sys.path.insert(0, _hooks_dir_str)
        try:
            _spec.loader.exec_module(_module)
            _plugin_review_api = _module
        except Exception:  # pragma: no cover - defensive; skip test below instead
            _plugin_review_api = None
        finally:
            if _inserted:
                sys.path.remove(_hooks_dir_str)


@pytest.mark.skipif(
    _plugin_review_api is None,
    reason="security-guidance plugin not installed locally; capping-parity check skipped",
)
def test_capping_matches_installed_plugin_cap_diff_for_prompt() -> None:
    assert _plugin_review_api is not None  # narrows for mypy; skipif already gates the run
    files = [
        ("big.py", "x" * 90_000),
        ("small.py", "y" * 10),
        ("overflow.py", "z" * 350_000),
    ]

    plugin_capped, plugin_dropped = _plugin_review_api.cap_diff_for_prompt(list(files))
    ours_capped, ours_dropped = sgd._cap_diff_for_prompt(
        list(files), sgd.DEFAULT_PER_FILE_BYTES, sgd.DEFAULT_TOTAL_BYTES
    )

    assert ours_capped == plugin_capped
    assert ours_dropped == plugin_dropped


# --- repo_identity ---------------------------------------------------------


def test_repo_identity_differs_for_two_unrelated_repos(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    _init_repo(repo_a)
    _init_repo(repo_b)

    assert sgd.repo_identity(repo_a) != sgd.repo_identity(repo_b)


def test_repo_identity_equal_for_worktree_of_same_repo(tmp_path: Path) -> None:
    main = tmp_path / "main-repo"
    _init_repo(main)
    _commit_one_file(main)
    worktree = tmp_path / "worktree-repo"

    git(main, "worktree", "add", str(worktree))

    assert sgd.repo_identity(main) == sgd.repo_identity(worktree)


def test_repo_identity_stable_across_repeated_calls(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    assert sgd.repo_identity(repo) == sgd.repo_identity(repo)


# --- diff_line_semantics: unit behavior -------------------------------------
# Equivalence between inline and resolved-artifact prompts is proven in
# tests/metrics/test_sg_diff_artifact.py, since it also exercises produce_prompt.


def test_diff_line_semantics_excludes_file_headers_counts_multiset() -> None:
    diff_text = (
        "=== DIFF: a.py ===\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "+added once\n"
        "+added once\n"
        "-removed\n"
    )

    semantics = sgd.diff_line_semantics(diff_text)

    assert semantics == {"a.py": Counter({"+added once": 2, "-removed": 1})}
