"""ADR-121 decisions 12 and 13 in the plugin-root interpreter validator.

Decision 12: the locator's `uv run --frozen python` form is allowed only in a skill
flagged `distribution: repo-local`, and it skips rule 2's import scan.
Decision 13: a target named in `GUARDED_IMPORT_ALLOWANCES` may reach the named
third-party module while every import of it in the target's closure is guarded.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.validation import check_plugin_root_interpreter as checker
from scripts.validation import plugin_root_guarded_imports as guarded

# The sites module puts build/scripts on sys.path for the validator itself, so the
# recipe is reached through it and this test adds no path of its own.
from scripts.validation.plugin_root_interpreter_sites import plugin_run_launcher
from tests.validation.test_check_plugin_root_interpreter import REPO_ROOT, make_repo

ISOLATED_INTERPRETER = plugin_run_launcher.ISOLATED_INTERPRETER
UV_INTERPRETER = plugin_run_launcher.UV_INTERPRETER
render_locator = plugin_run_launcher.render_locator

GUARDED_YAML = "try:\n    import yaml\nexcept ImportError:\n    yaml = None\n"
UNGUARDED_YAML = "import yaml\n"
REPO_LOCAL_TEMPLATE = "---\nname: demo\nmetadata:\n  distribution: repo-local\n---\n\n"
SHIPPED_TEMPLATE = "---\nname: demo\n---\n\n"
TARGET = "skills/demo/scripts/run.py"
MAPPED = f".claude/{TARGET}"


def _scan(tmp_path: Path, files: dict[str, str], used: set | None = None) -> list[str]:
    return checker.scan(make_repo(tmp_path, files), used_guarded=used)


def _template(header: str, body: str) -> dict[str, str]:
    return {"templates/skills/demo.SKILL.md.tmpl": header + body}


# --- decision 12: the `uv` form is repo-local only -------------------------------------


def test_uv_locator_in_a_repo_local_skill_is_clean(tmp_path: Path) -> None:
    body = f"Run `{render_locator(TARGET, interpreter=UV_INTERPRETER)}`.\n"
    files = {MAPPED: "import json\n", **_template(REPO_LOCAL_TEMPLATE, body)}
    assert _scan(tmp_path, files) == []


def test_uv_locator_in_a_shipped_skill_is_an_offense(tmp_path: Path) -> None:
    body = f"Run `{render_locator(TARGET, interpreter=UV_INTERPRETER)}`.\n"
    files = {MAPPED: "import json\n", **_template(SHIPPED_TEMPLATE, body)}
    [offense] = _scan(tmp_path, files)
    assert offense.startswith("templates/skills/demo.SKILL.md.tmpl:5: ")
    assert "distribution: repo-local" in offense


def test_uv_locator_outside_any_skill_is_an_offense(tmp_path: Path) -> None:
    text = f"Run `{render_locator(TARGET, interpreter=UV_INTERPRETER)}`.\n"
    [offense] = _scan(tmp_path, {MAPPED: "import json\n", "README.md": text})
    assert "distribution: repo-local" in offense


def test_uv_locator_skips_the_import_scan(tmp_path: Path) -> None:
    """`uv` resolves the lock, so a third-party import is not a rule 2 offense there."""
    body = f"Run `{render_locator(TARGET, interpreter=UV_INTERPRETER)}`.\n"
    files = {MAPPED: UNGUARDED_YAML, **_template(REPO_LOCAL_TEMPLATE, body)}
    assert _scan(tmp_path, files) == []


def test_uv_locator_still_needs_a_tracked_target(tmp_path: Path) -> None:
    body = f"Run `{render_locator(TARGET, interpreter=UV_INTERPRETER)}`.\n"
    [offense] = _scan(tmp_path, _template(REPO_LOCAL_TEMPLATE, body))
    assert f"{MAPPED} is not a tracked file" in offense


def test_python3_locator_in_a_repo_local_skill_keeps_the_import_scan(tmp_path: Path) -> None:
    """Negative control: only the `uv` form skips rule 2's import scan."""
    body = f"Run `{render_locator(TARGET)}`.\n"
    files = {MAPPED: UNGUARDED_YAML, **_template(REPO_LOCAL_TEMPLATE, body)}
    [offense] = _scan(tmp_path, files)
    assert "imports yaml" in offense


