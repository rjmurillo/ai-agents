"""YAML coverage for the plugin-root interpreter validator (issue #6195).

Shipped YAML (``pr-review-config.yaml`` command and scripts-map strings) runs
plugin scripts too, so the validator reads it under the same two rules as
Markdown, plus one YAML-only rule: a bare ``.claude/skills/...`` operand must be
written through the plugin root (plugin-self-containment MUST 2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import check_plugin_root_interpreter as checker
from scripts.validation.check_plugin_frontmatter_self_containment import plugin_roots
from scripts.validation.plugin_root_interpreter_allowances import yaml_key_paths
from tests.validation.test_check_plugin_root_interpreter import REPO_ROOT, make_repo

_ROOT = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
_CONFIG = ".claude/skills/demo/config.yaml"
_OTHER = ".claude/skills/other/config.yaml"
_STDLIB = {".claude/skills/foo/scripts/bar.py": "import json\n"}
_BARE_BAR = 'a: "python3 .claude/skills/foo/scripts/bar.py"\n'


def _scan(tmp_path: Path, files: dict[str, str]) -> list[str]:
    return checker.scan(make_repo(tmp_path, {**_STDLIB, **files}))


def test_plugin_root_python3_in_yaml_is_clean(tmp_path: Path) -> None:
    yaml_text = f"scripts:\n  run: 'python3 \"{_ROOT}/skills/foo/scripts/bar.py\" --x'\n"
    assert _scan(tmp_path, {_CONFIG: yaml_text}) == []


def test_uv_run_on_plugin_root_operand_in_yaml_is_flagged(tmp_path: Path) -> None:
    yaml_text = f"scripts:\n  run: 'uv run python \"{_ROOT}/skills/foo/scripts/bar.py\"'\n"
    [offense] = _scan(tmp_path, {_CONFIG: yaml_text})
    assert offense.startswith(f"{_CONFIG}:2: ")
    assert "'uv run python'" in offense


def test_third_party_target_in_yaml_is_flagged(tmp_path: Path) -> None:
    files = {
        ".claude/skills/foo/scripts/dep.py": "import yaml\n",
        _CONFIG: f"run: 'python3 \"{_ROOT}/skills/foo/scripts/dep.py\"'\n",
    }
    [offense] = _scan(tmp_path, files)
    assert "imports yaml" in offense


def test_bare_path_python3_in_yaml_is_flagged(tmp_path: Path) -> None:
    yaml_text = 'completion:\n  - command: "python3 .claude/skills/foo/scripts/bar.py --pr {pr}"\n'
    [offense] = _scan(tmp_path, {_CONFIG: yaml_text})
    assert offense.startswith(f"{_CONFIG}:2: ")
    assert "bare .claude/skills/foo/scripts/bar.py" in offense
    assert "MUST 2" in offense


@pytest.mark.parametrize(
    "operand",
    [
        "./.claude/skills/foo/scripts/bar.py",
        ".claude//skills/foo/scripts/bar.py",
        ".claude/./skills/foo/scripts/bar.py",
        "../.claude/skills/foo/scripts/bar.py",
        ".claude/skills//foo/./scripts/bar.py",
        ".//.claude/skills/foo/scripts/bar.py",
    ],
)
def test_path_spelling_variants_are_flagged_like_the_literal(tmp_path: Path, operand: str) -> None:
    [offense] = _scan(tmp_path, {_CONFIG: f'run: "python3 {operand} --x"\n'})
    assert offense.startswith(f"{_CONFIG}:1: ")
    assert "bare .claude/skills/foo/scripts/bar.py" in offense


def test_spelling_variant_with_uv_run_is_one_form_offense(tmp_path: Path) -> None:
    yaml_text = 'run: "uv run python ./.claude/skills/foo/scripts/bar.py"\n'
    [offense] = _scan(tmp_path, {_CONFIG: yaml_text})
    assert "'uv run python'" in offense


def test_spelling_variant_outside_skills_stays_clean(tmp_path: Path) -> None:
    assert _scan(tmp_path, {_CONFIG: 'run: "python3 ./.claude//lib/helper.py"\n'}) == []


def test_declaration_suppresses_a_spelling_variant(tmp_path: Path) -> None:
    yaml_text = (
        "# plugin-root-interpreter: repo-only entry, kept bare on purpose\n"
        'run: "python3 ./.claude/skills/foo/scripts/bar.py"\n'
    )
    assert _scan(tmp_path, {_CONFIG: yaml_text}) == []


def test_uv_run_on_bare_path_is_one_form_offense(tmp_path: Path) -> None:
    yaml_text = 'verify: "uv run python .claude/skills/foo/scripts/bar.py --json"\n'
    [offense] = _scan(tmp_path, {_CONFIG: yaml_text})
    assert "'uv run python'" in offense


def test_quoted_bare_operand_is_flagged(tmp_path: Path) -> None:
    yaml_text = "run: python3 '.claude/skills/foo/scripts/bar.py'\n"
    assert len(_scan(tmp_path, {_CONFIG: yaml_text})) == 1


def test_yml_extension_is_scanned(tmp_path: Path) -> None:
    yaml_text = 'run: "python3 .claude/skills/foo/scripts/bar.py"\n'
    assert len(_scan(tmp_path, {".claude/skills/demo/config.yml": yaml_text})) == 1


def test_declaration_comment_above_a_yaml_entry_suppresses_it(tmp_path: Path) -> None:
    yaml_text = (
        "# plugin-root-interpreter: repo-only entry, kept bare on purpose\n"
        'run: "python3 .claude/skills/foo/scripts/bar.py"\n'
    )
    assert _scan(tmp_path, {_CONFIG: yaml_text}) == []


@pytest.mark.parametrize(
    "line",
    [
        'run: "python3 scripts/validation/check.py"',
        'run: "python3 .claude/lib/helper.py"',
        "note: the bare .claude/skills/foo/scripts/bar.py path is shown here",
    ],
)
def test_yaml_lines_that_are_not_plugin_script_invocations_are_clean(
    tmp_path: Path, line: str
) -> None:
    assert _scan(tmp_path, {_CONFIG: f"{line}\n"}) == []


def test_yaml_outside_the_plugin_roots_is_not_scanned(tmp_path: Path) -> None:
    # Repository CI runs plugin scripts under uv on purpose.
    workflow = 'run: "uv run python .claude/skills/foo/scripts/bar.py"\n'
    assert _scan(tmp_path, {".github/workflows/ci.yml": workflow}) == []
    assert checker.is_in_scope(".github/workflows/ci.yml") is False
    assert checker.is_in_scope("src/copilot-cli/skills/x/config.yaml") is True


def test_every_declared_plugin_root_is_scanned_for_yaml() -> None:
    # Converse: a new marketplace source must not ship YAML this gate never reads.
    declared = {f"{root}/" for root in plugin_roots(REPO_ROOT)}
    assert declared - set(checker._PLUGIN_ROOTS) == set()


def test_bare_path_in_markdown_is_left_to_the_markdown_ratchet(tmp_path: Path) -> None:
    # Inverse: the bare-path rule is YAML-only, so Markdown keeps its old result.
    readme = "Run `python3 .claude/skills/foo/scripts/bar.py` to sync.\n"
    assert _scan(tmp_path, {"README.md": readme}) == []


def test_allowance_suppresses_only_its_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = ("skills/demo/config.yaml", "a", "bare-path", "skills/foo/scripts/bar.py")
    monkeypatch.setattr(checker, "_YAML_ALLOWANCES", {key: "test reason"})
    files = {
        ".claude/skills/foo/scripts/baz.py": "import json\n",
        "src/copilot-cli/skills/demo/config.yaml": _BARE_BAR,
        _CONFIG: (
            _BARE_BAR + 'b: "python3 .claude/skills/foo/scripts/baz.py"\n'
            'c: "uv run python .claude/skills/foo/scripts/bar.py"\n'
        ),
        _OTHER: _BARE_BAR,
    }
    used: set[tuple[str, str, str, str]] = set()
    offenses = checker.scan(make_repo(tmp_path, {**_STDLIB, **files}), used)
    assert [o.split(": ", 1)[0] for o in offenses] == [
        f"{_CONFIG}:{2}",
        f"{_CONFIG}:{3}",
        f"{_OTHER}:{1}",
    ]
    assert used == {key}


def test_main_fails_on_an_allowance_that_no_longer_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Issue #6506: a stale allowance fails the run so it cannot hide a later offense."""
    key = ("skills/demo/config.yaml", "a", "bare-path", "skills/foo/scripts/gone.py")
    monkeypatch.setattr(checker, "_YAML_ALLOWANCES", {key: "test reason"})
    repo = make_repo(tmp_path, {**_STDLIB, _CONFIG: "a: 1\n"})
    assert checker.main(["--repo-root", str(repo)]) == 1
    captured = capsys.readouterr()
    assert "allowance no longer matches: skills/demo/config.yaml a bare-path" in captured.err
    assert "0 offense(s), 1 stale allowance(s)" in captured.err
    assert "OK" not in captured.out


