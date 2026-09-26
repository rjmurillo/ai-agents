"""Regression tests for the issue #5420 .agents/ write-target gate.

``.agents/`` now holds only read-only canonical inputs (issue #5420). These
tests exercise both findings the gate produces: a stale reference to a
directory that moved to ``.project-toolkit/<sub>``, and write intent aimed at
a KEEP subtree, a KEEP top-level file, or the bare ``.agents`` root.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(VALIDATION) not in sys.path:
    sys.path.insert(0, str(VALIDATION))

import check_agents_write_targets as checker


def _init_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a tmp git repo with the given files staged (no commit needed)."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", relative], cwd=tmp_path, check=True)
    return tmp_path


# ---------------------------------------------------------------------------
# scan_text: STALE ROOT (rule a) -- fires regardless of write intent.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "See `.agents/sessions/x.json` for details.\n",
        "See `.agents\\sessions\\x.json` for details.\n",
        "Read `.agents/sessions-evil`.\n",
    ],
)
def test_stale_moved_subtree_reference_rejected(text: str) -> None:
    findings = checker.scan_text("docs/example.md", text)
    assert findings
    assert all(f.reason == checker._STALE_REASON for f in findings)


@pytest.mark.parametrize(
    "text",
    [
        "Run the check against `.agents/context-output-manifest.json`.\n",
        "See `.agents/context/tests/index.md`.\n",
        "Learnings live in `.agents/skills/linting.md`.\n",
    ],
)
def test_issue_5421_moved_subtree_reference_rejected(text: str) -> None:
    """Issue #5421 moved the generated context and skills trees out of KEEP."""
    findings = checker.scan_text("docs/example.md", text)
    assert findings
    assert all(f.reason == checker._STALE_REASON for f in findings)


def test_stale_reference_in_project_toolkit_history_is_not_scanned() -> None:
    """A file under an excluded root is never read, so old refs inside it
    (kept for historical record) never reach scan_text at all."""
    assert not checker._is_scanned(".project-toolkit/retrospective/2025.md")
    assert not checker._is_scanned(".agents/archive/old-plan.md")
    assert not checker._is_scanned(".claude-mem/session.md")


# ---------------------------------------------------------------------------
# scan_text: WRITE INTO KEEP / BARE ROOT (rule b) -- requires write intent.
# ---------------------------------------------------------------------------


def test_write_instruction_into_keep_subtree_rejected() -> None:
    text = "Save the report to `.agents/governance/x.md`.\n"
    findings = checker.scan_text("docs/example.md", text)
    assert findings
    assert findings[0].reason == checker._TEXT_WRITE_REASON


def test_shell_redirect_into_keep_subtree_rejected() -> None:
    text = 'echo "data" > .agents/governance/output.txt\n'
    assert checker.scan_text("scripts/example.sh", text)


def test_shell_append_and_tee_into_keep_subtree_rejected() -> None:
    assert checker.scan_text("scripts/a.sh", "cmd >> .agents/governance/log.txt\n")
    assert checker.scan_text("scripts/b.sh", "cmd | tee .agents/governance/log.txt\n")


@pytest.mark.parametrize(
    "text",
    [
        'OUT_DIR=".agents/governance"\n',
        'export OUT_DIR=".agents/governance"\n',
        '$env:OUT_DIR = ".agents/governance"\n',
    ],
)
def test_shell_and_powershell_assignment_into_keep_subtree_rejected(text: str) -> None:
    assert checker.scan_text("scripts/example.ps1", text)


def test_write_into_bare_agents_root_rejected() -> None:
    assert checker.scan_text("docs/example.md", "Save the output under `.agents`.\n")


def test_write_into_keep_top_level_file_rejected() -> None:
    text = "Save updates to `.agents/AGENT-INSTRUCTIONS.md`.\n"
    assert checker.scan_text("docs/example.md", text)


# ---------------------------------------------------------------------------
# scan_text: reads pass.
# ---------------------------------------------------------------------------


def test_read_only_keep_reference_accepted() -> None:
    text = "Read `.agents/governance/foo.md` before testing.\n"
    assert checker.scan_text("docs/example.md", text) == []


def test_keep_top_level_file_read_accepted() -> None:
    text = "Read `.agents/HANDOFF.md` for the current state.\n"
    assert checker.scan_text("docs/example.md", text) == []


