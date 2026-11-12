"""The plugin-root interpreter validator reads the locator and ratchets the legacy form (ADR-121).

Rollout step 3. The validator accepts a site written as the locator, applies rules 1
and 2 to the script path inside it, and refuses the locator in shipped YAML (Class G).
The legacy form keeps passing through a counted baseline that only moves down.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.validation import check_plugin_root_interpreter as checker
from scripts.validation import plugin_root_interpreter_allowances as allowances
from scripts.validation import plugin_root_interpreter_ratchet as ratchet
from scripts.validation import plugin_root_interpreter_sites as sites
from tests.validation.test_check_plugin_root_interpreter import REPO_ROOT, make_repo

sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
from lib_hand_files import PLUGIN_LIB_FILES
from plugin_run_launcher import render_locator

_LEGACY_ROOT = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
_BAR = "skills/foo/scripts/bar.py"
_STDLIB = {f".claude/{_BAR}": "import json\n"}
_CONFIG = "src/claude/skills/demo/demo-config.yaml"


def _legacy(script_rel: str = _BAR) -> str:
    return f'python3 "{_LEGACY_ROOT}/{script_rel}"'


def _scan(tmp_path: Path, files: dict[str, str]) -> list[str]:
    return checker.scan(make_repo(tmp_path, {**_STDLIB, **files}))


# --- the locator: rules 1 and 2 read the target out of it ------------------


def test_locator_on_a_tracked_stdlib_script_is_clean(tmp_path: Path) -> None:
    text = f"Run `{render_locator(_BAR, '--flag')}` to sync.\n"
    assert _scan(tmp_path, {"README.md": text}) == []


def test_locator_in_a_fenced_block_is_clean(tmp_path: Path) -> None:
    locator = render_locator(_BAR, '"a b" -x')
    text = f"```bash\n{locator}\n```\n"
    assert _scan(tmp_path, {"README.md": text}) == []


def test_locator_naming_a_missing_script_is_a_dangling_target(tmp_path: Path) -> None:
    text = f"Run `{render_locator('skills/foo/scripts/missing.py')}`.\n"
    [offense] = _scan(tmp_path, {"README.md": text})
    assert offense.startswith("README.md:1: ")
    assert ".claude/skills/foo/scripts/missing.py is not a tracked file" in offense


def test_locator_naming_a_script_with_third_party_imports_is_flagged(tmp_path: Path) -> None:
    files = {
        ".claude/skills/foo/scripts/dep.py": "import yaml\n",
        "README.md": f"Run `{render_locator('skills/foo/scripts/dep.py')}`.\n",
    }
    [offense] = _scan(tmp_path, files)
    assert "imports yaml" in offense


def test_locator_and_legacy_form_get_the_same_verdict_on_one_target(tmp_path: Path) -> None:
    """Negative control: the legacy form is judged the same way, so neither form dodges rule 2."""
    files = {
        ".claude/skills/foo/scripts/dep.py": "import yaml\n",
        "legacy.md": f"Run `{_legacy('skills/foo/scripts/dep.py')}`.\n",
        "locator.md": f"Run `{render_locator('skills/foo/scripts/dep.py')}`.\n",
    }
    offenses = _scan(tmp_path, files)
    assert [o.split(":", 1)[0] for o in offenses] == ["legacy.md", "locator.md"]
    assert all("imports yaml" in o for o in offenses)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (
            render_locator("skills/x/y.py").replace("skills/x/y.py", "skills/../y.py"),
            "not a plugin",
        ),
        (render_locator("skills/x/y.py").replace("skills/x/y.py", "tools/y.py"), "not a plugin"),
        (render_locator("skills/x/y.py").split("; fi;")[0], "no closing text"),
    ],
)
def test_a_locator_that_does_not_read_back_is_reported(
    tmp_path: Path, text: str, reason: str
) -> None:
    [offense] = _scan(tmp_path, {"README.md": f"Run `{text}`.\n"})
    assert "malformed locator" in offense
    assert reason in offense


def test_a_declaration_marker_suppresses_a_locator_offense(tmp_path: Path) -> None:
    text = (
        "<!-- plugin-root-interpreter: example of a missing target -->\n"
        f"`{render_locator('skills/foo/scripts/missing.py')}`\n"
    )
    assert _scan(tmp_path, {"README.md": text}) == []


def test_rule_4_is_satisfied_by_the_locator_text(tmp_path: Path) -> None:
    text = f"Run `{render_locator(_BAR)}`.\n"
    assert checker.find_single_root_offenses(text, "templates/skills/x.SKILL.md.tmpl") == []
    only_claude = 'Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/foo/scripts/bar.py"`.\n'
    assert checker.find_single_root_offenses(only_claude, "templates/skills/x.SKILL.md.tmpl")


# --- Class G: the locator is refused in shipped YAML ----------------------


def test_locator_in_a_scripts_map_is_refused(tmp_path: Path) -> None:
    yaml_text = f"scripts:\n  run: '{render_locator(_BAR)}'\n"
    [offense] = _scan(tmp_path, {_CONFIG: yaml_text})
    assert offense.startswith(f"{_CONFIG}:2: ")
    assert "Class G" in offense
    assert "shlex" in offense


@pytest.mark.parametrize("placement", ["same line", "line above"])
def test_a_declared_locator_in_yaml_is_still_refused(tmp_path: Path, placement: str) -> None:
    """The YAML prohibition runs before declaration suppression, so a marker cannot hide it."""
    marker = "plugin-root-interpreter: example"
    locator = render_locator(_BAR)
    if placement == "same line":
        yaml_text = f"scripts:\n  run: '{locator}'  # {marker}\n"
    else:
        yaml_text = f"scripts:\n  # {marker}\n  run: '{locator}'\n"
    [offense] = _scan(tmp_path, {_CONFIG: yaml_text})
    assert "Class G" in offense


def test_a_declared_locator_in_markdown_is_still_suppressed(tmp_path: Path) -> None:
    """Negative control: only the YAML refusal ignores a declaration."""
    text = (
        f"<!-- plugin-root-interpreter: example -->\n`{render_locator('skills/foo/missing.py')}`\n"
    )
    assert _scan(tmp_path, {"README.md": text}) == []


def test_the_legacy_form_in_the_same_yaml_map_still_passes(tmp_path: Path) -> None:
    """Negative control: the refusal is about the locator, not about the file or the key."""
    yaml_text = f"scripts:\n  run: '{_legacy()} --x'\n"
    assert _scan(tmp_path, {_CONFIG: yaml_text}) == []


def test_the_locator_in_markdown_beside_that_yaml_passes(tmp_path: Path) -> None:
    """Negative control: the same locator text is fine where a model runs it."""
    files = {"src/claude/skills/demo/SKILL.md": f"`{render_locator(_BAR)}`\n"}
    assert _scan(tmp_path, files) == []


def test_a_yaml_allowance_cannot_cover_a_locator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    yaml_text = f"scripts:\n  run: '{render_locator(_BAR)}'\n"
    key = ("skills/demo/demo-config.yaml", "scripts.run", "locator-yaml", _BAR)
    monkeypatch.setattr(checker, "_YAML_ALLOWANCES", {key: "test reason"})
    repo = make_repo(tmp_path, {**_STDLIB, _CONFIG: yaml_text})
    used: set[tuple[str, str, str, str]] = set()
    [offense] = checker.scan(repo, used)
    assert "Class G" in offense
    assert used == set(), "the allowance must not be marked as used"


def test_an_allowance_does_cover_the_legacy_offense_it_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: the same table still absorbs the offenses it was written for."""
    yaml_text = f"scripts:\n  run: 'python3 .claude/{_BAR}'\n"
    key = ("skills/demo/demo-config.yaml", "scripts.run", "bare-path", _BAR)
    monkeypatch.setattr(checker, "_YAML_ALLOWANCES", {key: "test reason"})
    repo = make_repo(tmp_path, {**_STDLIB, _CONFIG: yaml_text})
    used: set[tuple[str, str, str, str]] = set()
    assert checker.scan(repo, used) == []
    assert used == {key}


