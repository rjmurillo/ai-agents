# taste-lint: ignore file-size -- one suite owns shared git fixtures and the failure matrix.
"""Tests for the documented-interpreter portability ratchet (issue #3791)."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.validation.check_doc_interpreter_portability import (
    INVOCATION_PATTERN,
    find_offenses,
    is_in_scope,
    main,
    scan,
    third_party_imports,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# The three scripts issue #3791 names, and the module each one needs. Every one
# is a declared project dependency, so `uv run python` resolves it and a bare
# system interpreter may not.
ISSUE_3791_SCRIPTS = {
    "scripts/sync_adr_protocol.py": "yaml",
    "build/generate_agents.py": "yaml",
    "build/scripts/build_all.py": "yaml",
}


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a git repo at ``tmp_path`` with ``files`` committed."""
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def write_baseline(repo: Path, files: dict[str, int | list[str]]) -> Path:
    """Write a baseline JSON and return its path."""
    path = repo / "baseline.json"
    path.write_text(json.dumps({"files": files}), encoding="utf-8")
    return path


# --- positive: the defect is detected ---------------------------------------


def test_bare_interpreter_with_third_party_import_is_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import yaml\n",
            "README.md": "Run `python3 tool.py` to sync.\n",
        },
    )

    assert scan(repo) == {"README.md": ["tool.py"]}


def test_cli_exits_1_when_a_clean_file_starts_offending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"tool.py": "import yaml\n", "README.md": "Run `python3 tool.py`.\n"},
    )
    baseline = write_baseline(repo, {})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline)])

    assert exit_code == 1
    assert "README.md" in capsys.readouterr().err


def test_validation_ignores_ambient_git_repository_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_repo(
        tmp_path / "target",
        {"tool.py": "import yaml\n", "README.md": "Run `python3 tool.py`.\n"},
    )
    baseline = write_baseline(repo, {})
    other_repo = make_repo(tmp_path / "other", {"unrelated.txt": "other\n"})
    monkeypatch.setenv("GIT_DIR", str(other_repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other_repo))

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline)])

    assert exit_code == 1
    assert "README.md" in capsys.readouterr().err


def test_validation_disables_git_replacement_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path, {"README.md": "No command.\n"})
    baseline = write_baseline(repo, {})
    run_mock = Mock(wraps=subprocess.run)
    monkeypatch.setattr(subprocess, "run", run_mock)

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline)])

    git_commands = [call.args[0] for call in run_mock.call_args_list]
    assert exit_code == 0
    assert git_commands
    assert all(command[:2] == ["git", "--no-replace-objects"] for command in git_commands)


def test_validation_reports_git_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_repo(tmp_path, {"README.md": "text\n"})
    baseline = write_baseline(repo, {})

    def time_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="git", timeout=30)

    monkeypatch.setattr(subprocess, "run", time_out)

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline)])

    assert exit_code == 2
    assert "git command timed out after 30 seconds" in capsys.readouterr().err


