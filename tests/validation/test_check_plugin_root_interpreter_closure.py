"""Rules 4 and 5 of the plugin-root interpreter validator (plugin-self-containment MUST 4).

Rule 4 fails a file that names the Claude plugin-root variable without the
Copilot one. Rule 5 fails a shipped skill or lib module whose module-level import
needs a third-party package with no fallback. Each rule has a negative control
(the offense it must catch) and a positive control (the shape it must leave alone).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_plugin_root_interpreter as checker
from scripts.validation import plugin_root_interpreter_rules as rules
from tests.validation.test_check_plugin_root_interpreter import make_repo

CLAUDE = "CLAUDE_PLUGIN_ROOT"
COPILOT = "COPILOT_PLUGIN_ROOT"
NESTED = "${" + COPILOT + ":-${" + CLAUDE + ":-.claude}}"
SINGLE = "${" + CLAUDE + ":-.claude}"


def _lines(text: str) -> list[int]:
    logical, maps = checker._join_continuations(text)
    return rules.single_root_lines(logical, maps)


# --- rule 4: detector ------------------------------------------------------


def test_nested_form_is_clean() -> None:
    assert _lines(f'SCRIPTS_DIR="{NESTED}/skills/github/scripts"\n') == []


def test_single_root_command_is_flagged() -> None:
    assert _lines(f'SCRIPTS_DIR="{SINGLE}/skills/github/scripts"\n') == [1]


def test_single_root_command_is_flagged_even_beside_a_sentence_naming_both() -> None:
    text = f'Set {COPILOT} or {CLAUDE}.\nSCRIPTS_DIR="{SINGLE}/skills"\n'
    assert _lines(text) == [2]


def test_continued_list_naming_both_variables_is_one_clean_statement() -> None:
    text = f'for root in \\\n  "${{{COPILOT}:-}}" \\\n  "${{{CLAUDE}:-}}" \\\n  .claude; do\n'
    assert _lines(text) == []


def test_continued_list_naming_only_the_claude_variable_is_flagged() -> None:
    text = f'for root in \\\n  "${{{CLAUDE}:-}}" \\\n  .claude; do\n'
    assert _lines(text) == [2]


def test_name_in_a_resolver_pairs_with_the_copilot_read_on_the_next_line() -> None:
    text = f'a = os.environ.get("{COPILOT}")\nb = os.environ.get("{CLAUDE}")\n'
    assert _lines(text) == []


def test_name_alone_is_flagged() -> None:
    assert _lines(f'b = os.environ.get("{CLAUDE}")\n') == [1]


def test_name_pairing_stops_at_the_window() -> None:
    window = rules.NAME_PAIRING_WINDOW
    assert _lines(f"{COPILOT}{chr(10) * window}{CLAUDE}\n") == []
    assert _lines(f"{COPILOT}{chr(10) * (window + 1)}{CLAUDE}\n") == [window + 2]


def test_powershell_form_is_flagged() -> None:
    assert _lines(f"$p = $env:{CLAUDE}\n") == [1]


@pytest.mark.parametrize("text", ["", "no variable here\n", "\n\n"])
def test_text_without_the_variable_is_clean(text: str) -> None:
    assert _lines(text) == []


# --- rule 4: checker -------------------------------------------------------


def _offenses(tmp_path: Path, files: dict[str, str]) -> list[str]:
    return checker.scan(make_repo(tmp_path, files))


def test_scan_flags_single_root_in_a_skill_reference(tmp_path: Path) -> None:
    path = "src/claude/skills/demo/references/run.md"
    [offense] = _offenses(tmp_path, {path: f'SCRIPTS_DIR="{SINGLE}/skills/x"\n'})
    assert offense.startswith(f"{path}:1: ")
    assert "MUST 4" in offense


@pytest.mark.parametrize(
    "path",
    [
        "templates/skills/demo.SKILL.md.tmpl",
        "templates/agents/demo.claude.md.tmpl",
        "src/claude/agents/demo.md",
        "src/claude/rules/demo.md",
        "src/claude/lib/demo.py",
        "src/copilot-cli/skills/demo/SKILL.md",
        ".claude/skills/demo/references/run.md",
        "scripts/demo.py",
        "build/scripts/demo.py",
    ],
)
def test_scan_covers_every_plugin_content_tree(tmp_path: Path, path: str) -> None:
    [offense] = _offenses(tmp_path, {path: f'x="{SINGLE}/skills"\n'})
    assert offense.startswith(f"{path}:1: ")


def test_scan_leaves_nested_form_clean(tmp_path: Path) -> None:
    path = "src/claude/skills/demo/references/run.md"
    assert _offenses(tmp_path, {path: f'x="{NESTED}/skills"\n'}) == []


def test_scan_ignores_tests_and_unlisted_trees(tmp_path: Path) -> None:
    files = {"tests/fixture.md": f"x={SINGLE}\n", "docs/note.md": f"x={SINGLE}\n"}
    assert _offenses(tmp_path, files) == []


def test_scan_ignores_binary_suffixes(tmp_path: Path) -> None:
    assert _offenses(tmp_path, {"src/claude/skills/demo/data.bin": f"x={SINGLE}\n"}) == []


def test_declaration_marker_suppresses_one_line(tmp_path: Path) -> None:
    text = f'# plugin-root-interpreter: documents the legacy form\nx="{SINGLE}"\n'
    assert _offenses(tmp_path, {"src/claude/skills/demo/a.md": text}) == []


def test_allowance_absorbs_its_exact_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(checker._SINGLE_ROOT_ALLOWANCES, "skills/demo/a.md", (1, "test"))
    used: set[str] = set()
    repo = make_repo(tmp_path, {"src/claude/skills/demo/a.md": f"x={SINGLE}\n"})
    assert checker.scan(repo, used_single_root=used) == []
    assert "skills/demo/a.md" in used


def test_allowance_does_not_cover_a_new_statement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(checker._SINGLE_ROOT_ALLOWANCES, "skills/demo/a.md", (1, "test"))
    text = f"x={SINGLE}\n\n\n\n\n\n\ny={SINGLE}\n"
    [offense] = _offenses(tmp_path, {"src/claude/skills/demo/a.md": text})
    assert offense.startswith("src/claude/skills/demo/a.md:8: ")


def test_allowance_larger_than_the_file_needs_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(checker._SINGLE_ROOT_ALLOWANCES, "skills/demo/a.md", (2, "test"))
    [offense] = _offenses(tmp_path, {"src/claude/skills/demo/a.md": f"x={SINGLE}\n"})
    assert "allowance expects 2" in offense
    assert "found 1" in offense


def test_unmatched_allowance_fails_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(checker._SINGLE_ROOT_ALLOWANCES, "skills/gone/a.md", (1, "test"))
    repo = make_repo(tmp_path, {"README.md": "hello\n"})
    assert checker.main(["--repo-root", str(repo)]) == 1
    assert "skills/gone/a.md" in capsys.readouterr().err


def test_full_path_allowance_beats_the_tree_stripped_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude's hooks.json is allowed; the Copilot render of the same name is not."""
    monkeypatch.setitem(checker._SINGLE_ROOT_ALLOWANCES, "src/claude/hooks/hooks.json", (1, "t"))
    files = {
        "src/claude/hooks/hooks.json": f'"command": "{SINGLE}"\n',
        "src/copilot-cli/hooks/hooks.json": f'"command": "{SINGLE}"\n',
    }
    [offense] = _offenses(tmp_path, files)
    assert offense.startswith("src/copilot-cli/hooks/hooks.json:1: ")


