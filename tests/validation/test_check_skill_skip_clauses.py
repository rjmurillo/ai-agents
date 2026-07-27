"""Tests for the sibling-family SKIP-clause validator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATION_DIR))

import check_skill_skip_clauses as skip_clauses  # noqa: E402
import checks_spec  # noqa: E402
import pre_pr_sequence  # noqa: E402


def _write_skill(root: Path, name: str, description: str | None) -> Path:
    path = root / ".claude" / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if description is None:
        text = f"---\nname: {name}\n---\n# {name}\n"
    else:
        text = f"---\nname: {name}\ndescription: {description!r}\n---\n# {name}\n"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_family_accepts_connected_non_pairwise_graph(tmp_path: Path) -> None:
    """Positive: connected routing passes without pairwise reciprocity."""
    _write_skill(tmp_path, "alpha-one", "Use for one. Do NOT use for two (use alpha-two).")
    _write_skill(
        tmp_path,
        "alpha-two",
        "Use for two. Do NOT use for three (use alpha-three).",
    )
    _write_skill(tmp_path, "alpha-three", "Use for three. Do NOT use for one (use alpha-one).")

    assert skip_clauses.main(["--repo-root", str(tmp_path)]) == 0


def test_single_member_and_empty_tree_pass(tmp_path: Path) -> None:
    """Edge: empty skill trees and single-member families do not crash or fail."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    assert skip_clauses.main(["--repo-root", str(tmp_path)]) == 0

    _write_skill(tmp_path, "solo", "Use for solo work with no sibling family.")
    assert skip_clauses.main(["--repo-root", str(tmp_path)]) == 0


def test_missing_description_in_family_fails(tmp_path: Path) -> None:
    """Negative: missing descriptions fail once a sibling family exists."""
    _write_skill(tmp_path, "beta-one", None)
    _write_skill(tmp_path, "beta-two", "Use for two. Do NOT use for one (use beta-one).")

    assert skip_clauses.main(["--repo-root", str(tmp_path)]) == 1


def test_route_to_non_sibling_fails(tmp_path: Path) -> None:
    """Negative: any family member route must name at least one real sibling."""
    _write_skill(tmp_path, "gamma-one", "Use for one. Do NOT use for search (use memory).")
    _write_skill(tmp_path, "gamma-two", "Use for two. Do NOT use for one (use gamma-one).")
    _write_skill(tmp_path, "memory", "Use for memory.")

    skill_files = (tmp_path / ".claude" / "skills").glob("*/SKILL.md")
    violations = skip_clauses.validate_skills(
        [skip_clauses.parse_skill_file(path) for path in skill_files]
    )

    assert any(v.code == "no-sibling-target" and v.skill == "gamma-one" for v in violations)
    assert skip_clauses.main(["--repo-root", str(tmp_path)]) == 1


def test_disconnected_family_fails(tmp_path: Path) -> None:
    """Negative: pairwise islands do not satisfy the family routing graph."""
    _write_skill(tmp_path, "delta-one", "Use for one. Do NOT use for two (use delta-two).")
    _write_skill(tmp_path, "delta-two", "Use for two. Do NOT use for one (use delta-one).")
    _write_skill(tmp_path, "delta-three", "Use for three. Do NOT use for four (use delta-four).")
    _write_skill(tmp_path, "delta-four", "Use for four. Do NOT use for three (use delta-three).")

    skill_files = (tmp_path / ".claude" / "skills").glob("*/SKILL.md")
    violations = skip_clauses.validate_skills(
        [skip_clauses.parse_skill_file(path) for path in skill_files]
    )

    assert any(v.code == "disconnected-family" for v in violations)
    assert skip_clauses.main(["--repo-root", str(tmp_path)]) == 1


def test_compound_parenthetical_extracts_each_real_skill() -> None:
    """Edge: one parenthetical may route to several sibling skills."""
    targets = skip_clauses.extract_skip_targets(
        "Do NOT use for adding citations (use memory or memory-enhancement).",
        {"memory", "memory-enhancement", "memory-search"},
    )

    assert targets == {"memory", "memory-enhancement"}


def test_malformed_frontmatter_is_reported_without_crashing(tmp_path: Path) -> None:
    """Edge: malformed YAML is a logic finding, not a traceback."""
    bad = tmp_path / ".claude" / "skills" / "epsilon-one" / "SKILL.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("---\ndescription: [unterminated\n---\n", encoding="utf-8")
    _write_skill(
        tmp_path,
        "epsilon-two",
        "Use for two. Do NOT use for one (use epsilon-one).",
    )

    assert skip_clauses.main(["--repo-root", str(tmp_path)]) == 1


def test_non_directory_skills_path_is_config_error(tmp_path: Path) -> None:
    """CLI exit-code check: an invalid skills path exits 2."""
    skills_path = tmp_path / "not-a-dir"
    skills_path.write_text("", encoding="utf-8")

    assert skip_clauses.main(["--skills-dir", str(skills_path)]) == 2


def test_real_tree_passes() -> None:
    """Positive: the committed skill tree satisfies the validator."""
    assert skip_clauses.main(["--repo-root", str(REPO_ROOT)]) == 0


def test_real_script_fails_on_broken_fixture(tmp_path: Path) -> None:
    """Negative subprocess control: the script exits 1 on a broken fixture."""
    _write_skill(tmp_path, "zeta-one", "Use for one without a SKIP clause.")
    _write_skill(tmp_path, "zeta-two", "Use for two. Do NOT use for one (use zeta-one).")
    script = REPO_ROOT / "scripts" / "validation" / "check_skill_skip_clauses.py"

    result = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(tmp_path)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
    )

    assert result.returncode == 1
    assert "[missing-skip-clause] zeta: zeta-one" in result.stdout


def test_checks_spec_wrapper_fails_on_script_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative: pre-PR wrapper treats script exit 1 as a hard failure."""
    monkeypatch.setattr(
        checks_spec,
        "_run_subprocess",
        lambda *_args, **_kwargs: (1, "Skill SKIP-clause violations:", ""),
    )

    assert checks_spec.validate_skill_skip_clauses(REPO_ROOT) is False


def test_checks_spec_wrapper_passes_on_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Positive: pre-PR wrapper passes only on script exit 0."""
    monkeypatch.setattr(
        checks_spec,
        "_run_subprocess",
        lambda *_args, **_kwargs: (0, "Skill SKIP clauses OK", ""),
    )

    assert checks_spec.validate_skill_skip_clauses(REPO_ROOT) is True


def test_pre_pr_sequence_wires_skip_clause_after_skill_shells() -> None:
    """Wiring: the new validator runs next to sibling skill validators."""
    recorded: list[str] = []

    def fake_run_validation(
        name: str, _state: object, _callback: object, skip: bool = False
    ) -> bool:
        recorded.append(name)
        return True

    state = SimpleNamespace(total=0, skipped=0)
    args = SimpleNamespace(quick=True, skip_tests=True, verbose=False)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)

    idx = recorded.index("Skill Shell Detection")
    assert recorded[idx + 1] == "Skill SKIP Clause Routing"