def test_direct_script_execution_imports_sibling_helper(tmp_path: Path) -> None:
    validation_dir = tmp_path / "scripts" / "validation"
    validation_dir.mkdir(parents=True)
    for name in (
        "check_doc_interpreter_portability.py",
        "doc_interpreter_subprocess.py",
        "portability_baseline.py",
        "portability_baseline_write.py",
        "portability_floor.py",
        "portability_git.py",
    ):
        source = REPO_ROOT / "scripts" / "validation" / name
        (validation_dir / name).write_bytes(source.read_bytes())
    (tmp_path / "tool.py").write_text("import json\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Run `python3 tool.py`.\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    baseline = write_baseline(tmp_path, {})

    completed = subprocess.run(
        [
            sys.executable,
            str(validation_dir / "check_doc_interpreter_portability.py"),
            "--repo-root",
            str(tmp_path),
            "--baseline",
            str(baseline),
            "--update-baseline",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert baseline.is_file()
    assert "wrote" in completed.stdout


def test_transitive_local_import_reaches_third_party(tmp_path: Path) -> None:
    """build/generate_agents.py imports yaml only through build/scripts/yaml_loader.py."""
    repo = make_repo(
        tmp_path,
        {
            "pkg/loader.py": "import yaml\n",
            "entry.py": "import loader\n",
            "README.md": "Run `python3 entry.py`.\n",
        },
    )

    assert third_party_imports("entry.py", repo, {"pkg/loader.py", "entry.py"}) == {"yaml"}
    assert scan(repo) == {"README.md": ["entry.py"]}


def test_subprocess_wrapper_reaches_third_party_dependency(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "validate.py": "import jsonschema\n",
            "entry.py": (
                "import os\nimport subprocess\nimport sys\n"
                "def validate(repo_root):\n"
                "    target = os.path.join(repo_root, 'validate.py')\n"
                "    subprocess.run([sys.executable, target], check=False)\n"
                "def main():\n"
                "    validate('.')\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
            "README.md": "Run `python3 entry.py`.\n",
        },
    )

    assert third_party_imports("entry.py", repo, {"entry.py", "validate.py"}) == {"jsonschema"}
    assert scan(repo) == {"README.md": ["entry.py"]}


def test_dot_directory_script_path_is_flagged(tmp_path: Path) -> None:
    """`python3 .claude/skills/<name>/scripts/<file>.py` is a documented invocation.

    The operand used to have to start with a word character, so every script
    under a dot-directory was invisible to the guard. Four `.claude/` invocations
    of `detect_adr_changes.py` (which is `import yaml`) sat unreported.
    """
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/x/scripts/tool.py": "import yaml\n",
            "README.md": "Run `python3 .claude/skills/x/scripts/tool.py`.\n",
        },
    )

    assert scan(repo) == {"README.md": [".claude/skills/x/scripts/tool.py"]}


def test_relative_dot_slash_script_path_is_flagged(tmp_path: Path) -> None:
    """`./scripts/<file>.py` names the same script as `scripts/<file>.py`."""
    repo = make_repo(
        tmp_path,
        {"scripts/tool.py": "import yaml\n", "README.md": "Run `python3 ./scripts/tool.py`.\n"},
    )

    assert scan(repo) == {"README.md": ["scripts/tool.py"]}


def test_class_body_import_runs_at_import_time_and_is_flagged(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"tool.py": "class A:\n    import yaml\n"})

    assert third_party_imports("tool.py", repo, {"tool.py"}) == {"yaml"}


# --- negative: correct usage is not flagged ---------------------------------


def test_the_uv_flag_group_does_not_backtrack_exponentially() -> None:
    """CodeQL flagged the uv flag group for exponential backtracking.

    The old form parsed the optional `uv run` prefix inside the same regex that
    found Python invocations. That let the flag group split one long flag string
    many ways before giving up. The matcher now finds Python invocations only,
    and the `uv run` prefix check runs in normal Python token logic.
    """
    import time

    hostile = "uv run " + "--=" * 4000 + "!"
    started = time.perf_counter()
    INVOCATION_PATTERN.search(hostile)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"pattern took {elapsed:.3f}s on hostile input; it backtracks"


@pytest.mark.parametrize(
    "command",
    [
        "uv run python scripts/x.py",
        "uv run --frozen python scripts/x.py",
        "uv run --frozen --extra dev python scripts/x.py",
        "uv run --with pyyaml python3 scripts/x.py",
    ],
)
def test_every_uv_form_in_the_corpus_is_skipped(command: str, tmp_path: Path) -> None:
    """The rewrite must still recognize fixed invocations as fixed.

    These four are the only `uv run ... python` shapes present in the tree, by
    frequency: bare, --frozen, --frozen --extra dev, and --with pyyaml.
    """
    repo = make_repo(tmp_path, {"scripts/x.py": "import yaml\n"})

    assert find_offenses(command, repo, {"scripts/x.py"}) == []


def test_uv_run_prefix_is_not_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import yaml\n",
            "README.md": "Run `uv run python tool.py` to sync.\n",
        },
    )

    assert scan(repo) == {}


def test_stdlib_only_script_is_not_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import json\nimport pathlib\n",
            "README.md": "Run `python3 tool.py`.\n",
        },
    )

    assert scan(repo) == {}


def test_untracked_script_is_not_flagged(tmp_path: Path) -> None:
    """A placeholder path such as .claude/hooks/<Event>/invoke_<x>.py is not tracked."""
    repo = make_repo(tmp_path, {"README.md": "Run `python3 not_a_real_file.py`.\n"})

    assert scan(repo) == {}


def test_shebang_is_not_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {"tool.py": "import yaml\n", "README.md": "Start with `#!/usr/bin/env python3`.\n"},
    )

    assert scan(repo) == {}


def test_cli_exits_0_when_counts_match_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"tool.py": "import yaml\n", "README.md": "Run `python3 tool.py`.\n"},
    )
    baseline = write_baseline(repo, {"README.md": 1})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline)])

    assert exit_code == 0
    assert "OK" in capsys.readouterr().out


# --- edge: the two false-positive classes that would block working commands ---


