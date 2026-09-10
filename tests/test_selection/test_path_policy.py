"""The path policy is one document, and both readers must actually read it.

`.github/workflows/pytest.yml` gates the whole pytest matrix behind a
`dorny/paths-filter`. `scripts/test_selection/select_tests.py` decides whether a
push can skip most of the suite locally. Both answer the same question, "can a
change to this path alter a pytest outcome", and before issue #5318 each kept
its own answer: 53 globs in the workflow against 12 in
`runtime_read_patterns.txt`.

Two lists expressing one policy drift in whichever direction nobody is looking.
Issue #5316 widened the CI side by hand and left the local side alone. The
reverse gap is the silent one: a path the local selector treats as ordinary and
CI does not name at all runs no assertions in either place.

Coverage:

- positive: source, test-input, and unrelated paths each classify, and the glob
  that decided it is reported.
- negative: a path no glob names classifies unrelated with no glob.
- edge: `**/` matches at the repository root, a policy-named `.py` file stays
  source, and a malformed or empty policy document raises instead of quietly
  classifying everything as unrelated.
- negative control: the workflow's `filters:` input names this exact file, so a
  policy the gate no longer reads fails here rather than going silent.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.test_selection import path_policy

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/pytest.yml"
POLICY_INPUT = "scripts/test_selection/path_policy.yml"


def _write_policy(root: Path, body: str) -> Path:
    path = root / "path_policy.yml"
    path.write_text(body, encoding="utf-8")
    return path


def _paths_filter_step() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["check-paths"]["steps"]:
        if str(step.get("uses", "")).startswith("dorny/paths-filter@"):
            return step
    raise AssertionError("pytest.yml check-paths has no dorny/paths-filter step")


def test_the_gate_reads_the_file_this_module_reads() -> None:
    """The single-source claim, asserted rather than described.

    This is the negative control for the whole module. Restore an inline
    filter in the workflow, or point it at a second document, and the local
    selector goes on classifying against a list the required gate ignores.
    Every other assertion here would still pass.
    """
    named = str(_paths_filter_step()["with"]["filters"]).strip()
    assert named == POLICY_INPUT, f"pytest.yml reads {named!r}, not the shared policy"
    assert path_policy.POLICY_FILE == REPO_ROOT / POLICY_INPUT
    assert path_policy.POLICY_FILE.is_file()


def test_the_policy_is_not_empty() -> None:
    """Vacuity guard: an empty list would classify every path as unrelated."""
    assert len(path_policy.load_patterns()) > 1


def test_python_source_classifies_as_source() -> None:
    impact, pattern = path_policy.classify("scripts/validation/pre_pr.py")
    assert impact is path_policy.Impact.SOURCE
    assert pattern == "**/*.py"


def test_runtime_read_markdown_classifies_as_test_input() -> None:
    impact, pattern = path_policy.classify(".claude/skills/github/SKILL.md")
    assert impact is path_policy.Impact.TEST_INPUT
    assert pattern == ".claude/skills/**"


def test_a_path_no_glob_names_classifies_as_unrelated() -> None:
    """Negative case: nothing in the policy covers it, so CI skips pytest.

    `select_tests.py` still runs the full suite for this shape; issue #5377 is
    what turns an unrelated push into no pytest process. The classification has
    to be right before that change can be made.
    """
    impact, pattern = path_policy.classify("assets/logo.svg")
    assert impact is path_policy.Impact.UNRELATED
    assert pattern is None


def test_a_leading_double_star_matches_at_the_repository_root() -> None:
    """picomatch's `**/` matches zero directories; bare fnmatch does not.

    Without this, a root-level `conftest.py` or `pyproject.toml` matches no
    glob and classifies as unrelated, which is the one direction that runs too
    few tests. CI matches both, so the two readers would disagree on the files
    most likely to break everything.
    """
    assert path_policy.matches("conftest.py", "**/*.py")
    assert path_policy.matches("pyproject.toml", "**/pyproject.toml")
    assert path_policy.classify("pyproject.toml")[0] is path_policy.Impact.TEST_INPUT


def test_a_policy_named_python_file_is_source_not_a_test_input() -> None:
    """Source wins the overlap, which is the pre-#5318 behavior.

    `scripts/memory_enhancement/**` and `.claude/hooks/**` are named for their
    non-Python members. Calling their modules test inputs would force the full
    suite on every ordinary Python edit inside them.
    """
    impact, pattern = path_policy.classify("scripts/memory_enhancement/embed.py")
    assert impact is path_policy.Impact.SOURCE
    assert pattern is not None


def test_pyi_stubs_are_test_inputs_because_no_import_edge_reaches_them() -> None:
    """Edge: the policy names `.pyi`, but the import graph never maps one."""
    impact, _ = path_policy.classify("scripts/typings/thing.pyi")
    assert impact is path_policy.Impact.TEST_INPUT


def test_matched_pattern_reports_the_first_glob_in_declaration_order() -> None:
    patterns = ("docs/**", "docs/guide.md")
    assert path_policy.matched_pattern("docs/guide.md", patterns) == "docs/**"
    assert path_policy.matched_pattern("other/guide.md", patterns) is None


def test_directory_globs_match_at_any_depth() -> None:
    patterns = ("a/**",)
    assert path_policy.matches("a/b/c/d.md", "a/**")
    assert path_policy.matched_pattern("b/a/c.md", patterns) is None


def test_a_document_without_the_filter_key_raises(tmp_path: Path) -> None:
    """Failing closed beats returning an empty tuple.

    An empty tuple classifies every path as unrelated, which reads as "nothing
    here can affect a test" for the whole repository.
    """
    policy = _write_policy(tmp_path, "javascript:\n  - '**/*.js'\n")
    with pytest.raises(ValueError, match="declares no 'python' filter"):
        path_policy.load_patterns(policy)


def test_an_empty_filter_list_raises(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path, "python: []\n")
    with pytest.raises(ValueError, match="empty 'python' filter"):
        path_policy.load_patterns(policy)


def test_a_scalar_filter_value_raises(tmp_path: Path) -> None:
    """A single glob written without a dash parses as a string, not a list."""
    policy = _write_policy(tmp_path, "python: '**/*.py'\n")
    with pytest.raises(ValueError, match="empty 'python' filter"):
        path_policy.load_patterns(policy)


def test_a_non_mapping_document_raises(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path, "- '**/*.py'\n")
    with pytest.raises(ValueError, match="declares no 'python' filter"):
        path_policy.load_patterns(policy)


@pytest.mark.parametrize(
    "rel",
    [
        ".claude/rules/universal.md",
        ".github/instructions/universal.instructions.md",
        "src/copilot-cli/instructions/universal.instructions.md",
        "tests/conftest.py",
        "pyproject.toml",
        "lefthook.yml",
        "uv.lock",
        ".config/wt.toml",
        "scripts/ci/ruff_count_baseline.txt",
        "scripts/ci/subprocess_encoding_count_baseline.txt",
        ".agents/memory/episodes/2026-01-01-session.json",
    ],
)
def test_every_path_the_retired_local_list_named_is_still_covered(rel: str) -> None:
    """No coverage was dropped when `runtime_read_patterns.txt` was deleted.

    These are the paths that file named. Each must still be classified by the
    shared policy, as source or as a test input but never as unrelated, or the
    consolidation quietly removed a full-suite trigger.
    """
    impact, pattern = path_policy.classify(rel)
    assert impact is not path_policy.Impact.UNRELATED, rel
    assert pattern is not None
