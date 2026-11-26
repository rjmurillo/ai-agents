"""Frontmatter, grants and prompt surface (``skill_rewrite_skills.py``), and pytest collection."""

from __future__ import annotations

import os
import subprocess
import sys
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

import skill_rewrite_collection as collection

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
        assert not collection.defines_test(source, classes, func)

    def test_unrelated_false_assignments_keep_the_test(self) -> None:
        source = (
            "flag = False\n"
            "other.__test__ = False\n"
            "class TestA:\n    __test__ = True\n    def test_a(self):\n        pass\n"
        )
        assert collection.defines_test(source, ["TestA"], "test_a")


# Full sources pytest does not collect, beyond rebinds of the name itself.
HIDDEN = [
    ("import pytest\n@pytest.fixture\ndef test_t():\n    pass\n", [], "test_t"),
    ("@(lambda f: None)\ndef test_t():\n    pass\n", [], "test_t"),
    ("def drop(f):\n    return None\n@drop\ndef test_t():\n    pass\n", [], "test_t"),
    ("class TestR:\n    @property\n    def test_r(self):\n        pass\n", ["TestR"], "test_r"),
    (
        "from dataclasses import dataclass\n@dataclass\nclass TestR:\n"
        "    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "class Base:\n    __test__ = False\nclass TestR(Base):\n"
        "    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "class Base:\n    def __init__(self):\n        pass\nclass TestR(Base):\n"
        "    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    ("def test_t():\n    pass\nif True:\n    __test__ = False\n", [], "test_t"),
    ("def test_t():\n    pass\n__test__ = ()\n", [], "test_t"),
    ("def test_t():\n    pass\n(__test__ := False)\n", [], "test_t"),
    ("def test_t():\n    pass\n__test__, x = False, 1\n", [], "test_t"),
    (
        "class TestR:\n    def test_r(self):\n        pass\nTestR.test_r.__test__ = False\n",
        ["TestR"],
        "test_r",
    ),
    (
        "class TestR:\n    __init__ = lambda self: None\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "class TestR:\n    if True:\n        def __init__(self):\n"
        "            pass\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "def test_t():\n    pass\nclass Helper:\n    global test_t\n    test_t = None\n",
        [],
        "test_t",
    ),
    (
        "class TestR:\n    def test_r(self):\n        pass\nTestR.test_r = None\n",
        ["TestR"],
        "test_r",
    ),
    ("class TestR:\n    def test_r(self):\n        pass\ndel TestR.test_r\n", ["TestR"], "test_r"),
    (
        "def test_t():\n    pass\ntry:\n    raise ValueError\n"
        "except (test_t := ValueError):\n    pass\n",
        [],
        "test_t",
    ),
    # Import-time code, compile errors and hooks that hide the test.
    (
        "import pytest\npytest.skip('x', allow_module_level=True)\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "import pytest\npytest.importorskip('no_such_module_zz')\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "import pytest\nclass TestR:\n    pytest.skip('x', allow_module_level=True)\n"
        "    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    ("def test_t():\n    pass\nraise RuntimeError('x')\n", [], "test_t"),
    ("def test_t():\n    pass\nreturn\n", [], "test_t"),
    ("def test_t(x, x):\n    pass\n", [], "test_t"),
    ("# coding: nonexistent_zz\ndef test_t():\n    pass\n", [], "test_t"),
    (
        "class TestR:\n    from os import EX_OK as __test__\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "class TestR:\n    match 0:\n        case __test__:\n            pass\n"
        "    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "import pytest\ndef kill(f):\n    return None\n@pytest.mark.foo(kill)\n"
        "def test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "class mark:\n    foo = staticmethod(lambda f: None)\n@mark.foo\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "import pytest\npytest.mark.kill = lambda f: None\n"
        "@pytest.mark.kill\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    ("@mark.foo\ndef test_t():\n    pass\n", [], "test_t"),
    ("import pytest\n@pytest.mark.foo.mark\ndef test_t():\n    pass\n", [], "test_t"),
    ("@pytest.mark.foo\ndef test_t():\n    pass\nimport pytest\n", [], "test_t"),
    ("from pytest import fixture as mark\n@mark.foo\ndef test_t():\n    pass\n", [], "test_t"),
    ("def __getattr__(n):\n    return None\ndef test_t():\n    pass\n", [], "test_t"),
    ("pytest_plugins = ['test_x']\ndef test_t():\n    pass\n", [], "test_t"),
    ("def test_t():\n    yield\n", [], "test_t"),
    ("def test_t():\n    pass\ntest_t.__dict__['__test__'] = False\n", [], "test_t"),
    (
        "import pytest\ndef k(f):\n    return None\nA = [k]\n"
        "@pytest.mark.foo(*A)\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "import pytest\ndef k(f):\n    return None\n"
        "@pytest.mark.foo(k, **{})\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    ("import pytest\npytestmark = 1\ndef test_t():\n    pass\n", [], "test_t"),
    ("pytestmark = 'x'\ndef test_t():\n    pass\n", [], "test_t"),
    ("pytestmark = [1]\ndef test_t():\n    pass\n", [], "test_t"),
    (
        "import pytest\ndef k(f):\n    return None\npytestmark = pytest.mark.foo(k)\n"
        "def test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "class TestR:\n    pytestmark = 1\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    ("def test_t():\n    pass\ntest_t.pytestmark = 1\n", [], "test_t"),
    (
        "import pytest\nif True:\n    pytestmark = 1\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    ("pytestmark = pytest.mark.slow\nimport pytest\ndef test_t():\n    pass\n", [], "test_t"),
]
# Full sources pytest collects, with decorators and switches the checker allows.
COLLECTED = [
    (
        "import pytest\n@pytest.mark.usefixtures('tmp_path')\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "import pytest\n@pytest.mark.skip(reason='later')\n"
        "class TestR:\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    ("import pytest\ndef test_t():\n    pytest.skip('inside the test is fine')\n", [], "test_t"),
    (
        "import pytest\n@pytest.mark.skipif(1 > 2, reason='no')\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    ("import pytest\n@pytest.mark.parametrize('a', [1])\ndef test_t(a):\n    pass\n", [], "test_t"),
    ("from pytest import mark\n@mark.slow\ndef test_t():\n    pass\n", [], "test_t"),
    (
        "import pytest\n@pytest.mark.slow\nclass TestR:\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "other = type('O', (), {})\nother.__test__ = False\n"
        "flag = False\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "class TestR:\n    __test__ = True\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    ("import pytest\npytestmark = pytest.mark.slow\ndef test_t():\n    pass\n", [], "test_t"),
    (
        "import pytest\npytestmark = [pytest.mark.a, pytest.mark.b]\n"
        "class TestR:\n    pytestmark = [pytest.mark.c]\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
]
REBINDS = [
    ("test_t = None", [], "test_t"),
    ("del test_t", [], "test_t"),
    ("from os import path as test_t", [], "test_t"),
    ("test_t: object = None", [], "test_t"),
    ("type test_t = int", [], "test_t"),
    ("for test_t in [None]:\n    pass", [], "test_t"),
    ("with open(__file__) as test_t:\n    pass", [], "test_t"),
    ("(test_t := None)", [], "test_t"),
    ("print(test_t := None)", [], "test_t"),
    ("x = (test_t := None)", [], "test_t"),
    ("if (test_t := None):\n    pass", [], "test_t"),
    ("[test_t := 1 for _ in range(1)]", [], "test_t"),
    ("while (test_t := None):\n    pass", [], "test_t"),
    ("match (test_t := 1):\n    case _:\n        pass", [], "test_t"),
    ("@(test_t := lambda f: f)\ndef helper():\n    pass", [], "test_t"),
    ("def helper(a=(test_t := None)):\n    pass", [], "test_t"),
    ("def helper(*, a=(test_t := None)):\n    pass", [], "test_t"),
    ("class Helper((test_t := object)):\n    pass", [], "test_t"),
    ("@(TestR := lambda c: c)\nclass Helper:\n    pass", ["TestR"], "test_r"),
    ("class Helper(metaclass=(test_t := type)):\n    pass", [], "test_t"),
    ("f = lambda a=(test_t := None): a", [], "test_t"),
    ("from os import *", [], "test_t"),
    ("test_t = staticmethod(test_t)", [], "test_t"),
    ("TestR = None", ["TestR"], "test_r"),
    # A block body runs in module scope, so its bindings count at any depth.
    ("try:\n    test_t = None\nexcept Exception:\n    pass", [], "test_t"),
    ("try:\n    1 / 0\nexcept Exception:\n    test_t = None", [], "test_t"),
    ("try:\n    1 / 0\nexcept Exception as test_t:\n    pass", [], "test_t"),
    ("try:\n    pass\nexcept Exception:\n    pass\nelse:\n    test_t = None", [], "test_t"),
    ("try:\n    pass\nfinally:\n    test_t = None", [], "test_t"),
    ("try:\n    from os import path as test_t\nexcept ImportError:\n    pass", [], "test_t"),
    ("if True:\n    test_t = None", [], "test_t"),
    ("if False:\n    pass\nelif True:\n    test_t = None", [], "test_t"),
    ("if False:\n    pass\nelse:\n    test_t = None", [], "test_t"),
    ("if True:\n    print(test_t := None)", [], "test_t"),
    ("for _ in [1]:\n    test_t = None", [], "test_t"),
    ("for _ in []:\n    pass\nelse:\n    test_t = None", [], "test_t"),
    ("while True:\n    test_t = None\n    break", [], "test_t"),
    ("with open(__file__):\n    test_t = None", [], "test_t"),
    ("match 1:\n    case _:\n        test_t = None", [], "test_t"),
    ("match 1:\n    case test_t:\n        pass", [], "test_t"),
    ("match [1]:\n    case [*test_t]:\n        pass", [], "test_t"),
    ("match {}:\n    case {**test_t}:\n        pass", [], "test_t"),
    ("match 1:\n    case _ if (test_t := None) is None:\n        pass", [], "test_t"),
    (
        "if True:\n    for _ in [1]:\n        match 1:\n            case _:\n"
        "                try:\n                    test_t = None\n"
        "                except Exception:\n                    pass",
        [],
        "test_t",
    ),
    ("try:\n    TestR = None\nexcept Exception:\n    pass", ["TestR"], "test_r"),
]
# pytest collects these, because the rebind leaves a function under the name,
# but the checker cannot prove that statically, so it fails closed.
FAIL_CLOSED = frozenset(
    {
        "@(test_t := lambda f: f)\ndef helper():\n    pass",
        "from os import *",
        "test_t = staticmethod(test_t)",
    }
)
KEPT = [
    "test_t = None\n\ndef test_t():\n    pass\n",
    "from os import *\n\ndef test_t():\n    pass\n",
    "d = {}\nd[test_t] = 1\n",
    "x: test_t\n",
    "f = lambda: (test_t := None)\n",
    "def helper():\n    test_t = None\n",
    "class Helper:\n    test_t = None\n",
    "[test_t for test_t in range(1)]\n",
    "try:\n    x = 1\nexcept Exception:\n    y = 2\n",
    "if True:\n    def helper():\n        test_t = None\n",
]


def _rebound_source(rebind: str) -> str:
    return (
        "def test_t():\n    pass\n\n"
        "class TestR:\n    def test_r(self):\n        pass\n\n"
        f"{rebind}\n"
    )


def _kept_source(other: str) -> str:
    return f"def test_t():\n    pass\n\n{other}"


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
        assert collection.defines_test(_TESTS, classes, func)

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
        assert not collection.defines_test(_TESTS, classes, func)

    @pytest.mark.parametrize(
        "constructor",
        [
            "def __init__(self):\n        pass",
            "def __new__(cls):\n        return super().__new__(cls)",
            "async def __init__(self):\n        pass",
        ],
    )
    def test_class_with_its_own_constructor_is_not_collected(self, constructor: str) -> None:
        source = f"class TestC:\n    {constructor}\n\n    def test_c(self):\n        pass\n"
        assert not collection.defines_test(source, ["TestC"], "test_c")

    def test_constructor_on_an_outer_class_blocks_the_nested_test(self) -> None:
        source = (
            "class TestOuter:\n    def __init__(self):\n        pass\n\n"
            "    class TestInner:\n        def test_i(self):\n            pass\n"
        )
        assert not collection.defines_test(source, ["TestOuter", "TestInner"], "test_i")

    @pytest.mark.parametrize(("rebind", "classes", "func"), REBINDS)
    def test_a_rebound_name_is_not_collected(
        self, rebind: str, classes: list[str], func: str
    ) -> None:
        assert not collection.defines_test(_rebound_source(rebind), classes, func)

    @pytest.mark.parametrize(
        "rebind",
        [
            "    test_r = None",
            "    if True:\n        test_r = None",
            "    try:\n        pass\n    finally:\n        test_r = None",
        ],
    )
    def test_a_method_rebound_in_its_class_is_not_collected(self, rebind: str) -> None:
        source = f"class TestR:\n    def test_r(self):\n        pass\n{rebind}\n"
        assert not collection.defines_test(source, ["TestR"], "test_r")

    @pytest.mark.parametrize(("source", "classes", "func"), HIDDEN)
    def test_a_test_pytest_skips_is_not_collected(
        self, source: str, classes: list[str], func: str
    ) -> None:
        assert not collection.defines_test(source, classes, func)

    @pytest.mark.parametrize(("source", "classes", "func"), COLLECTED)
    def test_a_marked_or_switched_on_test_is_collected(
        self, source: str, classes: list[str], func: str
    ) -> None:
        assert collection.defines_test(source, classes, func)

    @pytest.mark.parametrize("other", KEPT)
    def test_a_def_that_stays_the_final_binding_is_collected(self, other: str) -> None:
        assert collection.defines_test(_kept_source(other), [], "test_t")

    def test_a_def_inside_a_block_fails_closed(self) -> None:
        """pytest collects it, but no static read proves the branch runs."""
        source = "if True:\n    def test_t():\n        pass\n"
        assert not collection.defines_test(source, [], "test_t")

    def test_the_checker_agrees_with_pytest_collection(self, tmp_path: Path) -> None:
        """Every corpus case, against a real ``pytest --collect-only`` run.

        The checker may fail closed, never open. Each fail-closed case is listed
        in FAIL_CLOSED, so a new disagreement in either direction fails here.
        """
        expected: dict[str, bool] = {}
        closed: set[str] = set()
        cases = [(r, _rebound_source(r), c, f) for r, c, f in REBINDS]
        cases += [(o, _kept_source(o), [], "test_t") for o in KEPT]
        cases += [(src, src, c, f) for src, c, f in [*HIDDEN, *COLLECTED]]
        for index, (case, source, classes, func) in enumerate(cases):
            name = f"test_case_{index}.py"
            (tmp_path / name).write_text(source, encoding="utf-8")
            node = "::".join([name, *classes, func])
            expected[node] = collection.defines_test(source, classes, func)
            closed |= {node} if case in FAIL_CLOSED else set()
        (tmp_path / "pytest.ini").write_text(
            "[pytest]\npython_files = test_*.py\n"
            "python_classes = Test*\npython_functions = test_*\n",
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        lines = result.stdout.splitlines()
        collected = {line.split("[")[0] for line in lines if line.startswith("test_case_")}
        actual = {node: node in collected for node in expected}
        assert any(actual.values()), result.stdout + result.stderr
        fail_open = {n for n in expected if expected[n] and not actual[n]}
        fail_closed = {n for n in expected if actual[n] and not expected[n]}
        assert (fail_open, fail_closed) == (set(), closed), result.stdout + result.stderr

    def test_constructor_in_a_sibling_class_does_not_block(self) -> None:
        source = (
            "class TestA:\n    def test_a(self):\n        pass\n\n"
            "class TestB:\n    def __init__(self):\n        pass\n"
        )
        assert collection.defines_test(source, ["TestA"], "test_a")

    def test_unparseable_source_is_not_defined(self) -> None:
        assert not collection.defines_test("def test_x(:\n", [], "test_x")


class TestCollectionRules:
    def test_constants_match_pyproject(self) -> None:
        config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        pytest_config = config["tool"]["pytest"]["ini_options"]
        assert pytest_config["python_files"] == [collection.PYTEST_FILE_GLOB]
        assert pytest_config["python_classes"] == [f"{collection.PYTEST_CLASS_PREFIX}*"]
        assert pytest_config["python_functions"] == [f"{collection.PYTEST_FUNC_PREFIX}*"]
        assert pytest_config["testpaths"] == [collection.PYTEST_ROOT]

    @pytest.mark.parametrize("path", ["tests/test_a.py", "tests/skills/demo/test_demo.py"])
    def test_collected_files(self, path: str) -> None:
        assert collection.is_collected_file(path)

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
        assert not collection.is_collected_file(path)