def test_function_body_import_is_not_flagged(tmp_path: Path) -> None:
    """scripts/eval/eval-suite.py reaches `anthropic` only inside a function body.

    `python3 -S scripts/eval/eval-suite.py --dry-run` succeeds, so counting a
    lazy import would report a working documented command as broken.
    """
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import json\n\n\ndef run():\n    import anthropic\n    return anthropic\n",
            "README.md": "Run `python3 tool.py`.\n",
        },
    )

    assert third_party_imports("tool.py", repo, {"tool.py"}) == set()
    assert scan(repo) == {}


def test_ambiguous_local_module_is_not_followed(tmp_path: Path) -> None:
    """Two tracked candidates for one import name prove nothing about which loads.

    scripts/memory/validate_memory_sizes.py imports `test_memory_size`, which
    matches four tracked files; one imports pytest. The script runs clean under
    `python3 -S`, so unioning the candidates invents a dependency.
    """
    repo = make_repo(
        tmp_path,
        {
            "a/helper.py": "import json\n",
            "b/helper.py": "import pytest\n",
            "entry.py": "import helper\n",
            "README.md": "Run `python3 entry.py`.\n",
        },
    )

    tracked = {"a/helper.py", "b/helper.py", "entry.py"}
    assert third_party_imports("entry.py", repo, tracked) == set()
    assert scan(repo) == {}


def test_same_directory_import_wins_over_repo_wide_match(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "helper.py": "import yaml\n",
            "far/helper.py": "import json\n",
            "entry.py": "import helper\n",
        },
    )

    tracked = {"helper.py", "far/helper.py", "entry.py"}
    assert third_party_imports("entry.py", repo, tracked) == {"yaml"}


@pytest.mark.parametrize(
    "path",
    [
        ".agents/sessions/2026-01-01-session-01.md",
        ".agents/retrospective/postmortem.md",
        ".agents/architecture/ADR-029-line-endings.md",
        ".serena/memories/note.md",
        "evals/reports/run.md",
    ],
)
def test_historical_records_are_out_of_scope(path: str) -> None:
    """A command quoted in a record describes what ran; rewriting it falsifies it."""
    assert not is_in_scope(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/copilot-cli/skills/session-init/SKILL.md",
        "src/vs-code-agents/retrospective.agent.md",
        ".github/instructions/python.instructions.md",
        ".github/prompts/pr-quality-gate-architect.md",
    ],
)
def test_generated_mirrors_are_out_of_scope(path: str) -> None:
    """Build outputs are fixed at their source and arrive here by regeneration."""
    assert not is_in_scope(path)


@pytest.mark.parametrize(
    "path",
    ["src/claude/AGENTS.md", "src/claude/architect.md"],
)
def test_hand_maintained_src_claude_is_in_scope(path: str) -> None:
    """`src/claude/` looks like a generated mirror and is not one.

    `.agents/governance/GENERATOR-FILES.md:35` states it verbatim: "`src/claude/`
    is a hand-maintained copy, not a generator output. It was misclassified as a
    strict vendored copy until Issue #2882". No generator writes it, and
    `build/scripts/validate_install_parity.py:97` blocklists `AGENTS.md` from
    every parity group, so `src/claude/AGENTS.md` is guarded by nothing else.

    An earlier revision of this guard listed `src/claude/` beside the real
    mirrors. Five `build/generate_agents.py` invocations in `src/claude/AGENTS.md`
    (lines 61, 70, 279, 294, 305) survived two rounds of the issue #3791 fix
    behind that one entry.
    """
    assert is_in_scope(path)


@pytest.mark.parametrize(
    "path",
    [
        ".claude/skills/session-init/scripts/new_session_log.py",
        "build/scripts/build_all.py",
        "scripts/ci/write_drift_job_summary.py",
    ],
)
def test_python_sources_are_in_scope(path: str) -> None:
    """A usage docstring and a printed remediation hand over the same broken command."""
    assert is_in_scope(path)


@pytest.mark.parametrize(
    "path",
    ["tests/test_check_doc_interpreter_portability.py", "tests/validation/test_x.py"],
)
def test_test_fixtures_are_out_of_scope(path: str) -> None:
    """Tests build offending invocations on purpose; see `.claude/rules/universal.md`."""
    assert not is_in_scope(path)


@pytest.mark.parametrize(
    "path",
    ["CONTRIBUTING.md", ".agents/SESSION-PROTOCOL.md", "docs/installation.md", "README.md"],
)
def test_live_instruction_docs_are_in_scope(path: str) -> None:
    assert is_in_scope(path)


