"""Tests for the documented-interpreter portability ratchet (issue #3791)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation.check_doc_interpreter_portability import (
    find_offenses,
    is_in_scope,
    main,
    scan,
    third_party_imports,
    tracked_files,
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
        "src/claude/architect.md",
        "src/vs-code-agents/retrospective.agent.md",
        ".github/instructions/python.instructions.md",
    ],
)
def test_generated_mirrors_are_out_of_scope(path: str) -> None:
    """Build outputs are fixed at their source and arrive here by regeneration."""
    assert not is_in_scope(path)


@pytest.mark.parametrize(
    "path",
    ["CONTRIBUTING.md", ".agents/SESSION-PROTOCOL.md", "docs/installation.md", "README.md"],
)
def test_live_instruction_docs_are_in_scope(path: str) -> None:
    assert is_in_scope(path)


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


# --- regression: the issue #3791 surface stays fixed ------------------------


@pytest.mark.parametrize("doc", ["CONTRIBUTING.md", ".agents/SESSION-PROTOCOL.md"])
def test_onboarding_docs_name_no_bare_interpreter_for_issue_3791_scripts(doc: str) -> None:
    """The contributor-onboarding docs must not tell a reader to run these bare.

    A fresh checkout has no system PyYAML, so `python3 scripts/sync_adr_protocol.py`
    dies with ModuleNotFoundError. CONTRIBUTING.md:838 is a required pre-submit
    step, which is why this is a blocking regression test rather than prose.
    """
    tracked_py = set(tracked_files(REPO_ROOT, "*.py"))
    text = (REPO_ROOT / doc).read_text(encoding="utf-8")

    flagged = [
        (number, script)
        for number, line in enumerate(text.splitlines(), 1)
        for script, _ in find_offenses(line, REPO_ROOT, tracked_py)
        if script in ISSUE_3791_SCRIPTS
    ]

    assert flagged == []


def test_issue_3791_scripts_still_need_a_project_environment() -> None:
    """If a script stops importing its third-party module, the guard entry is stale.

    This is the negative control for the test above: it fails if the premise
    (these scripts need more than the stdlib) ever stops holding, rather than
    letting the regression test pass vacuously.
    """
    tracked_py = set(tracked_files(REPO_ROOT, "*.py"))

    for script, module in ISSUE_3791_SCRIPTS.items():
        assert module in third_party_imports(script, REPO_ROOT, tracked_py), (
            f"{script} no longer imports {module}; revisit the issue #3791 doc fix"
        )


def test_repository_is_at_or_below_its_baseline() -> None:
    exit_code = main(["--repo-root", str(REPO_ROOT)])

    assert exit_code == 0


def test_repository_has_no_documented_bare_interpreter_invocations() -> None:
    """No in-scope document may name a bare interpreter for a non-stdlib script.

    Issue #3791 named one instance (`scripts/sync_adr_protocol.py` in
    CONTRIBUTING.md). Fixing only that one left 112 identical siblings across 47
    files, all of which die with the same ModuleNotFoundError on a clean
    checkout. They were migrated in the same change, so the correct count is
    zero, and this asserts the whole class rather than the named instance.

    Stronger than `test_repository_is_at_or_below_its_baseline`, which a
    `--update-baseline` run would satisfy by grandfathering a new offender.
    """
    offenders = scan(REPO_ROOT)

    assert offenders == {}, (
        "documented bare-interpreter invocations came back: "
        + ", ".join(f"{rel} ({count})" for rel, count in sorted(offenders.items()))
        + ". Use 'uv run python <script>' (issue #3791)."
    )


def test_bare_python3_still_fails_for_a_declared_dependency() -> None:
    """Ground the whole guard in the real interpreter, not in our import model."""
    result = subprocess.run(
        [sys.executable, "-S", "-c", "import yaml"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode == 0:
        pytest.skip("this interpreter has system-wide PyYAML, so -S cannot isolate it")
    assert "ModuleNotFoundError" in result.stderr
