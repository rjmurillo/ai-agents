"""Frontmatter, grants and prompt surface (``skill_rewrite_skills.py``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.skill_rewrite_helpers import (
    MOVED,
    REF,
    RUNNER,
    SKILL,
    checker,
    commit,
    repo,
    run,
    scenario_doc,
    skill_md,
    write,
)

__all__ = ["repo"]


class TestFrontmatter:
    def test_invalid_shape_value(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, SKILL, skill_md("drivr"))
        commit(repo, "typo")
        code, out = run(repo, capsys)
        assert code == 1
        assert "metadata.shape is 'drivr'; it must be driver or reference" in out

    @pytest.mark.parametrize("shape", ["[driver]", "{a: b}"])
    def test_unhashable_shape_is_a_finding_not_a_crash(
        self, repo: Path, capsys: pytest.CaptureFixture[str], shape: str
    ) -> None:
        write(repo, SKILL, skill_md(shape))
        commit(repo, "list shape")
        code, out = run(repo, capsys)
        assert code == 1
        assert "metadata.shape is" in out
        assert "it must be driver or reference" in out

    def test_invalid_yaml(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, SKILL, "---\nname: [unclosed\n---\n\nBody\n")
        commit(repo, "bad yaml")
        code, out = run(repo, capsys)
        assert code == 1
        assert "frontmatter is not valid YAML" in out

    @pytest.mark.parametrize("fence", ["----", "--- ", "---\t", "-----  "])
    def test_fence_variants_the_shared_parser_accepts_are_read(
        self, repo: Path, capsys: pytest.CaptureFixture[str], fence: str
    ) -> None:
        front = "name: demo\nallowed-tools: Read\nmetadata:\n  shape: driver\n"
        write(repo, SKILL, f"{fence}\n{front}{fence}\n\n# Demo\n\nBody.\n")
        commit(repo, "driver behind a variant fence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "metadata.shape changes from None to driver" in out

    def test_unterminated_frontmatter_is_untagged(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, "---\nname: demo\nmetadata:\n  shape: driver\n\nBody.\n")
        commit(repo, "no closing fence")
        assert run(repo, capsys)[0] == 0

    def test_malformed_yaml_behind_a_variant_fence_errors(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, "----\nname: [unclosed\n----\n\nBody\n")
        commit(repo, "bad yaml")
        code, out = run(repo, capsys)
        assert code == 1
        assert "frontmatter is not valid YAML" in out

    def test_no_frontmatter_is_untagged(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, "# Demo\n\nNo frontmatter.\n")
        commit(repo, "plain")
        assert run(repo, capsys)[0] == 0

    def test_non_utf8_surface(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, REF, b"\xff\xfe bad bytes\n")
        commit(repo, "binary")
        code, out = run(repo, capsys)
        assert code == 1
        assert "prompt surface is not UTF-8" in out

    def test_unknown_evidence_dir(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, "evals/skill-rewrites/ghost/run.json", "{}")
        commit(repo, "ghost")
        code, out = run(repo, capsys)
        assert code == 1
        assert "evals/skill-rewrites/ghost/ names no skill" in out

    def test_unknown_scenario_name_is_ignored(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, "tests/evals/critic-scenarios.json", scenario_doc())
        commit(repo, "agent scenarios")
        code, out = run(repo, capsys)
        assert code == 0
        assert "0 changed skills examined" in out


class TestReferenceGrants:
    @pytest.mark.parametrize(
        "tools",
        [
            "Read, Bash",
            "Read, Bash(*)",
            "Bash(git push:*)",
            "Bash(git -C . push:*)",
            "Bash(git commit:*)",
            "Bash(git:*)",
            "Bash(git branch:*)",
            "Bash(gh:*)",
            "Bash(gh pr create:*)",
            "Bash(python3:*)",
            "Bash(python3.14:*)",
            "Bash(uv:*)",
            "Bash(uv run:*)",
            "Bash(env gh:*)",
            "Bash(python3 -c:*)",
            "Bash(python3:*/skills/github/scripts/*)",
            "Bash(python3 .claude/skills/github/scripts/pr/*)",
            "Bash(python3:*/skills/demo/scripts/* && git push)",
            "Bash(python3:-I */pr/new_pr.py*)",
            "mcp__github__create_pull_request",
            "Bash(python3 .claude/skills/demo/scripts/../../github/scripts/pr/merge_pr.py)",
            "Bash(ls && git push:*)",
            "Bash(ls;git push)",
            "Bash(date | sh)",
            "Bash(ls $(git push))",
            "Bash(git grep:*)",
            "Bash(git diff --output=/tmp/x:*)",
            "Bash(git log --ext-diff:*)",
            "mcp__serena__find_and_replace",
            "Write, Bash(python3:*/skills/demo/scripts/*)",
            "Edit, Bash(git diff:*)",
            "Read, Task",
            "Read, Agent",
            "Bash(mkdir:-p .project-toolkit/scratch)",
            "Read(secrets/*)",
        ],
    )
    def test_reference_skill_may_not_write(
        self, repo: Path, capsys: pytest.CaptureFixture[str], tools: str
    ) -> None:
        write(repo, SKILL, skill_md("reference", body="\n".join(MOVED), tools=tools))
        commit(repo, "tag")
        code, out = run(repo, capsys)
        assert code == 1
        assert "shape is reference but allowed-tools grants" in out

    @pytest.mark.parametrize(
        "tools",
        [
            "Read, Grep, Glob, Skill, Write",
            "Bash(git diff:*), Bash(git merge-base:*), Bash(git branch --show-current)",
            "Bash(python3:*/skills/demo/scripts/*)",
            "Bash(uv run --frozen python -I */skills/demo/scripts/check.py*)",
            "mcp__serena__find_symbol, mcp__github__get_file_contents",
        ],
    )
    def test_read_only_grants_pass(
        self, repo: Path, capsys: pytest.CaptureFixture[str], tools: str
    ) -> None:
        write(repo, SKILL, skill_md("reference", body="\n".join(MOVED), tools=tools))
        commit(repo, "tag")
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_list_form_grants_are_read(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        text = (
            "---\nname: demo\nallowed-tools:\n  - Read\n  - Bash(*)\n"
            "metadata:\n  shape: reference\n---\n\n" + "\n".join(MOVED) + "\n"
        )
        write(repo, SKILL, text)
        commit(repo, "list form")
        code, out = run(repo, capsys)
        assert code == 1
        assert "grants Bash(*)" in out

    def test_non_string_grants_fail_closed(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        text = "---\nname: demo\nallowed-tools: {Bash: yes}\n---\n\nBody\n"
        write(repo, SKILL, text)
        commit(repo, "mapping")
        code, out = run(repo, capsys)
        assert code == 1
        assert "allowed-tools is a dict, not a string or list" in out

    @pytest.mark.parametrize(
        ("tools", "grant"),
        [
            ("*", "*"),
            ("*, Read", "*"),
            ("Read, *", "*"),
            ("Bash(*)", "Bash(*)"),
            ("Read, ??, Grep", "??"),
            ("Read Grep", "Read Grep"),
            ("mcp__github__get_*", "mcp__github__get_*"),
            ("Read, Bash(git diff:*", "Bash(git diff:*"),
            ("Read(secrets), *", "*"),
            ("Read), Grep", "Read)"),
            ("Bash(ls ,Write)", "Bash(ls ,Write)"),
        ],
    )
    def test_unparseable_or_wildcard_grants_are_findings(self, tools: str, grant: str) -> None:
        found = checker.reference_grant_findings("demo", tools)
        assert f"shape is reference but allowed-tools grants {grant}" in found

    def test_quoted_wildcard_in_frontmatter_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, skill_md("reference", body="\n".join(MOVED), tools='"*, Read"'))
        commit(repo, "wildcard")
        code, out = run(repo, capsys)
        assert code == 1
        assert "shape is reference but allowed-tools grants *" in out

    @pytest.mark.parametrize("tools", ["", "Read,", "Read,  , Grep", " Read ,Grep "])
    def test_empty_segments_and_spacing_are_not_findings(self, tools: str) -> None:
        assert checker.reference_grant_findings("demo", tools) == []

    def test_other_skill_script_fails(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        tools = "Bash(python3:*/skills/other/scripts/*)"
        write(repo, SKILL, skill_md("reference", body="\n".join(MOVED), tools=tools))
        commit(repo, "tag")
        assert run(repo, capsys)[0] == 1

    def test_grants_on_driver_are_not_checked_here(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SKILL, skill_md("driver", body="\n".join(MOVED), tools="Bash(*)"))
        commit(repo, "driver")
        assert "shape is reference" not in run(repo, capsys)[1]


def test_surface_matches_runner_loader(repo: Path) -> None:
    """The check hashes the same text the runner feeds the model."""
    write(repo, "src/claude/skills/demo/references/a.md", "First.\r\nCRLF line.\n")
    commit(repo, "refs")
    side = checker.read_skill(checker.Git(repo), "HEAD", "demo")
    assert side.surface == RUNNER.load_prompt_surface_from_file(str(repo / SKILL))
