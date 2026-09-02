"""Tests for scripts/validation/check_rule_scope_keys.py (issue #4871).

Guards the gate that refuses a `.claude/rules/*.md` scope key Claude Code
ignores. Claude Code honors `paths:` alone. The three keys the generator also
accepts fail differently, verified by running one rule per shape through
`generate_rules.py`: `applyTo:` is remapped, so the mirror is scoped and only
the Claude source leaks; `globs:` is preserved verbatim and never becomes
`applyTo:`, so neither tree is scoped; `alwaysApply:` is dropped and
`applyTo: '**'` is synthesized, so both trees load universally. All three leave
the rule loading on every Claude session, which is what this gate refuses.

- pos: a rules tree where every rule declares `paths:` -> exit 0, no findings
- neg/applyTo: the exact `pragmatic-programmer.md` shape -> exit 1, names the file
- neg/alwaysApply: the exact `code-quality.md` shape -> exit 1, names the file
- neg/globs: the third ignored key -> exit 1
- neg/no-scope: frontmatter with no scope key at all -> exit 1
- neg/two-keys: `paths:` plus `applyTo:` still fails; a right key does not
  excuse a wrong one shipping beside it
- neg/reports-every-rule: two bad rules produce two findings, not one
- edge/block-and-inline: both YAML forms of `paths:` pass (a line regex would
  fail the block form, which is how an earlier audit miscounted)
- neg/hollow-paths: `paths:` present but empty, wrong-typed, or holding an
  empty entry, in nine shapes; key presence is not scope
- neg/duplicate-key: `paths: []` then `paths: ["**"]` -> exit 1. A last-wins
  parse would certify the second; Claude Code may resolve the duplicate the
  other way, and that divergence is what this gate exists to prevent
- edge/no-frontmatter: a rule with no frontmatter is unscoped -> exit 1
- edge/malformed-yaml: unparsable frontmatter is unscoped -> exit 1
- edge/empty-rules-dir: a directory with no rules -> exit 2, never a vacuous pass
- edge/missing-rules-dir: no rules tree -> exit 2
- edge/invalid-root: non-existent root -> exit 2
- edge/non-md-ignored: a stray file that is not `*.md` is not a rule
- meta: the shipped `.claude/rules/` tree passes, and the pre-PR gate runs it
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_rule_scope_keys.py"
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_rule_scope_keys import (
    RulesDirectoryError,
    find_scope_key_violations,
    rule_files,
    validate_rule_scope_keys,
)

PATHS_BLOCK = 'paths:\n  - "**/*.py"\n  - "**/*.cs"\n'
PATHS_INLINE = 'paths: ["**"]\n'
APPLYTO = "applyTo: '**/*.py,**/*.cs'\n"
ALWAYS_APPLY = "alwaysApply: true\n"
GLOBS = 'globs: ["**/*.py"]\n'


def _rule(root: Path, name: str, frontmatter: str) -> Path:
    """Write one rule file with the given frontmatter body and return its path."""
    rules_dir = root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / f"{name}.md"
    path.write_text(f"---\n{frontmatter}---\n\n# {name}\n\nBody.\n", encoding="utf-8")
    return path


def _run_cli(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(repo_root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


# --- Positive -------------------------------------------------------------


def test_a_tree_scoped_with_paths_passes(tmp_path: Path) -> None:
    _rule(tmp_path, "code-rule", PATHS_BLOCK)
    _rule(tmp_path, "always-on-rule", f"{PATHS_INLINE}priority: critical\n")

    assert find_scope_key_violations(tmp_path) == []
    assert validate_rule_scope_keys(tmp_path) is True
    assert _run_cli(tmp_path).returncode == 0


def test_the_shipped_rules_tree_passes() -> None:
    """The repository's own rules must satisfy the gate that ships with them."""
    assert find_scope_key_violations(REPO_ROOT) == []


# --- Negative -------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "frontmatter", "expected_key"),
    [
        ("applyTo", f"description: x\n{APPLYTO}", "applyTo"),
        ("alwaysApply", f"description: x\n{ALWAYS_APPLY}", "alwaysApply"),
        ("globs", GLOBS, "globs"),
    ],
)
def test_an_ignored_scope_key_fails(
    tmp_path: Path, label: str, frontmatter: str, expected_key: str
) -> None:
    """Each key Claude Code ignores is caught, named, and exits 1."""
    _rule(tmp_path, label, frontmatter)

    findings = find_scope_key_violations(tmp_path)
    assert any(expected_key in reason for _, reason in findings), findings

    result = _run_cli(tmp_path)
    assert result.returncode == 1
    assert f"{label}.md" in result.stderr
    assert expected_key in result.stderr