# --- counting legacy sites ------------------------------------------------


def test_count_legacy_sites_counts_invocations_and_assignments_not_locators() -> None:
    text = (
        f"`{_legacy()} --a` and `{_legacy()}`\n"
        f'SCRIPTS_DIR="{_LEGACY_ROOT}/skills/foo"\n'
        f"`{render_locator(_BAR)}`\n"
        f"prose that names {_LEGACY_ROOT} but runs nothing\n"
    )
    assert sites.count_legacy_sites(text) == sites.LegacyCounts(invocations=2, assignments=1)


def test_a_suppressed_legacy_site_still_counts() -> None:
    text = f'<!-- plugin-root-interpreter: example -->\n`uv run python "{_LEGACY_ROOT}/{_BAR}"`\n'
    assert sites.count_legacy_sites(text).invocations == 1


def test_an_invocation_split_across_lines_counts_once() -> None:
    text = f'python3 \\\n    "{_LEGACY_ROOT}/{_BAR}" \\\n    --pr 1\n'
    assert sites.count_legacy_sites(text) == sites.LegacyCounts(invocations=1, assignments=0)


@pytest.mark.parametrize(
    ("rel", "group"),
    [
        ("templates/agents/architect.claude.md.tmpl", "templates/agents"),
        ("templates/skills/build.SKILL.md.tmpl", "templates/skills"),
        ("templates/skills/partials/x.mustache", "templates/skills"),
        ("templates/rules/universal.md", "templates/rules"),
        ("templates/AGENTS.md", "templates"),
        ("src/claude/skills/pr-review/references/x.md", "src/claude"),
        ("src/claude/skills/pr-review/scripts/x.py", "src/claude"),
        ("src/claude/skills/pr-review/pr-review-config.yaml", "src/claude yaml"),
        ("src/claude/AGENTS.md", "src/claude"),
        ("src/claude/lib/paths.py", "src/claude"),
        ("src/claude/lib/ptk_run.py", "src/claude"),
    ],
)
def test_authored_files_fall_in_a_group(rel: str, group: str) -> None:
    assert ratchet.authored_group(rel) == group