def test_declaration_on_the_offending_line_suppresses_it(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import yaml\n",
            "doc.md": "`python3 tool.py`  <!-- doc-interpreter-portability: quoted CI -->\n",
        },
    )

    assert scan(repo) == {}


def test_declaration_on_the_line_above_suppresses_it(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import yaml\n",
            "doc.md": "doc-interpreter-portability: quoted CI\n    python3 tool.py\n",
        },
    )

    assert scan(repo) == {}


def test_declaration_two_lines_above_does_not_suppress(tmp_path: Path) -> None:
    """Negative control: the opt-out is line-scoped, not file-scoped."""
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import yaml\n",
            "doc.md": "doc-interpreter-portability: quoted CI\n\n    python3 tool.py\n",
        },
    )

    assert scan(repo) == {"doc.md": ["tool.py"]}


def test_declaration_does_not_cover_a_sibling_offense_in_the_same_file(tmp_path: Path) -> None:
    """A declared line must not grant the rest of the file an exemption."""
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import yaml\n",
            "doc.md": (
                "`python3 tool.py`  <!-- doc-interpreter-portability: quoted CI -->\n"
                "\n"
                "Now run `python3 tool.py` for real.\n"
            ),
        },
    )

    assert scan(repo) == {"doc.md": ["tool.py"]}


def test_python_usage_docstring_is_an_offense(tmp_path: Path) -> None:
    """The surface widened past Markdown: a docstring hands over the same command."""
    repo = make_repo(
        tmp_path,
        {"tool.py": '"""Usage:\n\n    python3 tool.py --check\n"""\n\nimport yaml\n'},
    )

    assert scan(repo) == {"tool.py": ["tool.py"]}


def test_unreadable_baseline_exits_2(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": "nothing to see\n"})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(repo / "missing.json")])

    assert exit_code == 2


def test_update_baseline_requires_existing_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"tool.py": "import yaml\n", "README.md": "Run `python3 tool.py`.\n"},
    )
    baseline = repo / "baseline.json"

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"])

    assert exit_code == 2
    assert not baseline.exists()
    assert "baseline not found" in capsys.readouterr().err


def test_update_baseline_refuses_oversized_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, {"README.md": "No command.\n"})
    baseline = repo / "baseline.json"
    baseline.write_bytes(b"x" * 200_001)

    exit_code = main(
        [
            "--repo-root",
            str(repo),
            "--baseline",
            str(baseline),
            "--update-baseline",
        ]
    )

    assert exit_code == 2
    assert "exceeds the reviewability ceiling" in capsys.readouterr().err


def test_update_baseline_refuses_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, {"README.md": "No command.\n"})
    target = write_baseline(repo, {"README.md": 1})
    baseline = repo / "baseline-link.json"
    baseline.symlink_to(target.name)
    original = target.read_text(encoding="utf-8")

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"])

    assert exit_code == 2
    assert baseline.is_symlink()
    assert target.read_text(encoding="utf-8") == original
    assert "through a symlink" in capsys.readouterr().err


def test_update_baseline_refuses_symlinked_parent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {
            "README.md": "No command.\n",
            "real/baseline.json": '{"files": {}}\n',
        },
    )
    linked = repo / "linked"
    linked.symlink_to(repo / "real", target_is_directory=True)

    exit_code = main(
        [
            "--repo-root",
            str(repo),
            "--baseline",
            str(linked / "baseline.json"),
            "--update-baseline",
        ]
    )

    assert exit_code == 2
    assert "through a symlink" in capsys.readouterr().err


def test_update_baseline_refuses_hidden_diff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".gitattributes": "baseline.json -diff\n",
            "README.md": "No command.\n",
            "baseline.json": '{"files": {}}\n',
        },
    )

    exit_code = main(
        [
            "--repo-root",
            str(repo),
            "--baseline",
            str(repo / "baseline.json"),
            "--update-baseline",
        ]
    )

    assert exit_code == 2
    assert "told not to diff" in capsys.readouterr().err


def test_update_baseline_uses_shared_write_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path, {"README.md": "No command.\n"})
    baseline = write_baseline(repo, {})
    acquired: list[Path] = []

    @contextmanager
    def record_lock(lock_path: Path) -> Iterator[None]:
        acquired.append(lock_path)
        yield

    monkeypatch.setattr(
        "scripts.validation.check_doc_interpreter_portability.baseline_write_lock",
        record_lock,
    )

    exit_code = main(
        [
            "--repo-root",
            str(repo),
            "--baseline",
            str(baseline),
            "--update-baseline",
        ]
    )

    assert exit_code == 0
    assert acquired == [repo / ".baseline.json.write-lock"]


