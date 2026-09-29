"""Canonical versus generated classification for the byte report (issue #5400)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.instruction_bytes_corpus import (
    CorpusError,
    canonical_files,
    generated_files,
    group_summary,
    measure_corpus,
    read_sized,
)
from tests.validation._instruction_bytes_helpers import build_repo, write


class TestReadSized:
    def test_counts_utf8_bytes_not_characters(self, tmp_path: Path) -> None:
        expected = write(tmp_path, "a.md", "café → ok\n")
        sized = read_sized(tmp_path, "a.md")
        assert sized.size_bytes == expected
        assert sized.size_bytes > len("café → ok\n")
        assert sized.estimated_tokens > 0

    def test_invalid_utf8_is_counted_as_its_raw_bytes(self, tmp_path: Path) -> None:
        (tmp_path / "raw.md").write_bytes(b"ok \xff\xfe bad\n")
        assert read_sized(tmp_path, "raw.md").size_bytes == 10

    def test_empty_file_is_zero_bytes_and_zero_tokens(self, tmp_path: Path) -> None:
        write(tmp_path, "empty.md", "")
        sized = read_sized(tmp_path, "empty.md")
        assert (sized.size_bytes, sized.estimated_tokens) == (0, 0)

    def test_missing_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(CorpusError, match="not a file"):
            read_sized(tmp_path, "nope.md")

    def test_directory_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "dir.md").mkdir()
        with pytest.raises(CorpusError, match="not a file"):
            read_sized(tmp_path, "dir.md")

    def test_symlink_escaping_the_root_is_refused(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.md"
        outside.write_text("secret\n", encoding="utf-8")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "link.md").symlink_to(outside)
        with pytest.raises(CorpusError, match="outside the repository"):
            read_sized(repo, "link.md")

    def test_traversal_segment_is_refused(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        write(tmp_path, "outside.md", "x\n")
        with pytest.raises(CorpusError, match="outside the repository"):
            read_sized(repo, "../outside.md")


class TestCanonicalFiles:
    def test_groups_hold_every_authored_class(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        groups = canonical_files(tmp_path)
        assert set(groups) == {"skills", "agents", "rules", "governance", "root"}
        assert [f.path for f in groups["root"]] == ["AGENTS.md", "CLAUDE.md"]
        assert len(groups["skills"]) == 4
        assert len(groups["agents"]) == 1

    def test_per_harness_agent_templates_and_partials_are_authored_and_counted(
        self, tmp_path: Path
    ) -> None:
        build_repo(tmp_path)
        write(tmp_path, "templates/agents/scout.claude.md.tmpl", "x" * 500)
        write(tmp_path, "templates/agents/partials/shared.mustache", "y" * 100)
        write(tmp_path, "templates/skills/partials/skill.mustache", "z" * 100)
        groups = canonical_files(tmp_path)
        assert [f.path for f in groups["agents"]] == [
            "templates/agents/partials/shared.mustache",
            "templates/agents/scout.claude.md.tmpl",
            "templates/agents/scout.shared.md",
        ]
        assert "templates/skills/partials/skill.mustache" in [f.path for f in groups["skills"]]

    def test_a_directory_under_templates_is_not_counted_as_a_file(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        (tmp_path / "templates/agents/empty-dir").mkdir()
        assert all(f.size_bytes >= 0 for f in canonical_files(tmp_path)["agents"])
        assert "templates/agents/empty-dir" not in [
            f.path for f in canonical_files(tmp_path)["agents"]
        ]

    def test_hook_and_platform_config_is_not_instruction_text(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, "templates/hooks/Stop/hook.json", "{}" * 100)
        write(tmp_path, "templates/toolsets.yaml", "a: 1\n")
        paths = [f.path for files in canonical_files(tmp_path).values() for f in files]
        assert not any(
            p.startswith("templates/hooks") or p.endswith("toolsets.yaml") for p in paths
        )

    def test_generated_mirrors_never_enter_canonical(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        before = group_summary(canonical_files(tmp_path))["total"]
        write(tmp_path, "src/copilot-cli/skills/huge/SKILL.md", "x" * 100_000)
        after = group_summary(canonical_files(tmp_path))["total"]
        assert after == before

    @pytest.mark.parametrize(
        "missing",
        ["templates/skills", "templates/agents", "templates/rules", ".agents/governance"],
    )
    def test_an_empty_group_fails_closed(self, tmp_path: Path, missing: str) -> None:
        build_repo(tmp_path)
        for path in sorted((tmp_path / missing).glob("*")):
            path.unlink()
        with pytest.raises(CorpusError, match="holds no files"):
            canonical_files(tmp_path)

    def test_a_missing_root_guide_fails_closed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        (tmp_path / "AGENTS.md").unlink()
        (tmp_path / "CLAUDE.md").unlink()
        with pytest.raises(CorpusError, match="`root`"):
            canonical_files(tmp_path)


class TestGeneratedFiles:
    def test_copilot_cli_is_its_own_family(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        families = generated_files(tmp_path)
        assert "src/copilot-cli" in families
        assert ".claude" in families
        assert ".github" in families
        assert [f.path for f in families["src/copilot-cli"]] == [
            "src/copilot-cli/skills/alpha/SKILL.md"
        ]

    def test_missing_projection_trees_count_as_zero(self, tmp_path: Path) -> None:
        assert generated_files(tmp_path) == {}

    def test_families_are_sorted_for_stable_output(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        families = list(generated_files(tmp_path))
        assert families == sorted(families)

    def test_a_file_matched_by_two_globs_counts_once(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        paths = [f.path for files in generated_files(tmp_path).values() for f in files]
        assert len(paths) == len(set(paths))


class TestMeasureCorpus:
    def test_returns_canonical_and_generated(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        canonical, generated = measure_corpus(tmp_path)
        assert "skills" in canonical
        assert "src/copilot-cli" in generated

    def test_group_summary_total_is_the_sum_of_groups(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        summary = group_summary(canonical_files(tmp_path))
        groups = summary["groups"]
        assert isinstance(groups, dict)
        total = summary["total"]
        assert isinstance(total, dict)
        assert total["bytes"] == sum(g["bytes"] for g in groups.values())
        assert total["files"] == sum(g["files"] for g in groups.values())
