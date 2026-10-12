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


def test_bare_path_in_markdown_is_left_to_the_markdown_ratchet(tmp_path: Path) -> None:
    # Inverse: the bare-path rule is YAML-only, so Markdown keeps its old result.
    readme = "Run `python3 .claude/skills/foo/scripts/bar.py` to sync.\n"
    assert _scan(tmp_path, {"README.md": readme}) == []


def test_allowance_suppresses_only_its_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = ("skills/demo/config.yaml", "bare-path", "skills/foo/scripts/bar.py")
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
    used: set[tuple[str, str, str]] = set()
    offenses = checker.scan(make_repo(tmp_path, {**_STDLIB, **files}), used)
    assert [o.split(": ", 1)[0] for o in offenses] == [
        f"{_CONFIG}:{2}",
        f"{_CONFIG}:{3}",
        f"{_OTHER}:{1}",
    ]
    assert used == {key}


def test_main_notes_an_allowance_that_no_longer_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key = ("skills/demo/config.yaml", "bare-path", "skills/foo/scripts/gone.py")
    monkeypatch.setattr(checker, "_YAML_ALLOWANCES", {key: "test reason"})
    repo = make_repo(tmp_path, {**_STDLIB, _CONFIG: "a: 1\n"})
    assert checker.main(["--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "allowance no longer matches: skills/demo/config.yaml bare-path" in out


def test_shipped_config_offenses_are_all_allowed() -> None:
    # Self-apply: the real config has offenses, and the allowance names each.
    used: set[tuple[str, str, str]] = set()
    assert checker.scan(REPO_ROOT, used) == []
    assert any(rule == "form" and "run_completion_gate" in tail for _, rule, tail in used)
    assert {path for path, _, _ in used} == {"skills/pr-review/pr-review-config.yaml"}


def test_shipped_config_is_reported_without_the_allowance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(checker, "_YAML_ALLOWANCES", {})
    offenses = checker.scan(REPO_ROOT)
    assert offenses
    assert all("pr-review-config.yaml" in offense for offense in offenses)
