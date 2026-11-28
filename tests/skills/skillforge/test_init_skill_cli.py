"""CLI contract of skillforge init_skill.py: --dry-run writes nothing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "claude"
    / "skills"
    / "skillforge"
    / "scripts"
    / "init_skill.py"
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_dry_run_reports_target_and_creates_nothing(tmp_path: Path) -> None:
    result = run("my-skill", "--path", str(tmp_path), "--dry-run")

    assert result.returncode == 0
    assert "Dry run: would create" in result.stdout
    assert not (tmp_path / "my-skill").exists()


def test_real_run_creates_the_scaffold(tmp_path: Path) -> None:
    result = run("my-skill", "--path", str(tmp_path))

    assert result.returncode == 0
    assert (tmp_path / "my-skill" / "SKILL.md").is_file()


def test_dry_run_still_refuses_an_existing_directory(tmp_path: Path) -> None:
    (tmp_path / "my-skill").mkdir()

    result = run("my-skill", "--path", str(tmp_path), "--dry-run")

    assert result.returncode == 1
    assert "already exists" in result.stderr


def test_dry_run_still_rejects_a_bad_name(tmp_path: Path) -> None:
    result = run("Bad_Name", "--path", str(tmp_path), "--dry-run")

    assert result.returncode == 2
    assert result.stdout == ""


def test_dry_run_still_rejects_a_missing_parent(tmp_path: Path) -> None:
    result = run("my-skill", "--path", str(tmp_path / "absent"), "--dry-run")

    assert result.returncode == 2


# Docs page scaffold (rule agent-skill-docs MUST 1 and 3)

_README = """\
# Skills

## Code quality

| Skill | Slash command | Use it to |
| --- | --- | --- |
| [`alpha`](alpha.md) | match | Do alpha |

## Related

