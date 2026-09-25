"""Routing tests for the ``/test`` Gate 5 DX trigger (issue #5386).

Gate 5 composes the ``dx-review`` skill only when a change can alter a
developer workflow. These tests drive ``dx_trigger.py`` directly, so each row
of the trigger matrix is an assertion on real output, not on prose. Each block
carries a negative control: a trigger stubbed to always activate, or to always
skip, fails at least one case below.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

from tests.lib.vendored_copy import copy_vendored_entry

mod = import_skill_script(
    ".claude/skills/test/scripts/dx_trigger.py", module_name="test_dx_trigger_mod"
)

SKILLS_ROOT = PROJECT_ROOT / ".claude" / "skills"
COPILOT_SKILLS_ROOT = PROJECT_ROOT / "src" / "copilot-cli" / "skills"
TEST_SKILL_MD = SKILLS_ROOT / "test" / "SKILL.md"
DX_SKILL_MD = SKILLS_ROOT / "dx-review" / "SKILL.md"
_TIMEOUT_S = 60


@pytest.fixture(scope="module")
def classifier():
    return mod.load_classifier()


def _decide(classifier, paths, effects=()):
    return mod.decide(list(paths), list(effects), classifier)


# Trigger matrix: every row the issue names, plus the fail-closed rows.
ACTIVATE_CASES = [
    pytest.param(["packages/ai-agents-cli/src/cli.ts"], "public-cli", id="public-cli-module"),
    pytest.param(["tools/bin/run.py"], "public-cli", id="public-cli-bin-dir"),
    pytest.param(["pkg/__main__.py"], "public-cli", id="public-cli-main"),
    pytest.param(["src/api.py"], "public-api", id="public-api-module"),
    pytest.param(["schemas/request.json"], "public-api", id="public-api-schema"),
    pytest.param(["pyproject.toml"], "install-onboarding", id="install-dependency-manifest"),
    pytest.param(["README.md"], "install-onboarding", id="onboarding-readme"),
    pytest.param(["docs/install.md"], "install-onboarding", id="onboarding-install-doc"),
    pytest.param([".claude/skills/dx-review/SKILL.md"], "harness-interface", id="harness-skill"),
    pytest.param([".claude/hooks/pre_tool_use.py"], "harness-interface", id="harness-hook"),
    pytest.param(["src/claude/agents/analyst.md"], "harness-interface", id="harness-agent"),
    pytest.param(
        ["src/copilot-cli/.claude-plugin/plugin.json"], "harness-interface", id="harness-manifest"
    ),
    pytest.param(["src/claude/hooks.json"], "harness-interface", id="harness-hooks-json"),
    pytest.param(["docs/user-guide.md"], "user-docs", id="docs-only-user-facing"),
    pytest.param(["CONTRIBUTING.md"], "contributor-workflow", id="contributor-guide"),
    pytest.param(["lefthook.yml"], "contributor-workflow", id="contributor-hooks"),
    pytest.param(
        [".github/ISSUE_TEMPLATE/bug.yml"], "contributor-workflow", id="contributor-issue-template"
    ),
]


@pytest.mark.parametrize(("paths", "journey"), ACTIVATE_CASES)
def test_developer_facing_change_activates(classifier, paths, journey) -> None:
    result = _decide(classifier, paths)
    assert result["decision"] == "activate"
    assert result["activate"] is True
    assert result["fail_closed"] is False
    assert journey in result["journeys"]
    assert result["reason"].startswith("activate - developer journeys: ")


SKIP_CASES = [
    pytest.param(
        ["tests/skills/review/test_select_axes.py"], "test or fixture only", id="test-refactor"
    ),
    pytest.param(["tests/fixtures/sample.json"], "test or fixture only", id="fixture"),
    pytest.param(
        [".claude/skills/review/tests/test_x.py"],
        "test or fixture only",
        id="test-under-skills-dir",
    ),
    pytest.param(
        [".agents/retrospective/2026-09-24.md"], "internal-only root .agents/", id="agents-root"
    ),
    pytest.param(
        [".project-toolkit/specs/x.md"], "internal-only root .project-toolkit/", id="toolkit-root"
    ),
    pytest.param([".serena/project.yml"], "internal-only root .serena/", id="serena-root"),
    pytest.param(["docs/architecture/overview.md"], "internal planning record", id="decision-doc"),
    pytest.param(["docs/planning/q3.md"], "internal planning record", id="roadmap-doc"),
    pytest.param([".github/workflows/ci.yml"], "CI or deploy pipeline file", id="ci-workflow"),
    pytest.param(["CODEOWNERS"], "repository metadata", id="codeowners"),
    pytest.param([".gitattributes"], "repository metadata", id="gitattributes"),
]


@pytest.mark.parametrize(("paths", "why"), SKIP_CASES)
def test_internal_only_change_skips_with_reason(classifier, paths, why) -> None:
    result = _decide(classifier, paths)
    assert result["decision"] == "skip"
    assert result["activate"] is False
    assert result["journeys"] == []
    assert result["internal_paths"] == {paths[0]: why}
    # The skip states why DX is not affected, naming the path and the evidence.
    assert result["reason"] == f"skip - every changed path is provably internal: {paths[0]} ({why})"


def test_skip_reason_names_every_path(classifier) -> None:
    paths = ["tests/test_a.py", ".agents/x.md", ".github/workflows/ci.yml"]
    result = _decide(classifier, paths)
    assert result["decision"] == "skip"
    for path in paths:
        assert path in result["reason"]


def test_one_developer_facing_path_activates_a_mixed_change(classifier) -> None:
    result = _decide(classifier, ["tests/test_a.py", ".agents/x.md", "README.md"])
    assert result["decision"] == "activate"
    assert result["path_journeys"] == {"README.md": ["install-onboarding", "user-docs"]}
    assert set(result["internal_paths"]) == {"tests/test_a.py", ".agents/x.md"}


@pytest.mark.parametrize(
    ("paths", "effects", "reason_prefix"),
    [
        pytest.param(
            ["scripts/foo.py"],
            [],
            "activate - fail-closed: not provably internal: ",
            id="unclassified-code",
        ),
        pytest.param(
            ["notes.txt"],
            [],
            "activate - fail-closed: not provably internal: ",
            id="unclassified-text",
        ),
        pytest.param([], [], "activate - fail-closed: no changed paths supplied", id="empty"),
        pytest.param(
            ["", "   "], [], "activate - fail-closed: no changed paths supplied", id="blank-only"
        ),
        pytest.param(
            ["tests/test_a.py"],
            ["bogus"],
            "activate - fail-closed: unknown effect bogus",
            id="unknown-effect",
        ),
    ],
)
def test_unprovable_change_fails_closed(classifier, paths, effects, reason_prefix) -> None:
    result = _decide(classifier, paths, effects)
    assert result["decision"] == "activate"
    assert result["fail_closed"] is True
    assert result["reason"].startswith(reason_prefix)


@pytest.mark.parametrize(("effect", "journey"), sorted(mod.EFFECTS.items()))
def test_verified_effect_activates_on_an_internal_path(classifier, effect, journey) -> None:
    result = _decide(classifier, ["tests/test_a.py"], [effect])
    assert result["decision"] == "activate"
    assert result["fail_closed"] is False
    assert result["journeys"] == [journey]


def test_effect_names_are_case_and_space_insensitive(classifier) -> None:
    result = _decide(classifier, ["tests/test_a.py"], ["  CLI-Surface "])
    assert result["journeys"] == ["public-cli"]
    assert result["unknown_effects"] == []


def test_windows_separators_classify_like_posix(classifier) -> None:
    result = _decide(classifier, ["tests\\skills\\test_a.py"])
    assert result["decision"] == "skip"


def test_review_categories_drive_the_decision() -> None:
    """The decision comes from the #4981 classifier, not a private taxonomy.

    A stub classifier that calls an arbitrary path an agent artifact must make
    the trigger activate the harness journey; one that calls it a test must
    make it skip.
    """
    as_agent = SimpleNamespace(classify_paths=lambda paths: (["agent-artifacts"], []))
    as_test = SimpleNamespace(classify_paths=lambda paths: (["tests-or-fixtures"], []))
    assert mod.decide(["zz/plain.dat"], [], as_agent)["journeys"] == ["harness-interface"]
    assert mod.decide(["zz/plain.dat"], [], as_test)["decision"] == "skip"


def test_every_review_category_is_either_mapped_or_left_to_fail_closed(classifier) -> None:
    """A category the trigger names must exist in the review classifier."""
    real = {row[0] for row in classifier._RISK_TABLE}
    named = set(mod._CATEGORY_JOURNEYS) | set(mod._INTERNAL_CATEGORIES)
    assert named <= real, named - real


def test_load_classifier_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        mod.load_classifier(tmp_path / "missing.py")


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


@pytest.fixture(params=["vendored-copy", "copilot-generated"])
def shipped_script(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """The trigger as a consumer gets it, with its sibling review skill."""
    if request.param == "copilot-generated":
        return COPILOT_SKILLS_ROOT / "test" / "scripts" / "dx_trigger.py"
    plugin_skills = tmp_path / "plugin" / "skills"
    plugin_skills.mkdir(parents=True)
    for name in ("test", "review"):
        copy_vendored_entry(SKILLS_ROOT / name, plugin_skills / name)
    return plugin_skills / "test" / "scripts" / "dx_trigger.py"


def test_cli_emits_decision_from_a_foreign_cwd(shipped_script: Path, tmp_path: Path) -> None:
    cwd = tmp_path / "consumer-repo"
    cwd.mkdir()
    result = _run(shipped_script, cwd, "--changed-path", "README.md")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "activate"
    assert "install-onboarding" in payload["journeys"]

    skipped = _run(shipped_script, cwd, "--changed-path", "tests/test_a.py")
    assert skipped.returncode == 0, skipped.stderr
    assert json.loads(skipped.stdout)["decision"] == "skip"


def test_cli_exits_2_when_the_classifier_is_missing(tmp_path: Path) -> None:
    script = SKILLS_ROOT / "test" / "scripts" / "dx_trigger.py"
    result = _run(
        script, tmp_path, "--classifier", str(tmp_path / "nope.py"), "--changed-path", "README.md"
    )
    assert result.returncode == 2
    assert "review-axis classifier not found" in result.stderr
    assert result.stdout == ""


def test_cli_exits_2_when_the_sibling_review_skill_is_absent(tmp_path: Path) -> None:
    """Negative control for the vendored test: without review/, no decision."""
    plugin_skills = tmp_path / "plugin" / "skills"
    plugin_skills.mkdir(parents=True)
    copy_vendored_entry(SKILLS_ROOT / "test", plugin_skills / "test")
    result = _run(
        plugin_skills / "test" / "scripts" / "dx_trigger.py",
        tmp_path,
        "--changed-path",
        "README.md",
    )
    assert result.returncode == 2


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## )", text, re.M | re.S)
    assert match, f"section {heading!r} missing"
    return match.group(1)


def test_gate5_composes_dx_review_instead_of_a_checklist() -> None:
    gate5 = _section(TEST_SKILL_MD.read_text(encoding="utf-8"), "Gate 5: Developer Experience (DX)")
    assert 'Skill(skill="dx-review")' in gate5
    assert "skills/test/scripts/dx_trigger.py" in gate5
    assert "DX CHANGE-SCOPE REPORT" in gate5
    assert 'Skill(skill="orphan-ref-validator")' in gate5
    # The duplicate generic checklist is gone.
    for stale in (
        "API ergonomics",
        "Debuggability",
        "developer advocate",
        'subagent_type="critic"',
    ):
        assert stale not in gate5
    # Exit-code contract named in prose, asserted by test_cli_exits_2_*.
    assert "Exit `2`" in gate5


def test_gate5_effect_list_matches_the_script() -> None:
    gate5 = _section(TEST_SKILL_MD.read_text(encoding="utf-8"), "Gate 5: Developer Experience (DX)")
    effects_line = gate5.split("Effects:", 1)[1].split(". ", 1)[0]
    assert set(re.findall(r"`([a-z-]+)`", effects_line)) == set(mod.EFFECTS)


def test_step0_runs_gate5_for_every_pr_type() -> None:
    step0 = _section(TEST_SKILL_MD.read_text(encoding="utf-8"), "Step 0: Classify PR Type")
    rows = [
        line for line in step0.splitlines() if re.match(r"\| (CODE|WORKFLOW|CONFIG|DOCS) \|", line)
    ]
    assert len(rows) == 4, rows
    for row in rows:
        assert "5" in row or "All 6" in row, row


def test_dx_review_change_scope_mode_preserves_the_evidence_contract() -> None:
    text = DX_SKILL_MD.read_text(encoding="utf-8")
    mode = _section(text, "Change-Scope Mode")
    for required in (
        "Reviewed user journey",
        "TESTED, PARTIAL, or INFERRED",
        "TTHW",
        "Skipped dimensions",
        "GATE_STATUS: Evidence Gate",
        "GATE_STATUS: Review Gate",
        "VERDICT: PASS|WARN|CRITICAL_FAIL|ERROR",
        "Activation:",
    ):
        assert required in mode, required
    journeys = set(re.findall(r"^\s*\| `([a-z-]+)` \|", mode, re.M))
    assert journeys == set(mod.JOURNEYS)


def test_main_prints_the_decision_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert mod.main(["--changed-path", "README.md", "--effect", "cli-surface"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["journeys"] == ["public-cli", "install-onboarding", "user-docs"]


def test_main_returns_2_on_a_missing_classifier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert mod.main(["--classifier", str(tmp_path / "nope.py")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "dx_trigger: review-axis classifier not found" in captured.err


def test_load_classifier_rejects_an_unloadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "select_axes.py"
    target.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod.importlib.util, "spec_from_file_location", lambda *a, **k: None)
    with pytest.raises(ImportError, match="cannot load review-axis classifier"):
        mod.load_classifier(target)