@pytest.mark.parametrize(
    "text",
    [
        'ignores:\n  - ".agents/**"\n',
        "Match `.agents/*` and `.agents/{a,b}/` globs.\n",
        "Paths of the `.agents/`-class fail at runtime.\n",
        "The regex `.agents/episodes[^/]` rejects siblings.\n",
    ],
)
def test_glob_regex_and_prose_segments_are_not_paths(text: str) -> None:
    assert checker.scan_text("docs/example.md", text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Write the handoff to `.project-toolkit/sessions/h.md` from `.agents/templates/H.md`.\n",
        "Emit a JSON block matching the schema at `.agents/schemas/out.json`.\n",
        "Write one by hand against `.agents/schemas/session-log.schema.json`.\n",
        "It cites the output schema under `.agents/schemas/`.\n",
    ],
)
def test_write_verb_governing_another_object_is_not_a_write(text: str) -> None:
    assert checker.scan_text("docs/example.md", text) == []


def test_write_verb_far_from_path_is_not_a_write() -> None:
    text = "Save nothing here; the long explanation that follows cites `.agents/governance/x.md`.\n"
    assert checker.scan_text("docs/example.md", text) == []


def test_eval_scenario_data_is_not_scanned(tmp_path: Path) -> None:
    repo = _init_repo(
        tmp_path, {"tests/evals/scenario.json": '{"input": "consumer `.agents/tools` dir"}\n'}
    )
    findings, examined = checker.check_repository(repo)
    assert (findings, examined) == ([], 0)


# ---------------------------------------------------------------------------
# scan_text: opt-out marker.
# ---------------------------------------------------------------------------


def test_opt_out_with_reason_suppresses_finding() -> None:
    text = (
        "See `.agents/sessions/x.json`. "
        "agents-write-target: historical -- incident evidence\n"
    )
    assert checker.scan_text("docs/example.md", text) == []


def test_opt_out_without_reason_is_itself_a_finding() -> None:
    text = "See `.agents/sessions/x.json`. agents-write-target: historical\n"
    findings = checker.scan_text("docs/example.md", text)
    assert findings
    assert findings[0].reason == checker._MARKER_MISSING_REASON


# ---------------------------------------------------------------------------
# scan_python.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "from pathlib import Path\n(Path('.agents') / 'governance').mkdir()\n",
        "from pathlib import Path\nopen(Path('.agents') / 'governance' / 'x', 'w')\n",
        "import os\nos.makedirs('.agents/governance')\n",
        "import shutil\nshutil.copy('x', '.agents/governance/x')\n",
    ],
)
def test_python_write_into_keep_subtree_rejected(source: str) -> None:
    findings = checker.scan_python("scripts/example.py", source)
    assert findings
    assert all(f.reason == checker._PYTHON_WRITE_REASON for f in findings)


def test_python_var_then_mkdir_rejected() -> None:
    source = "from pathlib import Path\nd = Path('.agents') / 'governance'\nd.mkdir()\n"
    findings = checker.scan_python("scripts/example.py", source)
    assert len(findings) == 1
    assert findings[0].reason == checker._PYTHON_WRITE_REASON


@pytest.mark.parametrize(
    "source",
    [
        "from pathlib import Path\nx = Path('.agents') / 'sessions'\n",
        "import os\ny = os.path.join('base', '.agents', 'sessions')\n",
        "z = ('.agents', 'sessions')\n",
    ],
)
def test_python_stale_join_form_rejected(source: str) -> None:
    findings = checker.scan_python("scripts/example.py", source)
    assert findings
    assert all(f.reason == checker._STALE_REASON for f in findings)


def test_python_read_of_keep_subtree_passes() -> None:
    source = "open('.agents/governance/x', 'r')\n"
    assert checker.scan_python("scripts/example.py", source) == []


def test_python_read_reassigned_variable_is_not_tracked() -> None:
    """A name assigned more than once is not a 'simple local variable'."""
    source = (
        "from pathlib import Path\n"
        "d = Path('.agents') / 'governance'\n"
        "d = Path('other')\n"
        "d.mkdir()\n"
    )
    assert checker.scan_python("scripts/example.py", source) == []


# ---------------------------------------------------------------------------
# check_repository: git-index-based scan (not the working tree).
# ---------------------------------------------------------------------------


def test_scan_reads_staged_index_not_working_tree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, {"docs/a.md": "Save to `.agents/governance/x`.\n"})
    (repo / "docs" / "a.md").write_text("Read `.agents/governance/x`.\n", encoding="utf-8")
    findings, examined = checker.check_repository(repo)
    assert examined == 1
    assert findings and findings[0].reason == checker._TEXT_WRITE_REASON