def test_isolated_locator_is_judged_like_python3(tmp_path: Path) -> None:
    text = f"Run `{render_locator(TARGET, interpreter=ISOLATED_INTERPRETER)}`.\n"
    assert _scan(tmp_path, {MAPPED: "import json\n", "README.md": text}) == []
    [offense] = _scan(tmp_path / "dep", {MAPPED: UNGUARDED_YAML, "README.md": text})
    assert "imports yaml" in offense


@pytest.mark.parametrize(
    ("rel", "name"),
    [
        ("templates/skills/demo.SKILL.md.tmpl", "demo"),
        (".claude/skills/demo/SKILL.md", "demo"),
        ("src/claude/skills/demo/references/x.md", "demo"),
        ("src/hermes/project-toolkit-delivery/skills/demo/SKILL.md", "demo"),
        ("README.md", None),
        ("templates/agents/qa.shared.md", None),
    ],
)
def test_skill_name_of_reads_the_owning_skill(rel: str, name: str | None) -> None:
    assert guarded.skill_name_of(rel) == name


def test_a_bad_distribution_value_counts_as_shipped(tmp_path: Path) -> None:
    header = "---\nname: demo\nmetadata:\n  distribution: everywhere\n---\n\n"
    repo = make_repo(tmp_path, _template(header, "text\n"))
    assert guarded.is_repo_local_site(repo, "templates/skills/demo.SKILL.md.tmpl") is False


# --- decision 13: guarded-import allowances ----------------------------------------------


@pytest.fixture
def allow_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guarded, "GUARDED_IMPORT_ALLOWANCES", {(MAPPED, "yaml"): "test entry"})


def _locator_readme(target: str = TARGET) -> dict[str, str]:
    return {"README.md": f"Run `{render_locator(target)}`.\n"}


def test_a_guarded_import_without_an_allowance_still_fails(tmp_path: Path) -> None:
    [offense] = _scan(tmp_path, {MAPPED: GUARDED_YAML, **_locator_readme()})
    assert "imports yaml" in offense


@pytest.mark.usefixtures("allow_yaml")
def test_an_allowance_covers_a_guarded_import_and_is_recorded(tmp_path: Path) -> None:
    used: set = set()
    assert _scan(tmp_path, {MAPPED: GUARDED_YAML, **_locator_readme()}, used) == []
    assert used == {(MAPPED, "yaml")}


@pytest.mark.usefixtures("allow_yaml")
def test_an_allowance_does_not_cover_an_unguarded_import(tmp_path: Path) -> None:
    [offense] = _scan(tmp_path, {MAPPED: UNGUARDED_YAML, **_locator_readme()})
    assert f"{MAPPED} imports it with no fallback" in offense


@pytest.mark.usefixtures("allow_yaml")
def test_an_allowance_covers_one_module_only(tmp_path: Path) -> None:
    source = GUARDED_YAML + "import requests\n"
    [offense] = _scan(tmp_path, {MAPPED: source, **_locator_readme()})
    assert "imports requests" in offense and "yaml" not in offense


@pytest.mark.usefixtures("allow_yaml")
def test_an_allowance_follows_the_closure_to_a_guarded_sibling(tmp_path: Path) -> None:
    sibling = ".claude/skills/demo/scripts/helper.py"
    files = {MAPPED: "import helper\n", sibling: GUARDED_YAML, **_locator_readme()}
    assert _scan(tmp_path, files) == []


