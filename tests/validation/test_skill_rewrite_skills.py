"""Frontmatter, grant allowlist, and prompt surface in ``skill_rewrite_skills.py``."""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib

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

import skill_rewrite_skills as skills

_REPO_ROOT = Path(__file__).resolve().parents[2]


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


_TESTS = """
def test_top():
    pass


def make_thing():
    pass


class Helpers:
    def test_h(self):
        pass


class TestA:
    def test_a(self):
        pass

    def helper(self):
        pass

    async def test_async(self):
        pass

    class TestInner:
        def test_inner(self):
            pass


class TestB:
    def test_b(self):
        pass
"""


class TestCollectionSwitchedOff:
    """``__test__ = False`` makes pytest skip a module, class, or function."""

    @pytest.mark.parametrize(
        ("source", "classes", "func"),
        [
            ("__test__ = False\ndef test_a():\n    pass\n", [], "test_a"),
            ("def test_a():\n    pass\ntest_a.__test__ = False\n", [], "test_a"),
            (
                "class TestA:\n    __test__ = False\n    def test_a(self):\n        pass\n",
                ["TestA"],
                "test_a",
            ),
            (
                "class TestA:\n    def test_a(self):\n        pass\nTestA.__test__ = False\n",
                ["TestA"],
                "test_a",
            ),
            (
                "class TestA:\n    __test__: bool = False\n    def test_a(self):\n        pass\n",
                ["TestA"],
                "test_a",
            ),
            ("__test__ = 0\ndef test_a():\n    pass\n", [], "test_a"),
            ("__test__ = None\ndef test_a():\n    pass\n", [], "test_a"),
        ],
    )
    def test_switched_off_tests_are_not_defined(
        self, source: str, classes: list[str], func: str
    ) -> None:
        assert not skills.defines_test(source, classes, func)

    def test_unrelated_false_assignments_keep_the_test(self) -> None:
        source = (
            "flag = False\n"
            "other.__test__ = False\n"
            "class TestA:\n    __test__ = True\n    def test_a(self):\n        pass\n"
        )
        assert skills.defines_test(source, ["TestA"], "test_a")


class TestDefinesTest:
    @pytest.mark.parametrize(
        ("classes", "func"),
        [
            ([], "test_top"),
            (["TestA"], "test_a"),
            (["TestA"], "test_async"),
            (["TestA", "TestInner"], "test_inner"),
        ],
    )
    def test_defined_in_the_named_chain(self, classes: list[str], func: str) -> None:
        assert skills.defines_test(_TESTS, classes, func)

    @pytest.mark.parametrize(
        ("classes", "func"),
        [
            (["TestB"], "test_a"),
            ([], "test_a"),
            (["TestInner"], "test_inner"),
            (["TestInner", "TestA"], "test_inner"),
            (["TestA"], "test_top"),
            ([""], "test_a"),
            (["TestA"], ""),
            (["TestNope"], "test_a"),
            (["TestB"], "test_b[case-1]"),
            ([], "test_top[x]"),
            ([], "make_thing"),
            (["TestA"], "helper"),
            (["Helpers"], "test_h"),
        ],
    )
    def test_not_defined_in_the_named_chain(self, classes: list[str], func: str) -> None:
        assert not skills.defines_test(_TESTS, classes, func)

    def test_unparseable_source_is_not_defined(self) -> None:
        assert not skills.defines_test("def test_x(:\n", [], "test_x")


class TestCollectionRules:
    def test_constants_match_pyproject(self) -> None:
        config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        pytest_config = config["tool"]["pytest"]["ini_options"]
        assert pytest_config["python_files"] == [skills.PYTEST_FILE_GLOB]
        assert pytest_config["python_classes"] == [f"{skills.PYTEST_CLASS_PREFIX}*"]
        assert pytest_config["python_functions"] == [f"{skills.PYTEST_FUNC_PREFIX}*"]
        assert pytest_config["testpaths"] == [skills.PYTEST_ROOT]

    @pytest.mark.parametrize("path", ["tests/test_a.py", "tests/skills/demo/test_demo.py"])
    def test_collected_files(self, path: str) -> None:
        assert skills.is_collected_file(path)

    @pytest.mark.parametrize(
        "path",
        [
            "tests/helpers.py",
            "tests/conftest.py",
            "tests/skills/demo/demo_test.py",
            "tests/test_demo.txt",
            "scripts/test_demo.py",
            "test_demo.py",
            "tests/../scripts/test_demo.py",
            "tests",
            "",
        ],
    )
    def test_files_pytest_does_not_collect(self, path: str) -> None:
        assert not skills.is_collected_file(path)
