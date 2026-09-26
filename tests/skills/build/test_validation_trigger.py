"""Tests for the build Phase 2b provenance/authority trigger (issue #5387).

`/build` Phase 2b decides, from verified changed paths and diff effects,
whether a change can alter validation semantics before Phase 3 edits any
file. These tests drive `validation_trigger.py` directly, one row per
REQ-041 acceptance criterion and per the TASK-050 fixture table, so each rule
is an assertion on real output, not on prose.

REQ-041 acceptance criteria covered here: AC3 (trigger activates on path and
effect cues, skips unrelated changes with a reason), AC4 (generated cue alone
is not a target), and the failure modes for an empty path list, an unknown
effect, and a missing `build_all.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

from tests.lib.vendored_copy import copy_vendored_entry

mod = import_skill_script(
    ".claude/skills/build/scripts/validation_trigger.py", module_name="test_validation_trigger_mod"
)

SKILLS_ROOT = PROJECT_ROOT / ".claude" / "skills"
COPILOT_SKILLS_ROOT = PROJECT_ROOT / "src" / "copilot-cli" / "skills"
_TIMEOUT_S = 60


def _decide(paths, effects=(), repo_root: Path = PROJECT_ROOT):
    return mod.decide(list(paths), list(effects), repo_root)


# TASK-050 fixture table: trigger-level activation/skip half of each row.
FIXTURE_ACTIVATE_CASES = [
    pytest.param(
        ["scripts/validation/check_x.py"], [], "validator-code", id="local-validator-change"
    ),
    pytest.param([".markdownlint-cli2.yaml"], [], "validator-config", id="local-config-fix"),
    pytest.param(
        ["src/claude/skills/x/scripts/check_x.py"],
        [],
        "generated-output",
        id="generated-mirror-of-a-validator",
    ),
    pytest.param(
        ["scripts/validation/foo.py"],
        ["baseline-update"],
        "validator-code",
        id="baseline-update-effect",
    ),
]


@pytest.mark.parametrize(("paths", "effects", "cue"), FIXTURE_ACTIVATE_CASES)
def test_fixture_table_activation_cases(paths, effects, cue) -> None:
    result = _decide(paths, effects)
    assert result["decision"] == "activate"
    target_paths = {t["path"] for t in result["targets"]}
    assert paths[0] in target_paths
    matched = next(t for t in result["targets"] if t["path"] == paths[0])
    assert cue in matched["cues"]


def test_vendored_validator_activates_via_effect() -> None:
    """A vendored-logic effect activates the gate even with no path cue.

    ``vendor/lint/rule.py`` matches no path cue (its directory is not the
    literal ``linters``), so the composing agent supplies the effect it
    verified in the diff body. The path itself is not promoted to a
    ``targets`` entry: only a matching path cue, or the ``generated-validator``
    effect on a generated-output path, does that (AC4).
    """
    result = _decide(["vendor/lint/rule.py"], ["vendored-logic"])
    assert result["decision"] == "activate"
    assert result["targets"] == []
    assert result["effects"] == ["vendored-logic"]


def test_unrelated_source_change_skips() -> None:
    """TASK-050 fixture row: `src/app/feature.py` -> trigger skip."""
    result = _decide(["src/app/feature.py"])
    assert result["decision"] == "skip"
    assert result["targets"] == []
    assert "src/app/feature.py" in result["reason"]


def test_generated_output_alone_does_not_activate() -> None:
    """AC4: a generated mirror of an ordinary skill is not a validation target."""
    result = _decide(["src/app/plain_module.py"])
    assert result["decision"] == "skip"


def test_generated_skill_md_of_an_ordinary_skill_does_not_activate() -> None:
    """A `.claude/skills/<name>/SKILL.md` whose template exists is generated-output
    only; with no validator cue and no activating effect it must not activate.
    """
    result = _decide([".claude/skills/memory/SKILL.md"])
    assert result["decision"] == "skip"


def test_generated_validator_effect_promotes_a_generated_only_path() -> None:
    result = _decide(["src/claude/skills/memory/SKILL.md"], ["generated-validator"])
    assert result["decision"] == "activate"
    target_paths = {t["path"] for t in result["targets"]}
    assert "src/claude/skills/memory/SKILL.md" in target_paths


@pytest.mark.parametrize(
    ("path", "cue"),
    [
        pytest.param(
            "scripts/validation/anything.py", "validator-code", id="scripts-validation-dir"
        ),
        pytest.param("tools/validators/rule.py", "validator-code", id="validators-dir"),
        pytest.param("tools/linters/rule.py", "validator-code", id="linters-dir"),
        pytest.param(
            ".claude/skills/x/scripts/validate_foo.py", "validator-code", id="skill-script-validate"
        ),
        pytest.param(
            ".claude/skills/x/scripts/scan_foo.py", "validator-code", id="skill-script-scan"
        ),
        pytest.param(
            ".claude/skills/x/scripts/validation_record.py",
            "validator-code",
            id="skill-script-validation",
        ),
        pytest.param(
            ".claude/skills/x/scripts/validator_rules.py",
            "validator-code",
            id="skill-script-validator",
        ),
        pytest.param(
            ".claude/skills/x/scripts/verify_claims.py", "validator-code", id="skill-script-verify"
        ),
        pytest.param(
            "scripts/validation/ratchet_totals.json", "ratchet-or-baseline", id="ratchet-file"
        ),
        pytest.param(
            "scripts/validation/coverage_baseline.json", "ratchet-or-baseline", id="baseline-file"
        ),
        pytest.param(".yamllint.yaml", "validator-config", id="yamllint"),
        pytest.param("PSScriptAnalyzerSettings.psd1", "validator-config", id="psscriptanalyzer"),
        pytest.param(".qualityrc.json", "validator-config", id="qualityrc"),
        pytest.param(".pre-commit-config.yaml", "validator-config", id="pre-commit"),
        pytest.param("lefthook.yml", "validator-config", id="lefthook"),
        pytest.param(".gitleaks.toml", "validator-config", id="gitleaks"),
        pytest.param("ruff.toml", "validator-config", id="ruff-toml"),
        pytest.param("tests/validation/test_x.py", "validation-fixture", id="tests-validation-dir"),
        pytest.param(
            "tests/validation/fixtures/case.json",
            "validation-fixture",
            id="fixtures-below-validation",
        ),
    ],
)
def test_every_path_cue_activates(path, cue) -> None:
    result = _decide([path])
    assert result["decision"] == "activate", result["reason"]
    matched = next(t for t in result["targets"] if t["path"] == path)
    assert cue in matched["cues"]


def test_windows_separators_classify_like_posix() -> None:
    result = _decide(["scripts\\validation\\check_x.py"])
    assert result["decision"] == "activate"


def test_mixed_change_lists_only_the_matching_target() -> None:
    result = _decide(["scripts/validation/check_x.py", "src/app/feature.py"])
    assert result["decision"] == "activate"
    target_paths = {t["path"] for t in result["targets"]}
    assert target_paths == {"scripts/validation/check_x.py"}


# Failure modes (REQ-041).


def test_empty_changed_path_list_is_a_config_error() -> None:
    with pytest.raises(mod.TriggerConfigError, match="no changed paths"):
        _decide([])


def test_blank_only_changed_paths_is_a_config_error() -> None:
    with pytest.raises(mod.TriggerConfigError, match="no changed paths"):
        _decide(["", "   "])


def test_unknown_effect_is_a_config_error() -> None:
    with pytest.raises(mod.TriggerConfigError, match="unknown effect"):
        _decide(["scripts/validation/check_x.py"], ["bogus"])


@pytest.mark.parametrize("effect", sorted(mod.EFFECTS))
def test_every_known_effect_is_accepted(effect: str) -> None:
    result = _decide(["scripts/validation/check_x.py"], [effect])
    assert result["decision"] == "activate"


def test_effect_names_are_case_and_space_insensitive() -> None:
    result = _decide(["scripts/validation/check_x.py"], ["  Baseline-Update "])
    assert result["decision"] == "activate"


def test_missing_build_all_reports_null_generated_roots_source(tmp_path: Path) -> None:
    """REQ-041 failure mode: a vendored install has no `build_all.py`."""
    result = _decide(["src/app/feature.py"], repo_root=tmp_path)
    assert result["generated_roots_source"] is None
    assert result["generated_roots_note"]
    # Every other cue still functions: a validator path still activates.
    still_works = _decide(["scripts/validation/check_x.py"], repo_root=tmp_path)
    assert still_works["decision"] == "activate"


def test_missing_build_all_disables_the_generated_output_cue_only(tmp_path: Path) -> None:
    result = _decide(["src/claude/skills/x/scripts/check_x.py"], repo_root=tmp_path)
    # validator-code (stem "check_x" starts with "check") still fires even
    # though generated-output cannot be evaluated without build_all.py.
    assert result["decision"] == "activate"
    matched = next(
        t for t in result["targets"] if t["path"] == "src/claude/skills/x/scripts/check_x.py"
    )
    assert "generated-output" not in matched["cues"]
    assert "validator-code" in matched["cues"]


def test_fixtures_directory_without_a_validation_ancestor_is_not_a_target() -> None:
    """`fixtures/` alone, with no `validation` ancestor segment, is not a cue."""
    result = _decide(["tests/unit/fixtures/case.json"])
    assert result["decision"] == "skip"


def test_non_skill_md_file_under_a_skill_directory_is_not_generated_output() -> None:
    """A 4-segment `.claude/skills/<name>/<file>` that is not `SKILL.md`."""
    result = _decide([".claude/skills/build/README.md"])
    assert result["decision"] == "skip"


def test_matches_owned_prefix_recognizes_an_exact_file_entry() -> None:
    """An `OWNED_PREFIXES` entry with no trailing slash is an exact-match file."""
    assert mod._matches_owned_prefix(".claude/settings.json", (".claude/settings.json",)) is True
    assert (
        mod._matches_owned_prefix(".claude/settings.json.bak", (".claude/settings.json",)) is False
    )


def test_read_owned_prefixes_accepts_a_plain_assign(tmp_path: Path) -> None:
    """Resilience: a plain ``Assign`` (not ``AnnAssign``) is also readable."""
    build_scripts = tmp_path / "build" / "scripts"
    build_scripts.mkdir(parents=True)
    (build_scripts / "build_all.py").write_text('OWNED_PREFIXES = ("src/",)\n', encoding="utf-8")
    prefixes = mod.read_owned_prefixes(build_scripts / "build_all.py")
    assert prefixes == ("src/",)


def test_read_owned_prefixes_rejects_a_file_with_no_assignment(tmp_path: Path) -> None:
    build_scripts = tmp_path / "build" / "scripts"
    build_scripts.mkdir(parents=True)
    (build_scripts / "build_all.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="OWNED_PREFIXES assignment not found"):
        mod.read_owned_prefixes(build_scripts / "build_all.py")


def test_unparseable_owned_prefixes_reports_a_note(tmp_path: Path) -> None:
    """A `build_all.py` with no `OWNED_PREFIXES` degrades like an absent file."""
    build_scripts = tmp_path / "build" / "scripts"
    build_scripts.mkdir(parents=True)
    (build_scripts / "build_all.py").write_text("x = 1\n", encoding="utf-8")
    result = _decide(["scripts/validation/check_x.py"], repo_root=tmp_path)
    assert result["generated_roots_source"] is None
    assert "unreadable" in result["generated_roots_note"]


def test_found_generated_roots_source_names_build_all_path() -> None:
    result = _decide(["src/app/feature.py"])
    assert result["generated_roots_source"] is not None
    assert result["generated_roots_source"].endswith("build_all.py")
    assert result["generated_roots_note"] is None


def test_repo_root_search_walks_up_from_a_subdirectory() -> None:
    result = _decide(["src/app/feature.py"], repo_root=PROJECT_ROOT / "tests" / "skills" / "build")
    assert result["generated_roots_source"] is not None


# CLI-level behavior.


def _run(script: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_S,
        check=False,
    )


def test_cli_emits_decision_as_json() -> None:
    result = _run(
        SKILLS_ROOT / "build" / "scripts" / "validation_trigger.py",
        PROJECT_ROOT,
        "--changed-path",
        "scripts/validation/check_x.py",
        "--repo-root",
        str(PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "activate"


def test_cli_exits_2_on_empty_changed_paths() -> None:
    result = _run(
        SKILLS_ROOT / "build" / "scripts" / "validation_trigger.py",
        PROJECT_ROOT,
        "--repo-root",
        str(PROJECT_ROOT),
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "no changed paths" in result.stderr


def test_cli_exits_2_on_unknown_effect() -> None:
    result = _run(
        SKILLS_ROOT / "build" / "scripts" / "validation_trigger.py",
        PROJECT_ROOT,
        "--changed-path",
        "README.md",
        "--effect",
        "bogus",
        "--repo-root",
        str(PROJECT_ROOT),
    )
    assert result.returncode == 2
    assert "unknown effect" in result.stderr


@pytest.fixture(params=["vendored-copy", "copilot-generated"])
def shipped_script(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """The trigger as a consumer gets it: standalone, no sibling skill needed."""
    if request.param == "copilot-generated":
        return COPILOT_SKILLS_ROOT / "build" / "scripts" / "validation_trigger.py"
    plugin_skills = tmp_path / "plugin" / "skills"
    plugin_skills.mkdir(parents=True)
    copy_vendored_entry(SKILLS_ROOT / "build", plugin_skills / "build")
    return plugin_skills / "build" / "scripts" / "validation_trigger.py"


def test_cli_runs_standalone_in_a_vendored_install(shipped_script: Path, tmp_path: Path) -> None:
    cwd = tmp_path / "consumer-repo"
    cwd.mkdir(exist_ok=True)
    result = _run(shipped_script, cwd, "--changed-path", "src/app/feature.py")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "skip"
    assert payload["generated_roots_source"] is None


def test_main_returns_2_and_prints_nothing_on_stdout_for_a_config_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert mod.main(["--repo-root", str(PROJECT_ROOT)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no changed paths" in captured.err


def test_main_prints_the_decision_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        mod.main(
            [
                "--changed-path",
                "scripts/validation/check_x.py",
                "--repo-root",
                str(PROJECT_ROOT),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "activate"


@pytest.mark.parametrize(
    "path",
    [
        "./scripts/validation/check_x.py",
        ".\\scripts\\validation\\check_x.py",
        "scripts/./validation/check_x.py",
    ],
)
def test_dot_and_backslash_spellings_are_normalized(path: str) -> None:
    """AC3: a `./` or backslash spelling cannot hide a validator change."""
    result = _decide([path])
    assert result["decision"] == "activate"
    assert result["targets"] == [
        {"path": "scripts/validation/check_x.py", "cues": ["validator-code"]}
    ]


def test_generated_skill_md_found_from_a_subdirectory() -> None:
    """AC4: the template lookup uses the root that holds build_all.py, not the cwd."""
    cues = mod.classify_path(".claude/skills/build/SKILL.md", PROJECT_ROOT / ".claude")
    assert "generated-output" in cues


def test_resolved_roots_can_be_reused_across_paths() -> None:
    """Callers resolve OWNED_PREFIXES once and pass the result to each check."""
    roots = mod.resolve_generated_roots(PROJECT_ROOT)
    assert mod.is_validation_target("scripts/validation/check_x.py", PROJECT_ROOT, roots)
    assert not mod.is_validation_target("src/app/feature.py", PROJECT_ROOT, roots)
