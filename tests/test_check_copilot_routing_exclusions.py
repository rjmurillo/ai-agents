from pathlib import Path
import shutil
import textwrap

import pytest

from scripts.validation.check_copilot_routing_exclusions import (
    _load_excluded_skill_names,
    _scan_skill_files,
    validate_copilot_routing_exclusions,
)


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_repo_has_no_copilot_routing_violations(project_root: Path):
    # Run against the repository root and expect no violations after the fix.
    ok = validate_copilot_routing_exclusions(project_root)
    assert ok, "Expected no Copilot routing exclusions after applying fixes"


def test_validator_positive_and_negative(tmp_path: Path):
    # Build a minimal fake repo
    repo = tmp_path / "repo"
    (repo / "templates" / "platforms").mkdir(parents=True)
    copilot_yaml = textwrap.dedent("""
    artifacts:
      skills:
        excludeFilenames: ["merge-resolver", "internal-skill"]
    """)
    write_file(repo / "templates" / "platforms" / "copilot-cli.yaml", copilot_yaml)

    # Good file: uses Agent: merge-resolver (allowed)
    good_md = """
    # Some skill doc
    Agent: merge-resolver
    """
    write_file(repo / "src" / "copilot-cli" / "skills" / "good" / "SKILL.md", good_md)

    # Bad file: uses Skill: merge-resolver (should be flagged)
    bad_md = """
    | Merge conflicts | Skill: merge-resolver |
    """
    write_file(repo / "src" / "copilot-cli" / "skills" / "bad" / "SKILL.md", bad_md)

    ok = validate_copilot_routing_exclusions(repo)
    assert not ok, "Validator should detect the Skill: merge-resolver occurrence"

    # Ensure the low-level APIs behave as expected
    names = _load_excluded_skill_names(repo)
    assert "merge-resolver" in names

    violations = _scan_skill_files(repo, names)
    assert violations, "Expected violations list to be non-empty"
    assert any("Skill: merge-resolver" in v for v in violations)
