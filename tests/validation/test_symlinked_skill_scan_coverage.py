"""Gates that scan skills must reach shipped skill files through src/claude/skills.

ADR-119 made each shipped ``.claude/skills/<name>`` a directory link into
``src/claude/skills/<name>``. ``Path.rglob``, ``glob("**")`` and ``os.walk`` do
not descend into a linked directory, and ``git ls-files`` lists one link entry
per shipped skill. A gate that still names only ``.claude/skills`` therefore
examines the repo-local skills and passes. These tests pin that each gate
examines a non-zero number of shipped files, measured on the real repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import canonical_citations_count_ratchet as citation_ratchet
from scripts.ci import subprocess_encoding_count_ratchet as encoding_ratchet
from scripts.validation import (
    agent_skill_discriminator_baseline as discriminator_baseline,
)
from scripts.validation import (
    check_agent_skill_discriminator as discriminator,
)
from scripts.validation import (
    check_canonical_citations,
    check_colocated_skill_tests,
    check_external_contracts,
    check_skill_contract_tests,
    check_skill_md_portability,
    check_skill_resolver_anchoring,
    check_vendor_portability,
    skill_frontmatter,
    validate_skill_shells,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED = "src/claude/skills/"


def _shipped(paths: list[Path]) -> list[Path]:
    return [p for p in paths if p.relative_to(REPO_ROOT).as_posix().startswith(SHIPPED)]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _repo_with_linked_skill(tmp_path: Path, script_body: str) -> Path:
    """Build a repo whose only shipped skill is a directory link into src/claude/skills."""
    scripts = tmp_path / "src" / "claude" / "skills" / "demo" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run.py").write_text(script_body, encoding="utf-8")
    (scripts.parent / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    skills = tmp_path / ".claude" / "skills"
    skills.mkdir(parents=True)
    (skills / "demo").symlink_to(Path("..") / ".." / "src" / "claude" / "skills" / "demo")
    return tmp_path


def test_real_repo_link_is_not_followed_by_rglob() -> None:
    """The premise: a recursive walk of .claude/skills misses shipped files."""
    linked = REPO_ROOT / ".claude" / "skills" / "github"
    assert linked.is_symlink(), "expected a shipped skill to be a directory link"
    walked = {
        p.relative_to(REPO_ROOT).as_posix()
        for p in (REPO_ROOT / ".claude" / "skills").rglob("SKILL.md")
    }
    assert ".claude/skills/github/SKILL.md" not in walked


def test_vendor_portability_examines_shipped_scripts() -> None:
    examined = check_vendor_portability.iter_scanned_files(REPO_ROOT)
    assert len(_shipped(examined)) > 0


def test_vendor_portability_scans_a_linked_skill_once(tmp_path: Path) -> None:
    body = 'PATH_TO_OPEN = ".agents/sessions/log.json"\nopen(PATH_TO_OPEN)\n'
    repo = _repo_with_linked_skill(tmp_path, body)

    offenders = check_vendor_portability.collect_offenders(repo)

    assert [o.relpath for o in offenders] == ["src/claude/skills/demo/scripts/run.py"]


def test_canonical_citations_examines_shipped_scripts() -> None:
    roots = check_canonical_citations._scan_roots(REPO_ROOT)
    files = list(check_canonical_citations._iter_python_files(roots))
    assert len(_shipped(files)) > 0


def test_canonical_citations_ratchet_counts_shipped_prefix() -> None:
    assert citation_ratchet._in_scan_roots("src/claude/skills/github/scripts/pr/get_pr_context.py")


def test_external_contracts_examines_shipped_files() -> None:
    assert len(_shipped(check_external_contracts.scanned_files(REPO_ROOT))) > 0


def test_external_contracts_skips_rendered_skill_md_under_src() -> None:
    assert not check_external_contracts._scannable(Path("src/claude/skills/demo/SKILL.md"))
    assert check_external_contracts._scannable(Path("src/claude/skills/demo/references/a.md"))


def test_skill_contract_tests_cli_examines_shipped_skills(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = check_skill_contract_tests.main(["--repo-root", str(REPO_ROOT)])
    out = capsys.readouterr().out
    examined = int(out.split(" of ")[1].split(" examined")[0])
    assert rc == 0
    assert examined > 100


def test_resolver_anchoring_examines_shipped_skill_md() -> None:
    assert len(_shipped(check_skill_resolver_anchoring.iter_skill_files(REPO_ROOT))) > 0


def test_skill_frontmatter_corpus_includes_shipped_skills() -> None:
    assert len(_shipped(skill_frontmatter.default_corpus_files())) > 0


def test_skill_frontmatter_pattern_matches_shipped_path() -> None:
    assert skill_frontmatter._SKILL_FILE_PATTERN.search("src/claude/skills/github/SKILL.md")


def test_discriminator_pipeline_index_reads_shipped_skills() -> None:
    assert ("src/claude/skills", "SKILL.md") in discriminator_baseline.PIPELINE_SOURCES
    index = discriminator.build_pipeline_index(REPO_ROOT)
    assert any(key.startswith(SHIPPED) for key in index.agents_by_file)


def test_skill_shells_examines_shipped_skill_dirs() -> None:
    assert "src/claude/skills" in validate_skill_shells.SKILLS_ROOTS
    assert validate_skill_shells.count_skill_dirs(REPO_ROOT) > 100


def test_skill_shells_reports_a_shipped_shell(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    shell = tmp_path / "src" / "claude" / "skills" / "ghost"
    shell.mkdir(parents=True)
    (shell / "notes.md").write_text("orphaned\n", encoding="utf-8")
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    _git(tmp_path, "add", "-A")

    assert validate_skill_shells.find_skill_shells(tmp_path) == ["src/claude/skills/ghost"]


def test_subprocess_ratchet_maps_platform_mirrors_to_the_shipped_tree() -> None:
    source = encoding_ratchet._skill_mirror_canonical_source
    assert source("src/copilot-cli/skills/a/scripts/b.py") == "src/claude/skills/a/scripts/b.py"
    assert source(".claude/skills/a/scripts/b.py") == "src/claude/skills/a/scripts/b.py"
    assert source("src/claude/skills/a/scripts/b.py") is None


def test_colocated_tests_treat_other_shipped_trees_as_legacy_twins() -> None:
    twins = check_colocated_skill_tests._legacy_equivalent_paths(
        "src/copilot-cli/skills/a/tests/test_x.py"
    )
    assert "src/claude/skills/a/tests/test_x.py" in twins
    assert ".claude/skills/a/tests/test_x.py" in twins
    assert "src/copilot-cli/skills/a/tests/test_x.py" not in twins


def test_skill_md_portability_does_not_treat_the_shipped_tree_as_a_mirror() -> None:
    assert check_skill_md_portability._skill_mirror_source("src/claude/skills/a/SKILL.md") is None
    assert (
        check_skill_md_portability._skill_mirror_source("src/copilot-cli/skills/a/SKILL.md")
        == "src/claude/skills/a/SKILL.md"
    )