@pytest.mark.usefixtures("allow_yaml")
def test_an_unguarded_sibling_in_the_closure_voids_the_allowance(tmp_path: Path) -> None:
    sibling = ".claude/skills/demo/scripts/helper.py"
    files = {MAPPED: "import helper\n", sibling: UNGUARDED_YAML, **_locator_readme()}
    [offense] = _scan(tmp_path, files)
    assert f"{sibling} imports it with no fallback" in offense


@pytest.mark.usefixtures("allow_yaml")
def test_an_unguarded_child_started_through_sys_executable_voids_the_allowance(
    tmp_path: Path,
) -> None:
    """Rule 2's walk follows `sys.executable` children, so the guard check must too."""
    child = ".claude/skills/demo/scripts/child.py"
    parent = (
        GUARDED_YAML
        + "import subprocess, sys\n"
        + f'subprocess.run([sys.executable, "{child}"], check=True)\n'
    )
    files = {MAPPED: parent, child: UNGUARDED_YAML, **_locator_readme()}
    [offense] = _scan(tmp_path, files)
    assert f"{child} imports it with no fallback" in offense


@pytest.mark.usefixtures("allow_yaml")
def test_a_guarded_child_started_through_sys_executable_keeps_the_allowance(
    tmp_path: Path,
) -> None:
    child = ".claude/skills/demo/scripts/child.py"
    parent = (
        "import subprocess, sys\n" + f'subprocess.run([sys.executable, "{child}"], check=True)\n'
    )
    files = {MAPPED: parent, child: GUARDED_YAML, **_locator_readme()}
    assert _scan(tmp_path, files) == []


@pytest.mark.usefixtures("allow_yaml")
def test_an_allowance_used_only_by_shipped_yaml_is_recorded(tmp_path: Path) -> None:
    """Class G YAML keeps the legacy form; its use of an allowance must count."""
    legacy = f'python3 "${{COPILOT_PLUGIN_ROOT:-${{CLAUDE_PLUGIN_ROOT:-.claude}}}}/{TARGET}"'
    config = f"scripts:\n  run: {legacy}\n"
    used: set = set()
    files = {MAPPED: GUARDED_YAML, "src/claude/skills/demo/demo-config.yaml": config}
    assert _scan(tmp_path, files, used) == []
    assert used == {(MAPPED, "yaml")}


def test_an_allowance_for_another_target_does_not_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = {(".claude/skills/demo/scripts/other.py", "yaml"): "test entry"}
    monkeypatch.setattr(guarded, "GUARDED_IMPORT_ALLOWANCES", other)
    [offense] = _scan(tmp_path, {MAPPED: GUARDED_YAML, **_locator_readme()})
    assert "imports yaml" in offense


def test_stale_guarded_allowances_are_reported_for_this_checkout_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entry = (MAPPED, "yaml")
    monkeypatch.setattr(guarded, "GUARDED_IMPORT_ALLOWANCES", {entry: "test entry"})
    assert checker.guarded_stale(checker._REPO_ROOT, set()) == {entry}
    assert checker.guarded_stale(checker._REPO_ROOT, {entry}) == set()
    assert checker.guarded_stale(tmp_path, set()) == set()


def test_main_fails_on_a_stale_guarded_allowance(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(checker, "scan", lambda *args, **kwargs: [])
    monkeypatch.setattr(checker, "legacy_ratchet_messages", lambda *args: [])
    monkeypatch.setattr(checker, "tracked_files", lambda *args: ["x.md"])
    entry = (MAPPED, "yaml")
    monkeypatch.setattr(guarded, "GUARDED_IMPORT_ALLOWANCES", {entry: "test entry"})
    assert checker.main(["--repo-root", str(checker._REPO_ROOT)]) == 1
    err = capsys.readouterr().err
    assert f"guarded-import allowance matches no site: {MAPPED} yaml" in err


def test_the_committed_allowance_list_names_tracked_targets() -> None:
    for target, module in guarded.GUARDED_IMPORT_ALLOWANCES:
        assert (REPO_ROOT / target).is_file(), target
        assert module not in sys.stdlib_module_names
