from __future__ import annotations

import textwrap
from pathlib import Path

from scripts.validation.check_copilot_routing_exclusions import (
    RoutingViolation,
    load_excluded_skill_names,
    main,
    scan_copilot_skill_files,
    validate_copilot_routing_exclusions,
)


def test_repo_has_no_copilot_routing_violations(project_root: Path) -> None:
    assert validate_copilot_routing_exclusions(project_root)


def test_load_excluded_skill_names_filters_non_skill_files(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)

    excluded = load_excluded_skill_names(repo)

    assert excluded == {"merge-resolver"}


def test_skill_colon_reference_to_excluded_skill_is_violation(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)
    _write_skill(repo, "bad", "| Merge conflicts | Skill: merge-resolver |\n")

    violations = scan_copilot_skill_files(repo, {"merge-resolver"})

    assert _formatted(repo, violations) == [
        "src/copilot-cli/skills/bad/SKILL.md:1: merge-resolver: "
        "| Merge conflicts | Skill: merge-resolver |"
    ]


def test_bare_routing_table_reference_to_excluded_skill_is_violation(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)
    _write_skill(repo, "bad", "| Resolve merge conflicts | `merge-resolver` |\n")

    violations = scan_copilot_skill_files(repo, {"merge-resolver"})

    assert len(violations) == 1
    assert violations[0].skill_name == "merge-resolver"


def test_agent_references_to_excluded_skill_name_are_allowed(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)
    _write_skill(
        repo,
        "good",
        textwrap.dedent(
            """
            | Merge conflicts | Agent: merge-resolver |
            A failing trial merge means the conflict is real: resolve via merge-resolver agent.
            """
        ),
    )

    assert validate_copilot_routing_exclusions(repo)


def test_code_fence_reference_to_excluded_skill_name_is_ignored(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)
    _write_skill(
        repo,
        "example",
        textwrap.dedent(
            """
            ```markdown
            | Merge conflicts | Skill: merge-resolver |
            ```
            """
        ),
    )

    assert validate_copilot_routing_exclusions(repo)


def test_historical_prose_about_excluded_skill_name_is_allowed(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path)
    _write_skill(repo, "history", "This was also documented in the `merge-resolver` skill.\n")

    assert validate_copilot_routing_exclusions(repo)


def test_cli_returns_2_for_missing_config(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 2


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills" / "merge-resolver").mkdir(parents=True)
    (repo / ".claude" / "skills" / "merge-resolver" / "SKILL.md").write_text(
        "---\nname: merge-resolver\n---\n",
        encoding="utf-8",
    )
    _write(
        repo / "templates" / "platforms" / "copilot-cli.yaml",
        textwrap.dedent(
            """
            schemaVersion: "1.0"
            platform: copilot-cli
            artifacts:
              skills:
                sourceDir: ".claude/skills"
                outputDir: "src/copilot-cli/skills"
                excludeFilenames: ["AGENTS.md", "CLAUDE.md", "merge-resolver"]
            """
        ).lstrip(),
    )
    return repo


def _write_skill(repo: Path, name: str, body: str) -> None:
    _write(repo / "src" / "copilot-cli" / "skills" / name / "SKILL.md", body)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _formatted(repo: Path, violations: list[RoutingViolation]) -> list[str]:
    return [v.format(repo) for v in violations]