def test_main_passes_when_every_allowance_still_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key = ("skills/demo/config.yaml", "a", "bare-path", "skills/foo/scripts/bar.py")
    monkeypatch.setattr(checker, "_YAML_ALLOWANCES", {key: "test reason"})
    repo = make_repo(
        tmp_path,
        {**_STDLIB, ".claude/skills/foo/scripts/bar.py": "import json\n", _CONFIG: _BARE_BAR},
    )
    assert checker.main(["--repo-root", str(repo)]) == 0
    assert "no longer matches" not in capsys.readouterr().err


def test_shipped_config_offenses_are_all_allowed() -> None:
    # Self-apply: the real config has offenses, and the allowance names each.
    used: set[tuple[str, str, str, str]] = set()
    assert checker.scan(REPO_ROOT, used) == []
    # The verifier lives in the pr-review SKILL.md, not the config (issue #5520),
    # so no config command may invoke run_completion_gate.py.
    assert not any("run_completion_gate" in tail for _, _, _, tail in used)
    assert {path for path, _, _, _ in used} == {"skills/pr-review/pr-review-config.yaml"}


def test_shipped_config_is_reported_without_the_allowance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(checker, "_YAML_ALLOWANCES", {})
    offenses = checker.scan(REPO_ROOT)
    assert offenses
    assert all("pr-review-config.yaml" in offense for offense in offenses)