def test_symlinked_copy_is_not_scanned_twice(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"src/claude/hooks/a.py": f"x={SINGLE}\n"})
    (repo / ".claude").mkdir()
    try:
        (repo / ".claude/a.py").symlink_to("../src/claude/hooks/a.py")
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create symlinks")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    staged = subprocess.run(
        ["git", "ls-files", "-s", ".claude/a.py"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    if not staged.startswith("120000"):
        pytest.skip("git did not record the link as a symlink on this host")
    assert len(checker.scan(repo)) == 1


# --- rule 5: detector ------------------------------------------------------


def _third_party(source: str, repo_modules: frozenset[str] = frozenset()) -> list[str]:
    found = rules.unguarded_third_party_imports(source, repo_modules.__contains__)
    return [name for _, name in found]


def test_unguarded_top_level_import_is_flagged() -> None:
    assert _third_party("import yaml\n") == ["yaml"]


def test_from_import_and_submodule_are_flagged_by_root() -> None:
    assert _third_party("from jsonschema.validators import X\nimport a.b.c\n") == [
        "jsonschema",
        "a",
    ]


def test_standard_library_and_future_are_clean() -> None:
    assert _third_party("from __future__ import annotations\nimport json, os.path\n") == []


def test_repository_module_is_clean() -> None:
    assert _third_party("import hook_utilities\n", frozenset({"hook_utilities"})) == []


def test_relative_import_is_clean() -> None:
    assert _third_party("from . import sibling\nfrom .pkg import thing\n") == []


def test_import_inside_a_function_is_lazy_and_clean() -> None:
    assert _third_party("def f():\n    import yaml\n") == []
    assert _third_party("async def f():\n    import yaml\n") == []


def test_guarded_import_with_fallback_is_clean() -> None:
    source = "try:\n    import yaml\nexcept ImportError:\n    yaml = None\n"
    assert _third_party(source) == []


@pytest.mark.parametrize(
    "caught", ["ModuleNotFoundError", "(ImportError, OSError)", "Exception", ""]
)
def test_guard_forms_that_catch_the_failure_are_clean(caught: str) -> None:
    source = f"try:\n    import yaml\nexcept {caught}:\n    yaml = None\n".replace(
        "except :", "except:"
    )
    assert _third_party(source) == []


def test_guard_that_reraises_is_flagged() -> None:
    source = "try:\n    import yaml\nexcept ImportError:\n    raise\n"
    assert _third_party(source) == ["yaml"]


def test_guard_that_exits_is_flagged() -> None:
    source = "import sys\ntry:\n    import yaml\nexcept ImportError:\n    sys.exit(2)\n"
    assert _third_party(source) == ["yaml"]


def test_guard_that_catches_something_else_is_flagged() -> None:
    source = "try:\n    import yaml\nexcept ValueError:\n    yaml = None\n"
    assert _third_party(source) == ["yaml"]


def test_import_in_the_handler_is_not_guarded() -> None:
    source = "try:\n    import json\nexcept ImportError:\n    import yaml\n"
    assert _third_party(source) == ["yaml"]


def test_import_under_a_conditional_runs_at_import_time() -> None:
    assert _third_party("import sys\nif sys.platform == 'win32':\n    import yaml\n") == ["yaml"]


def test_type_checking_import_never_runs() -> None:
    source = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import yaml\n"
    assert _third_party(source) == []


def test_negated_type_checking_import_runs_at_import_time() -> None:
    source = "from typing import TYPE_CHECKING\nif not TYPE_CHECKING:\n    import yaml\n"
    assert _third_party(source) == ["yaml"]


def test_import_in_a_module_level_match_case_is_flagged() -> None:
    source = "match 1:\n    case 1:\n        import yaml\n    case _:\n        import json\n"
    assert _third_party(source) == ["yaml"]


def test_guarded_import_in_a_match_case_is_clean() -> None:
    source = (
        "match 1:\n    case 1:\n        try:\n            import yaml\n"
        "        except ImportError:\n            yaml = None\n"
    )
    assert _third_party(source) == []


def test_type_checking_else_branch_still_runs() -> None:
    source = "TYPE_CHECKING = False\nif TYPE_CHECKING:\n    pass\nelse:\n    import yaml\n"
    assert _third_party(source) == ["yaml"]


def test_syntax_error_propagates() -> None:
    with pytest.raises(SyntaxError):
        _third_party("def (:\n")


# --- rule 5: checker -------------------------------------------------------


def test_scan_flags_unguarded_import_in_a_skill_script(tmp_path: Path) -> None:
    path = "src/claude/skills/demo/scripts/run.py"
    [offense] = _offenses(tmp_path, {path: "import yaml\n"})
    assert offense.startswith(f"{path}:1: imports yaml at module level")
    assert "MUST 4" in offense


def test_scan_flags_unguarded_import_in_lib(tmp_path: Path) -> None:
    [offense] = _offenses(tmp_path, {"src/claude/lib/pkg/mod.py": "import jsonschema\n"})
    assert "imports jsonschema" in offense


def test_scan_accepts_lazy_and_guarded_imports(tmp_path: Path) -> None:
    files = {
        "src/claude/skills/demo/scripts/lazy.py": "def f():\n    import yaml\n",
        "src/claude/skills/demo/scripts/guarded.py": (
            "try:\n    import yaml\nexcept ImportError:\n    yaml = None\n"
        ),
    }
    assert _offenses(tmp_path, files) == []


def test_scan_resolves_sibling_modules_as_repository_code(tmp_path: Path) -> None:
    files = {
        "src/claude/skills/demo/scripts/run.py": "import helper\n",
        "src/claude/skills/demo/scripts/helper.py": "import json\n",
    }
    assert _offenses(tmp_path, files) == []


def test_scan_does_not_check_imports_outside_shipped_trees(tmp_path: Path) -> None:
    files = {"scripts/tool.py": "import yaml\n", "tests/test_x.py": "import yaml\n"}
    assert _offenses(tmp_path, files) == []


def test_scan_reports_unparseable_shipped_module_as_config_error(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"src/claude/skills/demo/scripts/bad.py": "def (:\n"})
    with pytest.raises(checker.ScanError, match="bad.py"):
        checker.scan(repo)
