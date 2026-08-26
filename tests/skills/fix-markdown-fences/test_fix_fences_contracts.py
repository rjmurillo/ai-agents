#!/usr/bin/env python3
"""Contract tests for the fix-markdown-fences scanner.

Two contracts against things outside this module. `TestVendoredInvocation`
executes the command SKILL.md documents, as shipped, from a consumer working
directory. `TestCommonMarkOracle` checks the list-container model against
`markdown-it-py`, a CommonMark reference implementation.

The detector and repair unit tests live in test_fix_fences.py; these are split
out because they answer to external contracts rather than to this module's own
behavior.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script
from commonmark_fence_cases import CASES as FENCE_CASES
from commonmark_fence_cases import oracle_fence_lines
from markdown_it import MarkdownIt

PROJECT_ROOT = Path(__file__).resolve().parents[3]

mod = import_skill_script(".claude/skills/fix-markdown-fences/scripts/fix_fences.py")
repair_markdown_fences = mod.repair_markdown_fences

_REFERENCE = MarkdownIt("commonmark")


def _has_unclosed_fence(text: str) -> bool:
    """Return True when the reference parser leaves a fence open at EOF.

    Read from the token rather than guessed from the string. A fence token
    spans its opener, its body, and its closing marker when one exists, while
    `content` holds the body alone. So a span that exceeds the opener plus the
    body by at least one line was closed by a marker, and one that does not
    ran to the end of the document. An earlier version of this asked whether
    the text ended in a fence character, which called two genuinely unclosed
    documents balanced.
    """
    for token in _REFERENCE.parse(text):
        if token.type != "fence" or not token.map:
            continue
        span = token.map[1] - token.map[0]
        body = token.content.count("\n")
        if span - 1 - body < 1:
            return True
    return False


class TestVendoredInvocation:
    """The command SKILL.md documents, executed as shipped through a shell.

    The other tests import the canonical module. This one reads the invocation
    line out of the SKILL.md that ships in each plugin root and runs that exact
    string through a POSIX shell, from a directory that is not the repository.
    The shell performs the plugin-root expansion, so a renamed variable, a
    reversed fallback order, or a bare relative path fails here rather than
    passing. Passing an already-resolved path would prove none of that.

    The no-variable case is the negative control: with neither variable set the
    documented form falls back to a bare relative path, which is exactly what
    breaks in a consumer install.
    """

    pytestmark = pytest.mark.skipif(
        sys.platform == "win32",
        reason="the documented invocation is a POSIX shell parameter expansion",
    )

    PLUGIN_REL = "skills/fix-markdown-fences/scripts/fix_fences.py"
    SKILL_REL = "skills/fix-markdown-fences/SKILL.md"
    PLACEHOLDER = "FILE_OR_DIR"
    ROOT_VARS = ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")

    def _documented_command(self, plugin_root: Path) -> str:
        """Return the report invocation from *plugin_root*'s own SKILL.md.

        Read rather than restated so the test tracks the shipped text. Each
        plugin root is checked against its own copy, which also catches a
        mirror whose SKILL.md drifted from the canonical one.
        """
        skill_md = plugin_root / self.SKILL_REL
        for line in skill_md.read_text(encoding="utf-8").splitlines():
            candidate = line.strip()
            if (
                candidate.startswith("python3 ")
                and "PLUGIN_ROOT" in candidate
                and candidate.endswith(self.PLACEHOLDER)
            ):
                return candidate.replace(self.PLACEHOLDER, "doc.md")
        raise AssertionError(f"no plugin-root invocation in {skill_md}")

    def _consumer(self, tmp_path: Path) -> Path:
        workdir = tmp_path / "consumer"
        workdir.mkdir(exist_ok=True)
        (workdir / "doc.md").write_text("```py\nx\n```py\ny\n```\n", encoding="utf-8")
        return workdir

    def _env(self, tmp_path: Path, roots: dict[str, str]) -> dict[str, str]:
        """Both root variables cleared, then *roots* applied.

        `python3` is pinned to the interpreter running the tests through a PATH
        shim, so the documented command text stays byte-identical while the
        subprocess cannot pick up an unrelated interpreter.
        """
        bindir = tmp_path / "bin"
        bindir.mkdir(exist_ok=True)
        shim = bindir / "python3"
        if not shim.exists():
            shim.symlink_to(sys.executable)
        env = {k: v for k, v in os.environ.items() if k not in self.ROOT_VARS}
        env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
        env.update(roots)
        return env

    def _run(self, command: str, tmp_path: Path, **roots: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", "-c", command],
            cwd=self._consumer(tmp_path),
            env=self._env(tmp_path, roots),
            capture_output=True,
            text=True,
            timeout=60,
        )

    @staticmethod
    def _unresolved(result: subprocess.CompletedProcess[str]) -> bool:
        return "can't open file" in result.stderr or "No such file" in result.stderr

    @pytest.mark.parametrize(
        ("root_var", "tree"),
        [
            ("CLAUDE_PLUGIN_ROOT", ".claude"),
            ("COPILOT_PLUGIN_ROOT", "src/copilot-cli"),
        ],
    )
    def test_documented_form_runs_from_a_foreign_cwd(
        self, tmp_path: Path, root_var: str, tree: str
    ) -> None:
        plugin_root = PROJECT_ROOT / tree
        assert (plugin_root / self.PLUGIN_REL).is_file(), f"missing: {plugin_root}"
        result = self._run(
            self._documented_command(plugin_root), tmp_path, **{root_var: str(plugin_root)}
        )
        assert result.returncode == 1, result.stderr
        assert "malformed_closing" in result.stdout

    def test_copilot_root_wins_when_both_are_set(self, tmp_path: Path) -> None:
        plugin_root = PROJECT_ROOT / "src/copilot-cli"
        result = self._run(
            self._documented_command(plugin_root),
            tmp_path,
            COPILOT_PLUGIN_ROOT=str(plugin_root),
            CLAUDE_PLUGIN_ROOT=str(tmp_path / "absent"),
        )
        assert result.returncode == 1, result.stderr
        assert "malformed_closing" in result.stdout

    def test_claude_root_does_not_override_copilot_root(self, tmp_path: Path) -> None:
        claude_root = PROJECT_ROOT / ".claude"
        result = self._run(
            self._documented_command(claude_root),
            tmp_path,
            COPILOT_PLUGIN_ROOT=str(tmp_path / "absent"),
            CLAUDE_PLUGIN_ROOT=str(claude_root),
        )
        assert result.returncode != 1
        assert self._unresolved(result), result.stderr

    def test_bare_relative_fallback_fails_from_a_foreign_cwd(self, tmp_path: Path) -> None:
        # Negative control. With neither variable set the documented form
        # expands to the bare relative path it replaced, which cannot resolve
        # from a consumer's working directory.
        result = self._run(self._documented_command(PROJECT_ROOT / ".claude"), tmp_path)
        assert result.returncode != 0
        assert self._unresolved(result), result.stderr


class TestCommonMarkOracle:
    """Fence tracking matches `markdown-it-py` on every list-container case.

    A repair tool that misplaces a list item's content column can append a
    closing fence into literal indented code, so the container model is checked
    against a reference implementation rather than against expectations.
    """

    @staticmethod
    def _inside_fence(text: str) -> set[int]:
        """Return 0-indexed non-blank lines the scanner treats as fenced.

        This mirrors the loop in `fix_fences.find_fence_defects`, including its
        container-close branch:

            if open_fence is not None and _container_closed(line.text, fence_base):
                open_fence = None  # the item holding the block ended

        A hand-written mirror can drift from what it mirrors, which is the
        whole reason this comment names the branch. `test_repair_is_a_no_op_on
        _balanced_documents` guards the direction that matters by driving the
        public repair path instead.
        """
        lines = mod._split_lines(text)
        containers = mod._ListContainers()
        open_fence = None
        fence_base = 0
        inside: set[int] = set()
        for index, line in enumerate(lines):
            if open_fence is not None and mod._container_closed(line.text, fence_base):
                open_fence = None  # the item holding the block ended
            if open_fence is None:
                open_fence = mod._scan_open(line.text, containers)
                fence_base = containers.base() if open_fence is not None else 0
                if open_fence is not None and line.text != "":
                    inside.add(index)
                continue
            if line.text != "":
                inside.add(index)
            match = mod._closes(line.text, open_fence, containers)
            if match is not None and not match.group("info").strip():
                open_fence = None
        return inside

    @pytest.mark.parametrize("name", sorted(FENCE_CASES))
    def test_fenced_lines_match_the_reference_parser(self, name: str) -> None:
        text = FENCE_CASES[name]
        assert self._inside_fence(text) == oracle_fence_lines(text), name

    @pytest.mark.parametrize("name", sorted(FENCE_CASES))
    def test_repair_is_idempotent_on_every_case(self, name: str) -> None:
        once = repair_markdown_fences(FENCE_CASES[name])
        assert repair_markdown_fences(once) == once, name

    @pytest.mark.parametrize("name", sorted(FENCE_CASES))
    def test_repair_is_a_no_op_on_balanced_documents(self, name: str) -> None:
        # Public path, no mirrored state machine. Where the reference parser
        # reads every fence as closed, `--write` must change nothing. This is
        # the assertion that would catch `_inside_fence` drifting from the
        # loops it mirrors, and it is how three separate corruption paths were
        # found: a fence on a marker line, a block outliving its list item, and
        # five-column padding before a marker-line fence.
        text = FENCE_CASES[name]
        if _has_unclosed_fence(text):
            pytest.skip("document is genuinely unclosed; repair should act")
        assert repair_markdown_fences(text) == text, name

    def test_write_never_invents_a_fence_in_indented_code(self) -> None:
        # Rules 1 and 2: a marker that is itself indented code, or padding of
        # five or more columns, both used to move the content column and let
        # the repair append a closing fence into literal code.
        for name in ("marker over indented is code", "padding of five columns"):
            text = FENCE_CASES[name]
            assert oracle_fence_lines(text) == set(), name
            assert repair_markdown_fences(text) == text, name