def test_the_pragmatic_programmer_shape_is_caught(tmp_path: Path) -> None:
    """Negative control: the exact defect from issue #4871, verbatim key and value."""
    _rule(
        tmp_path,
        "pragmatic-programmer",
        "description: Pragmatic Programmer principles.\n"
        "applyTo: '**/*.py,**/*.cs,**/*.ts,**/*.tsx,**/*.js,**/*.jsx,**/*.go,"
        "**/*.rs,**/*.java,**/*.rb,**/*.c,**/*.h,**/*.cpp,**/*.ps1,**/*.psm1,"
        "**/*.psd1,**/*.sh,**/*.sql'\n",
    )

    assert validate_rule_scope_keys(tmp_path) is False
    assert _run_cli(tmp_path).returncode == 1


def test_the_code_quality_shape_is_caught(tmp_path: Path) -> None:
    """Negative control: the second defect from issue #4871, `alwaysApply: true`."""
    _rule(tmp_path, "code-quality", f"description: Baseline rules.\n{ALWAYS_APPLY}")

    assert validate_rule_scope_keys(tmp_path) is False
    assert _run_cli(tmp_path).returncode == 1


def test_a_rule_with_no_scope_key_fails(tmp_path: Path) -> None:
    """No scope key is the same outcome as a wrong one: it loads on every turn."""
    _rule(tmp_path, "unscoped", "description: x\n")

    findings = find_scope_key_violations(tmp_path)
    assert [reason for _, reason in findings] == [
        "declares no `paths:` key, so it loads on every session"
    ]
    assert _run_cli(tmp_path).returncode == 1


def test_paths_beside_an_ignored_key_still_fails(tmp_path: Path) -> None:
    """A correct key does not excuse a wrong one shipping next to it.

    Both keys reach `generate_rules.py`, whose `_SCOPE_KEYS` accepts either, so
    which one wins in the mirror is an ordering detail nobody should have to
    reason about.
    """
    _rule(tmp_path, "both", f"{PATHS_BLOCK}{APPLYTO}")

    findings = find_scope_key_violations(tmp_path)
    assert len(findings) == 1
    assert "applyTo" in findings[0][1]
    assert _run_cli(tmp_path).returncode == 1


def test_every_bad_rule_is_reported_not_just_the_first(tmp_path: Path) -> None:
    _rule(tmp_path, "one", APPLYTO)
    _rule(tmp_path, "two", ALWAYS_APPLY)
    _rule(tmp_path, "three", PATHS_BLOCK)

    findings = find_scope_key_violations(tmp_path)
    assert {path.stem for path, _ in findings} == {"one", "two"}

    result = _run_cli(tmp_path)
    assert "one.md" in result.stderr
    assert "two.md" in result.stderr
    assert "three.md" not in result.stderr


@pytest.mark.parametrize(
    ("frontmatter", "expected"),
    [
        ("paths:\n", "not a list"),
        ('paths: ""\n', "not a list"),
        ("paths: {}\n", "not a list"),
        ('paths: "**"\n', "not a list"),
        ("paths: []\n", "empty `paths:` list"),
        ('paths:\n  - ""\n', "empty or not a string"),
        ('paths:\n  - "   "\n', "empty or not a string"),
        ("paths:\n  - 42\n", "empty or not a string"),
        ('paths:\n  - "**/*.py"\n  - ""\n', "empty or not a string"),
    ],
)
def test_a_paths_key_with_no_usable_scope_fails(
    tmp_path: Path, frontmatter: str, expected: str
) -> None:
    """Key presence is not scope. An empty or wrong-typed value is the same leak."""
    _rule(tmp_path, "hollow", frontmatter)

    findings = find_scope_key_violations(tmp_path)
    assert len(findings) == 1
    assert expected in findings[0][1]

    result = _run_cli(tmp_path)
    assert result.returncode == 1
    assert "hollow.md" in result.stderr


# --- Edge -----------------------------------------------------------------


@pytest.mark.parametrize("frontmatter", [PATHS_BLOCK, PATHS_INLINE])
def test_both_yaml_forms_of_paths_pass(tmp_path: Path, frontmatter: str) -> None:
    """A line regex reads the block form as unscoped; the parser must not."""
    _rule(tmp_path, "scoped", frontmatter)

    assert find_scope_key_violations(tmp_path) == []


def test_a_rule_with_no_frontmatter_fails(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".claude" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "bare.md").write_text("# Bare\n\nNo frontmatter.\n", encoding="utf-8")

    assert _run_cli(tmp_path).returncode == 1


def test_a_duplicate_top_level_key_fails(tmp_path: Path) -> None:
    """`yaml.safe_load` keeps the last value; that would certify the wrong one.

    `paths: []` then `paths: ["**"]` passes a last-wins parse on the second
    entry. Nothing guarantees Claude Code resolves the duplicate the same way,
    and if it takes the first the rule is unscoped while the gate reports it
    clean. Reuses the duplicate-rejecting loader the mirror-side budget parser
    already ships (`instruction_budget_globs._UniqueKeySafeLoader`).
    """
    _rule(tmp_path, "twice", 'paths: []\npaths: ["**"]\n')

    findings = find_scope_key_violations(tmp_path)
    assert len(findings) == 1
    assert "cannot be resolved to one scope" in findings[0][1]

    result = _run_cli(tmp_path)
    assert result.returncode == 1
    assert "twice.md" in result.stderr