def test_findings_are_located_and_sorted(tmp_path: Path) -> None:
    repo = _init_repo(
        tmp_path,
        {
            "docs/b.md": "Save to `.agents/governance/b`.\n",
            "docs/a.md": "Save to `.agents/governance/a`.\n",
        },
    )
    findings, examined = checker.check_repository(repo)
    assert examined == 2
    assert [(item.path, item.line) for item in findings] == [("docs/a.md", 1), ("docs/b.md", 1)]


def test_self_test_file_is_never_scanned(tmp_path: Path) -> None:
    repo = _init_repo(
        tmp_path,
        {checker._SELF_TEST: "Save to `.agents/governance/x`.\n"},
    )
    findings, examined = checker.check_repository(repo)
    assert examined == 0
    assert findings == []


def test_tests_directory_is_scanned_by_default(tmp_path: Path) -> None:
    repo = _init_repo(
        tmp_path,
        {"tests/other/test_thing.py": "open('.agents/governance/x', 'w')\n"},
    )
    findings, examined = checker.check_repository(repo)
    assert examined == 1
    assert findings


def test_repo_root_markdown_file_is_scanned(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, {"README.md": "Save to `.agents/governance/x`.\n"})
    findings, examined = checker.check_repository(repo)
    assert examined == 1
    assert findings


def test_unscoped_root_is_not_scanned(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, {"vendor/lib.py": "open('.agents/governance/x', 'w')\n"})
    _findings, examined = checker.check_repository(repo)
    assert examined == 0


# ---------------------------------------------------------------------------
# CLI / fail-closed behavior.
# ---------------------------------------------------------------------------


def test_main_returns_two_outside_git_repo(tmp_path: Path) -> None:
    assert checker.main(["--repo-root", str(tmp_path)]) == 2


def test_main_exits_two_on_git_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".git").mkdir()

    def fail(_root: Path) -> list[str]:
        raise RuntimeError("git ls-files failed")

    monkeypatch.setattr(checker, "_tracked_files", fail)
    assert checker.main(["--repo-root", str(tmp_path)]) == 2


def test_validator_fails_closed_on_inventory_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail(_root: Path) -> list[str]:
        raise RuntimeError("inventory failed")

    monkeypatch.setattr(checker, "_tracked_files", fail)
    assert checker.validate_agents_write_targets(tmp_path) is False


def test_main_returns_zero_on_clean_repo(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, {"docs/a.md": "Read `.agents/governance/x`.\n"})
    assert checker.main(["--repo-root", str(repo)]) == 0


def test_blob_read_failure_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, {"docs/a.md": "Read `.agents/governance/x.md`.\n"})
    real_git = checker._git

    def fail_cat_file(root: Path, args: list[str], stdin: bytes | None = None) -> bytes:
        if args[0] == "cat-file":
            raise RuntimeError("git cat-file failed: boom")
        return real_git(root, args, stdin)

    monkeypatch.setattr(checker, "_git", fail_cat_file)
    assert checker.validate_agents_write_targets(repo) is False


def test_symlink_entries_are_not_read(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, {"docs/a.md": "Read `.agents/governance/x.md`.\n"})
    (repo / "docs" / "link.md").symlink_to("a.md")
    subprocess.run(["git", "add", "docs/link.md"], cwd=repo, check=True)
    _findings, examined = checker.check_repository(repo)
    assert examined == 1


def test_python_stale_string_literal_rejected() -> None:
    findings = checker.scan_python("scripts/x.py", 'LOG = ".agents/sessions/x.json"\n')
    assert [f.reason for f in findings] == [checker._STALE_REASON]


def test_python_stale_literal_with_marker_reason_accepted() -> None:
    source = 'OLD = ".agents/sessions/x.json"  # agents-write-target: historical -- pre-move\n'
    assert checker.scan_python("scripts/x.py", source) == []


def test_python_marker_without_reason_is_a_finding() -> None:
    source = 'OLD = ".agents/sessions/x.json"  # agents-write-target: historical\n'
    findings = checker.scan_python("scripts/x.py", source)
    assert [f.reason for f in findings] == [checker._MARKER_MISSING_REASON]


def test_python_marker_suppresses_ast_write_finding() -> None:
    source = (
        "import os\n"
        "os.makedirs('.agents/governance')  # agents-write-target: historical -- scaffold\n"
    )
    assert checker.scan_python("scripts/x.py", source) == []


def test_python_join_and_literal_on_one_line_report_once() -> None:
    source = "from pathlib import Path\nP = Path('.agents') / 'sessions'  # .agents/sessions\n"
    findings = checker.scan_python("scripts/x.py", source)
    assert len(findings) == 1


def test_python_literal_under_tests_is_fixture_data() -> None:
    assert checker.scan_python("tests/x.py", 'OLD = ".agents/sessions/x.json"\n') == []