- [Agents](../agents/README.md)
"""


def _docs_repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "src" / "claude" / "skills").mkdir(parents=True)
    for kind in ("skills", "agents"):
        (tmp_path / "docs" / kind).mkdir(parents=True)
    (tmp_path / "docs" / "skills" / "README.md").write_text(_README, encoding="utf-8")
    (tmp_path / "docs" / "agents" / "README.md").write_text("# Agents\n", encoding="utf-8")
    return tmp_path


def _gate():
    from scripts.validation import check_agent_skill_docs

    return check_agent_skill_docs


def test_scaffold_writes_page_and_row_that_pass_the_gate(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    page = repo / "docs" / "skills" / "my-skill.md"
    assert not page.exists()

    result = run(
        "my-skill",
        "--path",
        str(repo / "src" / "claude" / "skills"),
        "--docs-section",
        "Code quality",
    )

    assert result.returncode == 0, result.stderr
    assert page.is_file()
    readme = (repo / "docs" / "skills" / "README.md").read_text(encoding="utf-8")
    code_quality = readme.split("## Related")[0]
    assert "[`my-skill`](my-skill.md)" in code_quality
    (repo / "docs" / "skills" / "alpha.md").write_text(
        page.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (repo / "src" / "claude" / "skills" / "alpha").mkdir()
    (repo / "src" / "claude" / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\n---\n", encoding="utf-8"
    )
    assert _gate().find_page_findings(repo).findings == []


def test_scaffold_without_section_prints_row_and_leaves_readme(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)

    result = run("my-skill", "--path", str(repo / "src" / "claude" / "skills"))

    assert result.returncode == 0
    assert (repo / "docs" / "skills" / "my-skill.md").is_file()
    assert (repo / "docs" / "skills" / "README.md").read_text(encoding="utf-8") == _README
    assert "| [`my-skill`](my-skill.md) |" in result.stdout


def test_scaffold_with_unknown_section_prints_row(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)

    result = run(
        "my-skill", "--path", str(repo / "src" / "claude" / "skills"), "--docs-section", "Nope"
    )

    assert result.returncode == 0
    assert "has no table" in result.stdout
    assert (repo / "docs" / "skills" / "README.md").read_text(encoding="utf-8") == _README


def test_scaffold_leaves_an_existing_page_alone(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    page = repo / "docs" / "skills" / "my-skill.md"
    page.write_text("# Hand written\n", encoding="utf-8")

    result = run(
        "my-skill",
        "--path",
        str(repo / "src" / "claude" / "skills"),
        "--docs-section",
        "Code quality",
    )

    assert result.returncode == 0
    assert page.read_text(encoding="utf-8") == "# Hand written\n"


def test_repository_without_docs_readme_gets_no_page(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    result = run("my-skill", "--path", str(tmp_path), "--docs-section", "Code quality")

    assert result.returncode == 0
    assert not (tmp_path / "docs").exists()
    assert "Docs page" not in result.stdout


def test_dry_run_names_the_docs_page_and_writes_nothing(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    readme = repo / "docs" / "skills" / "README.md"
    before = readme.read_text(encoding="utf-8")

    result = run("my-skill", "--path", str(repo / "src" / "claude" / "skills"), "--dry-run")

    assert result.returncode == 0
    assert "my-skill.md" in result.stdout
    assert f"would leave {readme} unchanged" in result.stdout
    assert "would add a row" not in result.stdout
    assert not (repo / "docs" / "skills" / "my-skill.md").exists()
    assert readme.read_text(encoding="utf-8") == before

    selected = run(
        "my-skill",
        "--path",
        str(repo / "src" / "claude" / "skills"),
        "--docs-section",
        "Code quality",
        "--dry-run",
    )

    assert selected.returncode == 0
    assert "would add a row under '## Code quality'" in selected.stdout
    assert not (repo / "docs" / "skills" / "my-skill.md").exists()
    assert readme.read_text(encoding="utf-8") == before


def test_skill_outside_the_skill_folders_gets_no_page(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    (repo / "scratch").mkdir()

    for skill, parent in (("at-root", repo), ("in-scratch", repo / "scratch")):
        result = run(skill, "--path", str(parent), "--docs-section", "Code quality")

        assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in (repo / "docs" / "skills").iterdir()) == ["README.md"]
    assert (repo / "docs" / "skills" / "README.md").read_text(encoding="utf-8") == _README


def test_dot_slash_row_counts_as_existing(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    readme = repo / "docs" / "skills" / "README.md"
    readme.write_text(
        _README.replace(
            "| match | Do alpha |", "| match | Do alpha |\n| [x](./my-skill.md) | match | Old |"
        ),
        encoding="utf-8",
    )
    before = readme.read_text(encoding="utf-8")

    result = run(
        "my-skill",
        "--path",
        str(repo / "src" / "claude" / "skills"),
        "--docs-section",
        "Code quality",
    )

    assert result.returncode == 0
    assert "README row exists" in result.stdout
    assert readme.read_text(encoding="utf-8") == before


def test_row_lands_in_alphabetical_order(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    readme = repo / "docs" / "skills" / "README.md"
    readme.write_text(
        _README.replace(
            "| match | Do alpha |", "| match | Do alpha |\n| [`zeta`](zeta.md) | match | Do zeta |"
        ),
        encoding="utf-8",
    )

    result = run(
        "beta", "--path", str(repo / "src" / "claude" / "skills"), "--docs-section", "Code quality"
    )

    assert result.returncode == 0
    rows = [
        line for line in readme.read_text(encoding="utf-8").splitlines() if line.startswith("| [")
    ]
    assert [row.split("`")[1] for row in rows] == ["alpha", "beta", "zeta"]


def test_mirror_skill_tree_gets_no_docs_page(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    mirror = repo / "src" / "copilot-cli" / "skills"
    mirror.mkdir(parents=True)
    readme = repo / "docs" / "skills" / "README.md"
    before = readme.read_text(encoding="utf-8")

    result = run("my-skill", "--path", str(mirror), "--docs-section", "Code quality")

    assert result.returncode == 0, result.stderr
    assert (mirror / "my-skill" / "SKILL.md").is_file()
    assert not (repo / "docs" / "skills" / "my-skill.md").exists()
    assert readme.read_text(encoding="utf-8") == before


def test_repo_local_skill_tree_still_gets_a_page(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    local = repo / ".claude" / "skills"
    local.mkdir(parents=True)

    result = run("my-skill", "--path", str(local), "--docs-section", "Code quality")

    assert result.returncode == 0, result.stderr
    assert (repo / "docs" / "skills" / "my-skill.md").is_file()


def test_other_repository_skill_folder_still_gets_a_page(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    skills = tmp_path / "team" / "skills"
    skills.mkdir(parents=True)
    (tmp_path / "docs" / "skills").mkdir(parents=True)
    (tmp_path / "docs" / "skills" / "README.md").write_text(_README, encoding="utf-8")

    result = run("my-skill", "--path", str(skills), "--docs-section", "Code quality")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "docs" / "skills" / "my-skill.md").is_file()


def test_consumer_repo_with_mirror_tree_still_gets_a_page(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    skills = tmp_path / "team" / "skills"
    skills.mkdir(parents=True)
    (tmp_path / "docs" / "skills").mkdir(parents=True)
    (tmp_path / "docs" / "skills" / "README.md").write_text(_README, encoding="utf-8")

    result = run("my-skill", "--path", str(skills), "--docs-section", "Code quality")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "docs" / "skills" / "my-skill.md").is_file()


def test_titled_row_counts_as_existing(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    readme = repo / "docs" / "skills" / "README.md"
    readme.write_text(
        _README.replace(
            "| match | Do alpha |",
            '| match | Do alpha |\n| [x](my-skill.md "my skill") | match | Old |',
        ),
        encoding="utf-8",
    )
    before = readme.read_text(encoding="utf-8")

    result = run(
        "my-skill",
        "--path",
        str(repo / "src" / "claude" / "skills"),
        "--docs-section",
        "Code quality",
    )

    assert result.returncode == 0, result.stderr
    assert "README row exists" in result.stdout
    assert readme.read_text(encoding="utf-8") == before


def test_two_column_table_gets_a_two_cell_row(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    readme = repo / "docs" / "skills" / "README.md"
    readme.write_text(
        "# Skills\n\n"
        "## Repository maintenance (this repository only)\n\n"
        "| Skill | Use it to |\n"
        "| --- | --- |\n"
        "| [`alpha`](alpha.md) | Do alpha |\n",
        encoding="utf-8",
    )

    result = run(
        "my-skill",
        "--path",
        str(repo / "src" / "claude" / "skills"),
        "--docs-section",
        "Repository maintenance (this repository only)",
    )

    assert result.returncode == 0, result.stderr
    text = readme.read_text(encoding="utf-8")
    assert "| [`my-skill`](my-skill.md) | TODO: what a reader uses it to do |" in text
    assert "| [`my-skill`](my-skill.md) | TODO | TODO:" not in text


def test_scaffold_frontmatter_passes_the_gp003_checks(tmp_path: Path) -> None:
    """A fresh scaffold carries a top-level SemVer version and a license."""
    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root))
    from scripts.validation.skill_frontmatter import (
        parse_frontmatter,
        validate_license,
        validate_version,
    )

    assert run("my-skill", "--path", str(tmp_path)).returncode == 0
    text = (tmp_path / "my-skill" / "SKILL.md").read_text(encoding="utf-8")
    parsed = parse_frontmatter(text)

    assert parsed.errors == []
    assert validate_version(parsed.typed.get("version")) == []
    assert validate_license(parsed.typed.get("license")) == []
