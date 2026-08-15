"""Tests for ``scripts/validation/check_skill_memory_references.py``.

The gate exists because of issue #4897: pr-comment-responder's BLOCKING
Phase 0 ran ``read_memory(memory_file_name="pr-comment-responder-skills")``
while the memory was tracked at
``.serena/memories/pr-review/pr-comment-responder-skills.md``. The name did
not resolve, the blocking phase failed for any agent that followed the
instruction literally, and nothing in the repository could observe it.

Every behavioral test drives ``main(argv)`` and asserts the integer it
returns, per ``.claude/rules/testing.md`` MUST 8. Asserting that
``collect_findings`` returned a non-empty list would prove detection and say
nothing about whether the program fails, which is the silent-pass shape this
repository has hit six times (Issue #4068).

Coverage:

- positive: a scoped name resolves and the run exits 0.
- negative: the #4897 shape (unscoped name, memory present under a scope)
  exits 1 and the report names the scoped replacement; a name that resolves
  nowhere exits 1 with the no-such-basename message.
- edge: placeholder names, ``write_memory``, absent memories root, absent
  corpus, a non-directory repo root, path traversal, symlinked components,
  backslash names, multi-line calls, and the ``memory_name`` alias.
- corpus: the shipped tree passes, which is the claim ``.claude/rules/
  ci-scripts.md`` MUST 13 requires a gate-introducing PR to demonstrate.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "validation" / "check_skill_memory_references.py"
)


def _load_module():
    """Load the script as a module under a stable name."""
    spec = importlib.util.spec_from_file_location(
        "check_skill_memory_references",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


csmr = _load_module()


# --- Fixture helpers -------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _make_repo(
    tmp_path: Path,
    memories: tuple[str, ...] = (),
    instructions: tuple[tuple[str, str], ...] = (),
) -> Path:
    """Build a repo root holding the given memories and instruction files.

    ``memories`` are memory names (no ``.md``); ``instructions`` are
    ``(relative path, content)`` pairs written verbatim.
    """
    memories_root = tmp_path / ".serena" / "memories"
    memories_root.mkdir(parents=True, exist_ok=True)
    for name in memories:
        _write(memories_root / f"{name}.md", f"# {name}\n")
    for relative, content in instructions:
        _write(tmp_path / relative, content)
    return tmp_path


def _run(repo_root: Path) -> int:
    return csmr.main(["--repo-root", str(repo_root)])


_SKILL = ".claude/skills/example/SKILL.md"
_AGENT = "templates/agents/example.shared.md"


def _call(name: str, operation: str = "read_memory") -> str:
    return (
        "```python\n"
        f'mcp__serena__{operation}(memory_file_name="{name}")\n'
        "```\n"
    )


# --- Positive --------------------------------------------------------------


class TestResolvingReferences:
    def test_a_scoped_name_that_resolves_exits_zero(self, tmp_path: Path) -> None:
        repo = _make_repo(
            tmp_path,
            memories=("pr-review/pr-comment-responder-skills",),
            instructions=(
                (_SKILL, _call("pr-review/pr-comment-responder-skills")),
            ),
        )
        assert _run(repo) == csmr.EXIT_OK

    def test_a_top_level_name_that_resolves_exits_zero(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(
            tmp_path,
            memories=("usage-mandatory",),
            instructions=((_SKILL, _call("usage-mandatory")),),
        )
        assert _run(repo) == csmr.EXIT_OK

    def test_the_pass_line_reports_what_was_examined(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """MUST 12: a clean run must be distinguishable from an idle one."""
        repo = _make_repo(
            tmp_path,
            memories=("usage-mandatory",),
            instructions=((_SKILL, _call("usage-mandatory")),),
        )
        assert _run(repo) == csmr.EXIT_OK
        out = capsys.readouterr().out
        assert "[PASS]" in out
        assert "1 literal memory read(s)" in out
        assert "1 instruction file(s)" in out


# --- Negative --------------------------------------------------------------


class TestUnresolvedReferences:
    def test_the_issue_4897_shape_exits_one(self, tmp_path: Path) -> None:
        """Unscoped name, memory present under exactly one scope."""
        repo = _make_repo(
            tmp_path,
            memories=("pr-review/pr-comment-responder-skills",),
            instructions=((_SKILL, _call("pr-comment-responder-skills")),),
        )
        assert _run(repo) == csmr.EXIT_UNRESOLVED

    def test_the_report_names_the_scoped_replacement(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(
            tmp_path,
            memories=("pr-review/pr-comment-responder-skills",),
            instructions=((_SKILL, _call("pr-comment-responder-skills")),),
        )
        assert _run(repo) == csmr.EXIT_UNRESOLVED
        out = capsys.readouterr().out
        assert "'pr-review/pr-comment-responder-skills'" in out
        assert f"{_SKILL}:2" in out

    def test_a_name_that_resolves_nowhere_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(
            tmp_path,
            memories=("pr-review/other",),
            instructions=((_SKILL, _call("no-such-memory")),),
        )
        assert _run(repo) == csmr.EXIT_UNRESOLVED
        assert "no tracked memory shares that basename" in capsys.readouterr().out

    def test_every_scope_holding_the_basename_is_listed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(
            tmp_path,
            memories=("pr-review/observations", "github/observations"),
            instructions=((_SKILL, _call("observations")),),
        )
        assert _run(repo) == csmr.EXIT_UNRESOLVED
        out = capsys.readouterr().out
        assert "'github/observations'" in out
        assert "'pr-review/observations'" in out

    def test_edit_memory_is_checked_like_read_memory(
        self, tmp_path: Path
    ) -> None:
        """edit_memory mutates an existing memory, so its target must exist."""
        repo = _make_repo(
            tmp_path,
            memories=("pr-review/pr-comment-responder-skills",),
            instructions=(
                (
                    _SKILL,
                    _call("pr-comment-responder-skills", "edit_memory"),
                ),
            ),
        )
        assert _run(repo) == csmr.EXIT_UNRESOLVED

    def test_an_agent_surface_is_checked_too(self, tmp_path: Path) -> None:
        """51 of the 53 references repaired for #4897 lived in agent copies."""
        repo = _make_repo(
            tmp_path,
            memories=("pr-review/pr-comment-responder-skills",),
            instructions=((_AGENT, _call("pr-comment-responder-skills")),),
        )
        assert _run(repo) == csmr.EXIT_UNRESOLVED

    def test_one_bad_reference_fails_a_file_holding_good_ones(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(
            tmp_path,
            memories=("pr-review/good", "pr-review/also-good"),
            instructions=(
                (
                    _SKILL,
                    _call("pr-review/good")
                    + _call("bad")
                    + _call("pr-review/also-good"),
                ),
            ),
        )
        assert _run(repo) == csmr.EXIT_UNRESOLVED


# --- Reference detection edges --------------------------------------------


class TestReferenceDetection:
    @pytest.mark.parametrize(
        "call_text",
        [
            'read_memory(memory_file_name="target")',
            'mcp__serena__read_memory(memory_file_name="target")',
            "mcp__serena__read_memory(memory_file_name='target')",
            'mcp__serena__read_memory(memory_name="target")',
            'current = mcp__serena__read_memory(memory_file_name="target")',
            (
                "mcp__serena__edit_memory(\n"
                '    memory_file_name="target",\n'
                '    needle="x",\n'
                '    repl="y",\n'
                ")"
            ),
        ],
    )
    def test_each_call_spelling_is_detected(
        self, tmp_path: Path, call_text: str
    ) -> None:
        repo = _make_repo(
            tmp_path,
            memories=("scope/target",),
            instructions=((_SKILL, f"```python\n{call_text}\n```\n"),),
        )
        assert _run(repo) == csmr.EXIT_UNRESOLVED

    @pytest.mark.parametrize(
        "name",
        ["<memory-name>", "${MEMORY}", "{name}", "testing/foo[0]", "prefix*"],
    )
    def test_a_placeholder_name_is_not_a_literal(
        self, tmp_path: Path, name: str
    ) -> None:
        repo = _make_repo(
            tmp_path,
            instructions=((_SKILL, _call(name)),),
        )
        assert _run(repo) == csmr.EXIT_OK

    def test_write_memory_is_a_creation_target_not_a_reference(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(
            tmp_path,
            instructions=((_SKILL, _call("brand-new-memory", "write_memory")),),
        )
        assert _run(repo) == csmr.EXIT_OK

    def test_a_call_with_no_literal_name_is_skipped(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(
            tmp_path,
            instructions=(
                (
                    _SKILL,
                    "```python\nmcp__serena__read_memory(memory_file_name=name)\n```\n",
                ),
            ),
        )
        assert _run(repo) == csmr.EXIT_OK

    def test_a_backslash_in_a_name_normalizes_to_a_forward_slash(
        self, tmp_path: Path
    ) -> None:
        """Mirrors ``memory_index.py``: ``file_name.replace("\\\\", "/")``."""
        repo = _make_repo(
            tmp_path,
            memories=("pr-review/target",),
            instructions=((_SKILL, _call("pr-review\\target")),),
        )
        assert _run(repo) == csmr.EXIT_OK

    def test_a_reference_outside_a_corpus_root_is_ignored(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(
            tmp_path,
            instructions=(("docs/notes.md", _call("no-such-memory")),),
        )
        assert _run(repo) == csmr.EXIT_OK


# --- Containment -----------------------------------------------------------


class TestContainment:
    def test_a_traversing_name_does_not_resolve(self, tmp_path: Path) -> None:
        """Mirrors canonical's ``is_relative_to(resolved_memory)`` guard.

        The target file is made to exist outside the memories root, so
        nonexistence cannot be what fails the reference. Only the containment
        check can, and removing it turns this test green.
        """
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.md").write_text("# secret\n", encoding="utf-8")
        repo = _make_repo(
            tmp_path / "repo",
            instructions=((_SKILL, _call("../../../outside/secret")),),
        )
        assert (
            repo / ".serena" / "memories" / "../../../outside/secret.md"
        ).resolve() == (outside / "secret.md").resolve()
        assert _run(repo) == csmr.EXIT_UNRESOLVED

    def test_a_symlinked_component_does_not_resolve(
        self, tmp_path: Path
    ) -> None:
        """Mirrors canonical's per-component ``is_symlink`` refusal."""
        repo = _make_repo(
            tmp_path,
            memories=("real/target",),
            instructions=((_SKILL, _call("alias/target")),),
        )
        memories_root = repo / ".serena" / "memories"
        try:
            (memories_root / "alias").symlink_to(
                memories_root / "real", target_is_directory=True
            )
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation unavailable on this platform")
        assert _run(repo) == csmr.EXIT_UNRESOLVED


# --- Absent inputs and configuration ---------------------------------------


class TestAbsentInputs:
    def test_an_absent_memories_root_skips_with_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A vendored install ships instructions without the memory tree."""
        _write(tmp_path / _SKILL, _call("anything"))
        assert _run(tmp_path) == csmr.EXIT_OK
        assert "[SKIP]" in capsys.readouterr().out

    def test_an_absent_corpus_skips_with_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(tmp_path, memories=("pr-review/target",))
        assert _run(repo) == csmr.EXIT_OK
        out = capsys.readouterr().out
        assert "[SKIP]" in out
        assert "0 memory references examined" in out

    def test_a_missing_repo_root_is_a_configuration_error(
        self, tmp_path: Path
    ) -> None:
        assert _run(tmp_path / "does-not-exist") == csmr.EXIT_CONFIG

    def test_an_unreadable_instruction_file_fails_closed(
        self, tmp_path: Path
    ) -> None:
        """Decode errors are configuration failures, not silent skips."""
        repo = _make_repo(tmp_path, memories=("pr-review/target",))
        _write(repo / _SKILL, _call("pr-review/target"))
        (repo / ".claude" / "skills" / "example" / "binary.md").write_bytes(
            b"\xff\xfe not utf-8"
        )
        with pytest.raises(SystemExit) as exc_info:
            _run(repo)
        assert exc_info.value.code == csmr.EXIT_CONFIG


# --- Real corpus -----------------------------------------------------------


class TestShippedCorpus:
    def test_the_shipped_instruction_corpus_resolves(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``.claude/rules/ci-scripts.md`` MUST 13: prove it on the real tree.

        A fixture proves the checker's logic. It proves nothing about whether
        the corpus satisfies the gate, and only the second claim decides
        whether main goes red.
        """
        assert csmr.main(["--repo-root", str(REPO_ROOT)]) == csmr.EXIT_OK
        assert "[PASS]" in capsys.readouterr().out