def test_a_duplicate_of_an_ignored_key_also_fails(tmp_path: Path) -> None:
    """A trailing `paths:` must not launder a leading `applyTo:` past the gate."""
    _rule(tmp_path, "laundered", "applyTo: '**'\napplyTo: '**/*.py'\n")

    assert _run_cli(tmp_path).returncode == 1


def test_malformed_frontmatter_fails(tmp_path: Path) -> None:
    """Unparsable YAML declares nothing, so the rule is unscoped."""
    _rule(tmp_path, "broken", "paths: [unclosed\n")

    assert validate_rule_scope_keys(tmp_path) is False
    assert _run_cli(tmp_path).returncode == 1


def test_an_empty_rules_directory_is_a_config_error(tmp_path: Path) -> None:
    """An empty survey must never read as a clean one."""
    (tmp_path / ".claude" / "rules").mkdir(parents=True)

    with pytest.raises(RulesDirectoryError, match="no \\*.md rule files"):
        rule_files(tmp_path)
    assert _run_cli(tmp_path).returncode == 2


def test_a_missing_rules_directory_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(RulesDirectoryError, match="not a directory"):
        rule_files(tmp_path)
    assert _run_cli(tmp_path).returncode == 2


def test_an_invalid_repository_root_is_a_config_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    assert _run_cli(missing).returncode == 2


def test_a_non_markdown_file_is_not_a_rule(tmp_path: Path) -> None:
    _rule(tmp_path, "scoped", PATHS_BLOCK)
    (tmp_path / ".claude" / "rules" / "notes.txt").write_text("applyTo: '**'\n", encoding="utf-8")

    assert [p.name for p in rule_files(tmp_path)] == ["scoped.md"]
    assert find_scope_key_violations(tmp_path) == []


# --- Wiring ---------------------------------------------------------------


def test_the_gate_is_wired_into_the_pre_pr_sequence() -> None:
    """An unwired validator does not gate anything."""
    from pre_pr_sequence import _SEQUENCE

    names = [gate.name for gate in _SEQUENCE]
    assert "Rule Scope Declarations (paths:)" in names, names


def test_the_gate_verdict_reaches_the_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive run_all_validations twice, differing only in the gate's verdict.

    The name assertion above still passes if the gate keeps its name but is
    wired to the wrong callable or to a constant-true stub. Calling the real
    runner with the validator monkeypatched proves the by-name resolution in
    `_root_only` reaches THIS validator's verdict, with the passing run as the
    control. Same shape as
    `tests/validation/test_check_citation_freshness_wiring.py`.
    """
    import argparse
    from types import SimpleNamespace

    import pre_pr_sequence

    gate_name = "Rule Scope Declarations (paths:)"
    verdicts: dict[str, bool] = {}

    def fake_run_validation(
        name: str, _state: object, callback: object, skip: bool = False
    ) -> bool:
        if name == gate_name and callable(callback):
            verdicts["gate"] = bool(callback())
        return True

    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    args = argparse.Namespace(quick=True, skip_tests=False, verbose=False)

    monkeypatch.setattr(pre_pr_sequence, "validate_rule_scope_declarations", lambda _r: False)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)
    assert verdicts["gate"] is False

    monkeypatch.setattr(pre_pr_sequence, "validate_rule_scope_declarations", lambda _r: True)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)
    assert verdicts["gate"] is True


def test_the_gate_runs_as_a_remote_check_not_only_a_local_hook() -> None:
    """A gate that only fires in a pre-push hook is not enforced on the remote.

    A push from a clone without `lefthook install`, from the web editor, or
    from the API bypasses the hook entirely. Deleting the workflow step would
    silently restore that gap, and no other test would notice.
    """
    workflow = REPO_ROOT / ".github" / "workflows" / "pr-validation.yml"
    body = workflow.read_text(encoding="utf-8")

    assert "scripts/validation/check_rule_scope_keys.py" in body, (
        f"{workflow.relative_to(REPO_ROOT).as_posix()} no longer invokes the rule "
        "scope gate; the check is back to being local-hook-only."
    )


def test_the_gate_skips_rather_than_fails_without_a_rules_tree(tmp_path: Path) -> None:
    """A downstream install carries no `.claude/rules/`; that is not a violation."""
    from checks_common import MissingScriptSkip
    from checks_tooling import validate_rule_scope_declarations

    with pytest.raises(MissingScriptSkip):
        validate_rule_scope_declarations(tmp_path)


def test_the_gate_adapter_reports_a_violation(tmp_path: Path) -> None:
    """The adapter must return the underlying verdict, not swallow it."""
    from checks_tooling import validate_rule_scope_declarations

    _rule(tmp_path, "bad", ALWAYS_APPLY)
    assert validate_rule_scope_declarations(tmp_path) is False

    _rule(tmp_path, "bad", PATHS_BLOCK)
    assert validate_rule_scope_declarations(tmp_path) is True
