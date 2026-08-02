"""Tests for the documented-interpreter portability ratchet (issue #3791)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.validation.check_doc_interpreter_portability import (
    INVOCATION_PATTERN,
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
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def write_baseline(repo: Path, files: dict[str, int]) -> Path:
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

    assert scan(repo) == {"README.md": 1}


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
    assert scan(repo) == {"README.md": 1}


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

    assert scan(repo) == {"README.md": 1}


def test_relative_dot_slash_script_path_is_flagged(tmp_path: Path) -> None:
    """`./scripts/<file>.py` names the same script as `scripts/<file>.py`."""
    repo = make_repo(
        tmp_path,
        {"scripts/tool.py": "import yaml\n", "README.md": "Run `python3 ./scripts/tool.py`.\n"},
    )

    assert scan(repo) == {"README.md": 1}


def test_class_body_import_runs_at_import_time_and_is_flagged(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"tool.py": "class A:\n    import yaml\n"})

    assert third_party_imports("tool.py", repo, {"tool.py"}) == {"yaml"}


# --- negative: correct usage is not flagged ---------------------------------


def test_the_uv_flag_group_does_not_backtrack_exponentially() -> None:
    """CodeQL flagged the uv flag group for exponential backtracking.

    The old form let `\\S*` swallow the following flag, so `uv run --=--=--=...`
    had exponentially many parses. Measured on the old pattern: 12 repetitions
    took 1.1 ms, 16 took 16.8 ms, 20 took 272 ms. This bound is generous by three
    orders of magnitude against that curve, so it fails loudly on a regression
    without being flaky on a slow machine.
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
def test_every_uv_form_in_the_corpus_still_matches(command: str) -> None:
    """The rewrite must not narrow what it recognises.

    These four are the only `uv run ... python` shapes present in the tree, by
    frequency: bare, --frozen, --frozen --extra dev, and --with pyyaml.
    """
    assert INVOCATION_PATTERN.search(command) is not None


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

    assert scan(repo) == {"doc.md": 1}


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

    assert scan(repo) == {"doc.md": 1}


def test_python_usage_docstring_is_an_offense(tmp_path: Path) -> None:
    """The surface widened past Markdown: a docstring hands over the same command."""
    repo = make_repo(
        tmp_path,
        {"tool.py": '"""Usage:\n\n    python3 tool.py --check\n"""\n\nimport yaml\n'},
    )

    assert scan(repo) == {"tool.py": 1}


def test_unreadable_baseline_exits_2(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": "nothing to see\n"})

    exit_code = main(["--repo-root", str(repo), "--baseline", str(repo / "missing.json")])

    assert exit_code == 2


def test_update_baseline_writes_current_counts(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {"tool.py": "import yaml\n", "README.md": "Run `python3 tool.py`.\n"},
    )
    baseline = repo / "baseline.json"

    exit_code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"])

    assert exit_code == 0
    assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {"README.md": 1}