@pytest.mark.parametrize(
    "rel",
    [
        "src/claude/skills/pr-review/SKILL.md",
        "src/claude/agents/architect.md",
        "src/claude/rules/universal.md",
        "src/claude/hooks/hooks.json",
        "src/claude/lib/bootstrap.py",
        "src/claude/lib/hook_utilities/ptk_run.py",
        "src/copilot-cli/skills/pr-review/references/x.md",
        "src/codex/skills/pr-review/references/x.md",
        ".claude/agents/architect.md",
        "tests/validation/x.py",
        "scripts/validation/x.py",
    ],
)
def test_renders_and_other_trees_are_not_authored(rel: str) -> None:
    assert ratchet.authored_group(rel) is None


def test_every_hand_maintained_lib_module_is_authored() -> None:
    """Conformance: the ratchet reads the build's own list, so the two cannot drift."""
    assert PLUGIN_LIB_FILES
    for name in PLUGIN_LIB_FILES:
        assert ratchet.authored_group(f"src/claude/lib/{name}") == "src/claude"


def test_a_legacy_site_in_a_hand_maintained_lib_module_is_counted(tmp_path: Path) -> None:
    """A site added to ptk_run.py or paths.py must reach the ratchet, not hide as a render."""
    site = f'"""`{_legacy()}`"""\n'
    files = {f"src/claude/lib/{name}": site for name in PLUGIN_LIB_FILES}
    files["src/claude/lib/bootstrap.py"] = site
    counts: dict[str, sites.LegacyCounts] = {}
    checker.scan(make_repo(tmp_path, {**_STDLIB, **files}), legacy_counts=counts)
    assert counts == {"src/claude": sites.LegacyCounts(invocations=len(PLUGIN_LIB_FILES))}


def test_a_nested_skill_md_is_authored_support_text() -> None:
    """Only `skills/<name>/SKILL.md` is a render. A deeper file of that name is not."""
    assert ratchet.authored_group("src/claude/skills/x/references/SKILL.md") == "src/claude"


# --- the ratchet ----------------------------------------------------------


def _counts(**groups: tuple[int, int]) -> dict[str, sites.LegacyCounts]:
    return {name.replace("__", "/"): sites.LegacyCounts(*pair) for name, pair in groups.items()}


_BASELINE = {"templates/skills": (3, 1, "reason")}


def test_a_count_equal_to_the_baseline_passes() -> None:
    assert ratchet.ratchet_messages(_counts(templates__skills=(3, 1)), _BASELINE) == []


@pytest.mark.parametrize("found", [(4, 1), (3, 2), (9, 0)])
def test_a_count_above_the_baseline_fails(found: tuple[int, int]) -> None:
    [message] = ratchet.ratchet_messages(_counts(templates__skills=found), _BASELINE)
    assert "templates/skills" in message
    assert "lower the baseline when a batch migrates" in message
    assert "locator" in message


@pytest.mark.parametrize("found", [(2, 1), (3, 0), (0, 0)])
def test_a_count_below_the_baseline_fails_so_the_room_cannot_be_reused(
    found: tuple[int, int],
) -> None:
    [message] = ratchet.ratchet_messages(_counts(templates__skills=found), _BASELINE)
    assert "lower the baseline when a batch migrates" in message
    assert "LEGACY_SITE_BASELINE" in message