def test_update_baseline_refuses_count_increase(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"tool.py": "import yaml\n", "README.md": "Run `python3 tool.py`.\n"},
    )
    baseline = write_baseline(repo, {})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"])

    assert exit_code == 1
    assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {}
    error = capsys.readouterr().err
    assert "README.md:1" in error
    assert "tool.py imports yaml" in error
    assert "refusing to raise baseline" in error


def test_update_baseline_records_verified_reduction(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"tool.py": "import yaml\n", "README.md": "No command.\n"})
    baseline = write_baseline(repo, {"README.md": 1})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"])

    assert exit_code == 0
    assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {}


def test_update_baseline_preserves_original_when_replace_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path, {"README.md": "No command.\n"})
    baseline = write_baseline(repo, {"README.md": 1})
    original = baseline.read_text(encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> Path:
        if target == baseline:
            raise OSError("replace failed")
        return source

    monkeypatch.setattr(Path, "replace", fail_replace)

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"])

    assert exit_code == 2
    assert baseline.read_text(encoding="utf-8") == original
    assert list(baseline.parent.glob(f".{baseline.name}.*.tmp")) == []
    assert "replace failed" in capsys.readouterr().err


def test_update_baseline_preserves_replace_error_when_cleanup_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path, {"README.md": "No command.\n"})
    baseline = write_baseline(repo, {"README.md": 1})
    original = baseline.read_text(encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> Path:
        if target == baseline:
            raise OSError("replace failed")
        return source

    def fail_cleanup(path: Path, missing_ok: bool = False) -> None:
        del missing_ok
        if path.name.startswith(f".{baseline.name}."):
            raise OSError("cleanup failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"])

    assert exit_code == 2
    assert baseline.read_text(encoding="utf-8") == original
    error = capsys.readouterr().err
    assert "replace failed" in error
    assert "cleanup failed" not in error


def test_update_baseline_reports_cleanup_only_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo(tmp_path, {"README.md": "No command.\n"})
    baseline = write_baseline(repo, {"README.md": 1})

    def fail_cleanup(path: Path, missing_ok: bool = False) -> None:
        del missing_ok
        if path.name.startswith(f".{baseline.name}."):
            raise OSError("cleanup failed")

    monkeypatch.setattr(Path, "unlink", fail_cleanup)

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"])

    assert exit_code == 2
    assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {}
    assert "cleanup failed" in capsys.readouterr().err


def test_update_baseline_refuses_empty_scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, {"tests/fixture.md": "Run `python3 tool.py`.\n"})
    baseline = write_baseline(repo, {"README.md": 1})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"])

    assert exit_code == 2
    assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {"README.md": 1}
    assert "refusing zero-file scan" in capsys.readouterr().err


def test_update_baseline_refuses_repository_subdirectory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"docs/README.md": "No command.\n", "outside.md": "No command.\n"},
    )
    baseline = write_baseline(repo, {"outside.md": 1})
    original = baseline.read_text(encoding="utf-8")

    exit_code = main(
        [
            "--repo-root",
            str(repo / "docs"),
            "--baseline",
            str(baseline),
            "--update-baseline",
        ]
    )

    assert exit_code == 2
    assert baseline.read_text(encoding="utf-8") == original
    assert "repository root must be" in capsys.readouterr().err


def test_validation_refuses_empty_scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, {"tests/fixture.md": "No command.\n"})
    baseline = write_baseline(repo, {})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline)])

    assert exit_code == 2
    assert "refusing zero-file scan" in capsys.readouterr().err


def test_update_baseline_refuses_partial_scan_with_unreadable_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, {"README.md": "No command.\n", "bad.md": "placeholder\n"})
    (repo / "bad.md").write_bytes(b"\xff")
    baseline = write_baseline(repo, {"bad.md": 1})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"])

    assert exit_code == 2
    assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {"bad.md": 1}
    assert "could not read bad.md" in capsys.readouterr().err


def test_validation_refuses_malformed_referenced_script(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {"README.md": "Run `python3 tool.py`.\n", "tool.py": "def broken(:\n"},
    )
    baseline = write_baseline(repo, {})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline)])

    assert exit_code == 2
    assert "could not analyze tool.py" in capsys.readouterr().err


def test_validation_refuses_missing_tracked_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, {"README.md": "No command.\n", "missing.md": "tracked\n"})
    (repo / "missing.md").unlink()
    baseline = write_baseline(repo, {})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline)])

    assert exit_code == 2
    assert "tracked file is missing or not a regular file: missing.md" in capsys.readouterr().err