def test_yaml_key_paths_follow_indentation_and_list_items() -> None:
    text = (
        "scripts:\n"
        "  claude_code:\n"
        "    # comment\n"
        '    get: "python3 x"\n'
        "  copilot:\n"
        '    get: "python3 y"\n'
        "completion_criteria:\n"
        '  - name: "One"\n'
        '    command: "python3 z"\n'
    )
    assert yaml_key_paths(text) == [
        "scripts",
        "scripts.claude_code",
        "scripts.claude_code",
        "scripts.claude_code.get",
        "scripts.copilot",
        "scripts.copilot.get",
        "completion_criteria",
        "completion_criteria.name",
        "completion_criteria.command",
    ]


@pytest.mark.parametrize("header", ["|", ">", "|-", ">+", "|2", "| # note"])
def test_yaml_key_paths_ignore_key_like_lines_in_a_block_scalar(header: str) -> None:
    text = f"scripts:\n  run: {header}\n    fake_key: value\n\n    other: python3 x\n  next: 1\n"
    assert yaml_key_paths(text) == [
        "scripts",
        "scripts.run",
        "scripts.run",
        "scripts.run",
        "scripts.run",
        "scripts.next",
    ]


def test_yaml_key_paths_block_scalar_in_a_list_item_ends_at_dedent() -> None:
    text = (
        "criteria:\n"
        "  - name: One\n"
        "    command: |\n"
        "      inner: not a key\n"
        "    after: 1\n"
        "  - plain\n"
    )
    assert yaml_key_paths(text) == [
        "criteria",
        "criteria.name",
        "criteria.command",
        "criteria.command",
        "criteria.after",
        "criteria",
    ]


def test_yaml_key_paths_value_that_only_resembles_a_header_is_a_key_line() -> None:
    # `a: |x` is a plain scalar, so the next deeper line still parses normally.
    assert yaml_key_paths("a: |x\n  b: 1\n") == ["a", "a.b"]


def test_block_scalar_text_does_not_corrupt_the_allowance_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Without the fix `commands:` inside the block pops `run` and re-keys the offense,
    # so the allowance for `scripts.run` would not match.
    yaml_text = "scripts:\n  run: |\n    commands:\n    python3 .claude/skills/foo/scripts/bar.py\n"
    key = ("skills/demo/config.yaml", "scripts.run", "bare-path", "skills/foo/scripts/bar.py")
    monkeypatch.setattr(checker, "_YAML_ALLOWANCES", {key: "test reason"})
    used: set[tuple[str, str, str, str]] = set()
    assert checker.scan(make_repo(tmp_path, {**_STDLIB, _CONFIG: yaml_text}), used) == []
    assert used == {key}


def test_allowance_does_not_cover_a_new_key_for_the_same_script(tmp_path: Path) -> None:
    # The allowed claude_code entry stays quiet; the same bare call under a
    # new key is reported, so an allowance cannot absorb a new regression.
    script = ".claude/skills/github/scripts/pr/get_pr_context.py"
    config = (
        "scripts:\n"
        "  claude_code:\n"
        f'    get_pr_context: "python3 {script} --pull-request {{number}}"\n'
        "  copilot:\n"
        f'    new_check: "python3 {script}"\n'
    )
    config_path = ".claude/skills/pr-review/pr-review-config.yaml"
    files = {script: "import json\n", config_path: config}
    [offense] = checker.scan(make_repo(tmp_path, files))
    assert offense.startswith(f"{config_path}:{5}: ")
