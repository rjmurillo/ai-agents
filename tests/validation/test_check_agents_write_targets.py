"""Regression tests for the issue #5420 .agents/ write-target gate.

``.agents/`` now holds only read-only canonical inputs (issue #5420). These
tests exercise both findings the gate produces: a stale reference to a
directory that moved to ``.project-toolkit/<sub>``, and write intent aimed at
a KEEP subtree, a KEEP top-level file, or the bare ``.agents`` root.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from concurrent.futures.process import BrokenProcessPool
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


def test_codex_marketplace_read_accepted() -> None:
    text = "Codex reads `.agents/plugins/marketplace.json` from the root.\n"
    assert checker.scan_text("scripts/validation/example.py", text) == []


def test_write_into_the_codex_marketplace_dir_still_flagged() -> None:
    text = 'echo "{}" > .agents/plugins/marketplace.json\n'
    assert checker.scan_text("scripts/a.sh", text)


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
    text = "See `.agents/sessions/x.json`. agents-write-target: historical -- incident evidence\n"
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


# ADR-119 decision 7: .agents/skills is Codex's skill directory again, and only
# the binplace install-root owners may name it.
@pytest.mark.parametrize(
    ("relative", "text", "expected"),
    [
        ("templates/platforms/binplace.yaml", "install_tree: .agents/skills\n", 0),
        ("build/scripts/binplace_manifest.py", 'ROOT = ".agents/skills"\n', 0),
        ("scripts/validation/other.py", 'ROOT = ".agents/skills"\n', 1),
        ("docs/guide.md", "Edit `.agents/skills/foo`.\n", 1),
        ("templates/platforms/binplace.yaml", "install_tree: .agents/context\n", 1),
        ("templates/platforms/binplace.yaml", "install_tree: .agents/skills/foo\n", 1),
    ],
)
def test_codex_skills_root_is_nameable_only_by_its_owners(
    tmp_path: Path, relative: str, text: str, expected: int
) -> None:
    repo = _init_repo(tmp_path, {relative: text})

    findings, examined = checker.check_repository(repo)

    assert examined == 1
    assert len(findings) == expected


# ---------------------------------------------------------------------------
# Issue #6734: scan_python skips its walks when no finding is possible, and
# check_repository fans the scan out to worker processes. Both must return
# exactly what the single-process, unfiltered scan returned.
# ---------------------------------------------------------------------------


def _reference_scan_python(path: str, text: str) -> list[checker.Finding]:
    """The scan_python body from before the prefilter: parse, walk, and scan every file."""
    tree = ast.parse(text, filename=path)
    variables = checker._single_assigned_paths(tree)
    visitor = checker._PythonAgentsScan(path, variables)
    visitor.visit(tree)
    lines = text.splitlines()
    unique = {(item.line, item.reason): item for item in visitor.findings}
    literal_findings = (
        [] if path.startswith(checker._TEST_PREFIX) else checker._stale_line_findings(path, lines)
    )
    for item in literal_findings:
        unique.setdefault((item.line, item.reason), item)
    return [item for item in unique.values() if not checker._line_opted_out(lines, item.line)]


_IMPORT = "from pathlib import Path\n"

# Each source names a stale or written .agents path without the substring ".agents".
_HIDDEN_AGENTS_SOURCES = [
    pytest.param(_IMPORT + 'Path("\\x2eagents/sessions/x")\n', id="hex-escape"),
    pytest.param(_IMPORT + 'Path("\\u002eagents/sessions/x")\n', id="u-escape"),
    pytest.param(_IMPORT + 'Path("\\U0000002eagents/sessions/x")\n', id="big-u-escape"),
    pytest.param(_IMPORT + 'Path("\\N{FULL STOP}agents/sessions/x")\n', id="named-escape"),
    pytest.param(_IMPORT + 'Path("\\056agents/sessions/x")\n', id="octal-escape"),
    pytest.param(_IMPORT + 'Path("\\x2eagent\\x73/sessions/x")\n', id="two-escapes"),
    pytest.param(_IMPORT + 'Path(".age" "nts/sessions/x")\n', id="implicit-concat"),
    pytest.param(
        _IMPORT + 'Path(\n    ".a"  # why\n    "gents"\n    "/sessions/x"\n)\n',
        id="concat-with-comment",
    ),
    pytest.param(_IMPORT + 'Path(r".age" u"nts/sessions/x")\n', id="concat-with-prefixes"),
    pytest.param(_IMPORT + 'Path(".age\\\nnts/sessions/x")\n', id="line-continuation"),
    pytest.param(_IMPORT + 'Path(""".""" "agents/sessions/x")\n', id="triple-quote-concat"),
    pytest.param(
        _IMPORT + 'Path("\\x2eagents/governance/x").write_text("a")\n', id="hidden-keep-write"
    ),
]


@pytest.mark.parametrize("source", _HIDDEN_AGENTS_SOURCES)
def test_hidden_agents_spelling_still_gets_the_full_scan(source: str) -> None:
    """A bare '.agents' substring skip would return [] here and miss the finding."""
    assert ".agents" not in source
    assert checker._may_name_agents(source)
    findings = checker.scan_python("scripts/example.py", source)
    assert findings
    assert findings == _reference_scan_python("scripts/example.py", source)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("x = 1\n", id="plain"),
        pytest.param('GREEN = "\\x1b[32m"\nPATTERN = r"\\d+\\s*"\n', id="other-escapes"),
        pytest.param('"""Prose, e.g.\nagents write here."""\nx = 1\n', id="prose-across-lines"),
        pytest.param('self.assert_called()\nitems = [".a", "b"]\n', id="near-miss"),
        pytest.param('NAME = "agents"\nDIR = "."\n', id="pieces-in-separate-statements"),
    ],
)
def test_source_without_any_agents_spelling_skips_the_walks(source: str) -> None:
    assert not checker._may_name_agents(source)
    assert checker.scan_python("scripts/example.py", source) == []
    assert _reference_scan_python("scripts/example.py", source) == []


def test_syntax_error_without_agents_text_still_fails_the_scan() -> None:
    """The skip must not drop the parse: a broken file failed before and still must."""
    source = "def broken(:\n    pass\n"
    assert not checker._may_name_agents(source)
    with pytest.raises(SyntaxError):
        checker.scan_python("scripts/broken.py", source)
    with pytest.raises(SyntaxError):
        _reference_scan_python("scripts/broken.py", source)


def test_marker_text_without_agents_substring_is_still_scanned() -> None:
    source = "x = 1  # agents-write-target: historical\n"
    assert checker._may_name_agents(source)
    findings = checker.scan_python("scripts/example.py", source)
    assert [f.reason for f in findings] == [checker._MARKER_MISSING_REASON]
    assert findings == _reference_scan_python("scripts/example.py", source)


def test_prefilter_matches_the_unfiltered_scan_on_real_sources() -> None:
    root = Path(__file__).resolve().parents[2]
    paths = sorted((root / "scripts" / "validation").glob("*.py")) + sorted(
        (root / "tests" / "validation").glob("*.py")
    )
    scanned = 0
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if relative in (checker._SELF_TEST, checker._SELF_SOURCE):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert checker.scan_python(relative, text) == _reference_scan_python(relative, text), (
            relative
        )
        scanned += 1
    assert scanned > 50


_MIXED_CORPUS = {
    "scripts/a_stale.py": _IMPORT + 'Path(".agents/sessions/x")\n',
    "scripts/b_clean.py": "x = 1\n",
    "scripts/c_hidden.py": _IMPORT + 'Path("\\x2eagents/sessions/x")\n',
    "scripts/d_write.py": _IMPORT + 'Path(".agents/governance/x").write_text("a")\n',
    "docs/e.md": "Save to `.agents/governance/x`.\n",
    "docs/f.md": "Nothing here.\n",
    "tests/g_test.py": "open('.agents/governance/x', 'w')\n",
    "scripts/h_clean.py": "y = 2\n",
}


def _items(corpus: dict[str, str]) -> list[tuple[str, str]]:
    return list(corpus.items())


def test_parallel_scan_returns_the_serial_findings() -> None:
    items = _items(_MIXED_CORPUS)
    serial = checker._scan_candidates(items)
    assert len(serial) == 5
    assert checker._scan_parallel(items, 2) == serial


def test_check_repository_uses_the_pool_for_large_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _init_repo(tmp_path, _MIXED_CORPUS)
    expected, examined = checker.check_repository(repo)
    monkeypatch.setattr(checker, "_PARALLEL_MIN_BYTES", 0)
    monkeypatch.setattr(checker.os, "process_cpu_count", lambda: 4)
    calls: list[int] = []
    real = checker._scan_parallel

    def spy(items: list[tuple[str, str]], workers: int) -> list[checker.Finding]:
        calls.append(workers)
        return real(items, workers)

    monkeypatch.setattr(checker, "_scan_parallel", spy)

    assert checker.check_repository(repo) == (expected, examined)
    assert calls == [4]
    assert len(expected) == 5


def test_check_repository_stays_in_process_for_small_input_or_one_cpu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _init_repo(tmp_path, _MIXED_CORPUS)

    def boom(_items: list[tuple[str, str]], _workers: int) -> list[checker.Finding]:
        raise AssertionError("pool must not start")

    monkeypatch.setattr(checker, "_scan_parallel", boom)
    assert len(checker.check_repository(repo)[0]) == 5  # below the byte threshold
    monkeypatch.setattr(checker, "_PARALLEL_MIN_BYTES", 0)
    monkeypatch.setattr(checker.os, "process_cpu_count", lambda: 1)
    assert len(checker.check_repository(repo)[0]) == 5  # one CPU


def test_parallel_scan_raises_the_first_syntax_error_in_input_order() -> None:
    items = [
        ("scripts/a_ok.py", "x = 1\n"),
        ("scripts/b_bad.py", "def first(:\n"),
        ("scripts/c_ok.py", "y = 2\n"),
        ("scripts/d_bad.py", "def second(:\n"),
    ]
    with pytest.raises(SyntaxError) as serial:
        checker._scan_candidates(items)
    with pytest.raises(SyntaxError) as parallel:
        checker._scan_parallel(items, 4)
    assert "b_bad.py" in str(parallel.value)
    assert str(parallel.value) == str(serial.value)


def test_syntax_error_in_pool_fails_the_validator_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _init_repo(tmp_path, {**_MIXED_CORPUS, "scripts/z_bad.py": "def broken(:\n"})
    monkeypatch.setattr(checker, "_PARALLEL_MIN_BYTES", 0)
    monkeypatch.setattr(checker.os, "process_cpu_count", lambda: 2)
    assert checker.validate_agents_write_targets(repo) is False
    assert checker.main(["--repo-root", str(repo)]) == 2


def test_broken_pool_falls_back_to_the_serial_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    items = _items(_MIXED_CORPUS)

    class DeadPool:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise BrokenProcessPool("pool died")

    monkeypatch.setattr(checker, "ProcessPoolExecutor", DeadPool)
    assert checker._scan_parallel(items, 2) == checker._scan_candidates(items)


def test_missing_forkserver_falls_back_to_the_serial_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_context(_method: str) -> None:
        raise ValueError("cannot find context for 'forkserver'")

    monkeypatch.setattr(checker.multiprocessing, "get_context", no_context)
    items = _items(_MIXED_CORPUS)
    assert checker._scan_parallel(items, 2) == checker._scan_candidates(items)


@pytest.mark.parametrize("count", [1, 2, 3, 8, 32])
def test_batches_keep_input_order_and_cover_every_item(count: int) -> None:
    items = [(f"scripts/f{i}.py", "x" * (i * 7 % 50)) for i in range(20)]
    batches = checker._batches(items, count)
    assert 1 <= len(batches) <= count
    assert [item for batch in batches for item in batch] == items
    assert all(batches)


def test_batches_of_empty_input_is_one_empty_batch() -> None:
    assert checker._batches([], 4) == [[]]


def test_deep_chain_without_agents_text_no_longer_crashes_the_visitor() -> None:
    """The one input class whose outcome changes: the old visitor hit RecursionError.

    A 400-term ``"a" + "a" + ...`` chain parses fine but nests past the visitor's
    recursion budget, so the unfiltered scan crashed the gate on a file that cannot
    hold a finding. The skip returns the verdict the file deserves: no findings.
    """
    source = "x = " + " + ".join(['"a"'] * 400) + "\n"
    assert not checker._may_name_agents(source)
    with pytest.raises(RecursionError):
        _reference_scan_python("scripts/deep.py", source)
    assert checker.scan_python("scripts/deep.py", source) == []