def test_a_new_group_has_a_baseline_of_zero() -> None:
    [message] = ratchet.ratchet_messages(_counts(templates__agents=(1, 0)), {})
    assert "templates/agents" in message


def test_a_group_in_the_baseline_but_absent_from_the_scan_fails() -> None:
    [message] = ratchet.ratchet_messages({}, _BASELINE)
    assert "templates/skills" in message


def test_tally_adds_to_the_running_count() -> None:
    counts: dict[str, sites.LegacyCounts] = {}
    ratchet.tally(counts, "g", sites.LegacyCounts(1, 2))
    ratchet.tally(counts, "g", sites.LegacyCounts(3, 4))
    assert counts == {"g": sites.LegacyCounts(4, 6)}


def test_the_committed_baseline_names_only_groups_that_exist() -> None:
    known = {"templates/agents", "templates/skills", "src/claude", "src/claude yaml"}
    assert set(allowances.LEGACY_SITE_BASELINE) <= known
    assert all(isinstance(v[2], str) and v[2] for v in allowances.LEGACY_SITE_BASELINE.values())


# --- the ratchet inside main ----------------------------------------------


def _owned_repo(tmp_path: Path, sites_in_template: int) -> Path:
    body = "".join(f"`{_legacy()} --n {n}`\n" for n in range(sites_in_template))
    return make_repo(tmp_path, {**_STDLIB, "templates/skills/demo.SKILL.md.tmpl": body})


def _no_other_allowances(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty the tables that name files of this checkout, so a fixture repo is not stale."""
    monkeypatch.setattr(checker, "_YAML_ALLOWANCES", {})
    monkeypatch.setattr(checker, "_SINGLE_ROOT_ALLOWANCES", {})


def _own(
    monkeypatch: pytest.MonkeyPatch, repo: Path, baseline: dict[str, tuple[int, int, str]]
) -> None:
    monkeypatch.setattr(checker, "_REPO_ROOT", repo.resolve())
    monkeypatch.setattr(allowances, "LEGACY_SITE_BASELINE", baseline)
    _no_other_allowances(monkeypatch)


def test_main_passes_at_the_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _owned_repo(tmp_path, 2)
    _own(monkeypatch, repo, {"templates/skills": (2, 0, "x")})
    assert checker.main(["--repo-root", str(repo)]) == 0


def test_main_fails_when_a_new_legacy_site_raises_the_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _owned_repo(tmp_path, 3)
    _own(monkeypatch, repo, {"templates/skills": (2, 0, "x")})
    assert checker.main(["--repo-root", str(repo)]) == 1
    assert "lower the baseline when a batch migrates" in capsys.readouterr().err


def test_main_fails_when_a_batch_migrated_and_the_baseline_stayed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _owned_repo(tmp_path, 1)
    _own(monkeypatch, repo, {"templates/skills": (2, 0, "x")})
    assert checker.main(["--repo-root", str(repo)]) == 1
    assert "lower the baseline when a batch migrates" in capsys.readouterr().err


def test_a_locator_in_a_template_does_not_raise_the_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = f"`{_legacy()}`\n`{render_locator(_BAR)}`\n"
    repo = make_repo(tmp_path, {**_STDLIB, "templates/skills/demo.SKILL.md.tmpl": body})
    _own(monkeypatch, repo, {"templates/skills": (1, 0, "x")})
    assert checker.main(["--repo-root", str(repo)]) == 0


def test_a_render_is_not_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = {
        **_STDLIB,
        "templates/skills/demo.SKILL.md.tmpl": f"`{_legacy()}`\n",
        "src/claude/skills/demo/SKILL.md": f"`{_legacy()}`\n",
        "src/copilot-cli/skills/demo/SKILL.md": f"`{_legacy()}`\n",
    }
    repo = make_repo(tmp_path, files)
    _own(monkeypatch, repo, {"templates/skills": (1, 0, "x")})
    assert checker.main(["--repo-root", str(repo)]) == 0


def test_a_scan_of_another_root_is_not_held_to_this_checkouts_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_other_allowances(monkeypatch)
    repo = _owned_repo(tmp_path, 5)
    assert checker.main(["--repo-root", str(repo)]) == 0
    counts = {"templates/skills": sites.LegacyCounts(5)}
    assert checker.legacy_ratchet_messages(repo.resolve(), counts) == []
