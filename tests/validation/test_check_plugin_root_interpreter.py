# taste-lint: ignore file-size -- one suite owns shared git fixtures and the failure matrix.
"""Tests for the plugin-root interpreter validator (issue #5949)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation.check_plugin_root_interpreter import (
    find_offenses,
    is_in_scope,
    main,
    scan,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a git repo at ``tmp_path`` with ``files`` committed to the index."""
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


# --- positive: the canonical form is not flagged --------------------------


def test_python3_with_stdlib_script_is_clean_whole_operand_quoted(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "README.md": (
                'Run `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    assert scan(repo) == []


def test_python3_with_stdlib_script_is_clean_quote_closes_before_path(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "README.md": (
                'Run `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"'
                "/skills/foo/scripts/bar.py` to sync.\n"
            ),
        },
    )

    assert scan(repo) == []


def test_python3_with_short_option_is_still_canonical(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "README.md": (
                'Run `python3 -u "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    assert scan(repo) == []


# --- negative: form violations (rule 1) ------------------------------------


def test_uv_run_python_is_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "README.md": (
                'Run `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    offenses = scan(repo)
    assert len(offenses) == 1
    assert "python3" in offenses[0]
    assert "'uv run python'" in offenses[0]


def test_uv_run_with_option_python_is_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "README.md": (
                "Run `uv run --frozen python "
                '"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    offenses = scan(repo)
    assert len(offenses) == 1
    assert "'uv run --frozen python'" in offenses[0]


def test_uv_run_python_with_unquoted_operand_is_flagged(tmp_path: Path) -> None:
    # The quality-auditor agent template carried this shape, which the issue's
    # quoted-only grep did not count.
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "README.md": (
                "Run `uv run python ${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
                "/skills/foo/scripts/bar.py --query x`.\n"
            ),
        },
    )

    offenses = scan(repo)
    assert len(offenses) == 1
    assert "'uv run python'" in offenses[0]


def test_uv_run_before_a_shell_separator_does_not_capture_the_next_command(
    tmp_path: Path,
) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "README.md": (
                "Run `uv run pytest -q; python3 "
                '"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"`.\n'
            ),
        },
    )

    assert scan(repo) == []


def test_bare_python_is_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "README.md": (
                'Run `python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    offenses = scan(repo)
    assert len(offenses) == 1
    assert "'python'" in offenses[0]


def test_pinned_python_version_is_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "README.md": (
                'Run `python3.11 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    offenses = scan(repo)
    assert len(offenses) == 1
    assert "'python3.11'" in offenses[0]


# --- negative: dependency violations (rule 2) -------------------------------


def test_python3_on_script_importing_yaml_is_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import yaml\n",
            "README.md": (
                'Run `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    offenses = scan(repo)
    assert len(offenses) == 1
    assert "imports yaml" in offenses[0]


def test_python3_on_script_importing_yaml_transitively_is_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "from helper import do_it\n",
            ".claude/skills/foo/scripts/helper.py": "import yaml\n",
            "README.md": (
                'Run `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    offenses = scan(repo)
    assert len(offenses) == 1
    assert "imports yaml" in offenses[0]


def test_dangling_target_is_flagged(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "README.md": (
                'Run `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/missing.py"` to sync.\n'
            ),
        },
    )

    offenses = scan(repo)
    assert len(offenses) == 1
    assert "dangling plugin-root target" in offenses[0]
    assert ".claude/skills/foo/scripts/missing.py" in offenses[0]


def test_form_violation_suppresses_the_dependency_check(tmp_path: Path) -> None:
    """A rule-1 violation is reported once; rule 2 does not pile on."""
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import yaml\n",
            "README.md": (
                'Run `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    offenses = scan(repo)
    assert len(offenses) == 1
    assert "python3" in offenses[0]
    assert "imports" not in offenses[0]


# --- edge cases --------------------------------------------------------------


def test_line_continuation_split_invocation_is_clean_when_the_target_exists(
    tmp_path: Path,
) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "NOTES.md": (
                "echo before\n"
                "python3 \\\n"
                '  "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"\n'
            ),
        },
    )

    assert scan(repo) == []


def test_line_continuation_split_invocation_is_reported_at_its_start_line(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path, {"README.md": "placeholder\n"})
    text = (
        "echo before\n"
        "python3 \\\n"
        '  "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
        '/skills/foo/scripts/missing.py"\n'
    )

    offenses = find_offenses(text, "NOTES.md", repo, set())

    assert len(offenses) == 1
    lineno, message = offenses[0]
    assert lineno == 2
    assert "dangling plugin-root target" in message


def test_opt_out_marker_on_the_offending_line_suppresses_it(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "README.md": (
                "Run `uv run python "
                '"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/missing.py"` to sync.'
                " <!-- plugin-root-interpreter: CI installs deps system-wide here -->\n"
            ),
        },
    )

    assert scan(repo) == []


def test_opt_out_marker_on_the_line_above_suppresses_it(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "README.md": (
                "<!-- plugin-root-interpreter: CI installs deps system-wide here -->\n"
                'Run `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/missing.py"` to sync.\n'
            ),
        },
    )

    assert scan(repo) == []


def test_files_under_tests_are_ignored(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "tests/fixtures/README.md": (
                'Run `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/missing.py"` on purpose.\n'
            ),
        },
    )

    assert scan(repo) == []


def test_files_under_a_historical_root_are_ignored(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".project-toolkit/sessions/2026-01-01-log.md": (
                'Ran `uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/missing.py"` during the session.\n'
            ),
        },
    )

    assert scan(repo) == []


def test_is_in_scope_excludes_the_documented_roots() -> None:
    assert is_in_scope("README.md") is True
    assert is_in_scope("tests/fixtures/README.md") is False
    assert is_in_scope(".project-toolkit/sessions/2026-01-01-log.md") is False


def test_prose_mention_of_the_env_var_without_an_interpreter_is_ignored(
    tmp_path: Path,
) -> None:
    repo = make_repo(
        tmp_path,
        {
            "README.md": (
                "See `${COPILOT_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_ROOT}` for details "
                "on how the plugin root resolves; neither is invoked here.\n"
            ),
        },
    )

    assert scan(repo) == []


# --- CLI -----------------------------------------------------------------


def test_cli_exits_0_on_a_clean_repo(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            ".claude/skills/foo/scripts/bar.py": "import json\n",
            "README.md": (
                'Run `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    assert main(["--repo-root", str(repo)]) == 0


def test_cli_exits_1_on_an_offending_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(
        tmp_path,
        {
            "README.md": (
                'Run `python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
                '/skills/foo/scripts/bar.py"` to sync.\n'
            ),
        },
    )

    exit_code = main(["--repo-root", str(repo)])

    assert exit_code == 1
    err = capsys.readouterr().err
    # Built, not literal, so citation-freshness does not read it as a path:line cite.
    assert ":".join(("README.md", "1")) in err
    assert "FAIL" in err


def test_cli_reports_config_error_on_unreadable_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"README.md": "hello\n"})
    binary_path = repo / "broken.py"
    binary_path.write_bytes(b"\xff\xfe\x00\x01")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)

    exit_code = main(["--repo-root", str(repo)])

    assert exit_code == 2


# --- repository-level: the real corpus ---------------------------------


def test_the_real_repository_is_clean() -> None:
    """The shipped tree must satisfy its own new gate.

    If this fails, the reported offenses name real, pre-existing plugin-root
    invocations that are not yet in the canonical form -- see the offense
    messages for the exact file, line, and reason.
    """
    assert main(["--repo-root", str(REPO_ROOT)]) == 0
