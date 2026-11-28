"""Execute the documented PR alert reader from a fork checkout."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import _git, _repo

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ".agents/governance/SECURITY-REVIEW-PROTOCOL.md",
    ".project-toolkit/security/benchmarks/README.md",
)


def _codeql_block(relative: str) -> str:
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    match = re.search(r"```bash\n(?P<body>[^`]*get_pr_code_scanning_alerts.py[^`]*)```", text)
    assert match is not None, f"{relative} has no CodeQL fetch block"
    return match.group("body")


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_codeql_fetch_uses_github_skill_and_explicit_pr_base(relative: str) -> None:
    block = _codeql_block(relative)

    assert "skills/github/scripts/pr/get_pr_code_scanning_alerts.py" in block
    assert '--owner "$base_owner" --repo "$base_repo"' in block
    assert "get_repo_info" not in block
    assert "gh api" not in block


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_codeql_fetch_documents_freshness_not_just_exit_zero(relative: str) -> None:
    block = _codeql_block(relative)

    assert '--head-sha "$head_sha" --tree-state "$tree_state"' in block
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    for outcome in ("CURRENT", "STALE", "NOT ANALYZED", "SKIPPED"):
        assert f"`{outcome}`" in text
    assert "Exit 0 alone is not a clean scan" in text


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_codeql_fetch_blocks_missing_base_parameters(relative: str, tmp_path: Path) -> None:
    root = _repo(tmp_path)
    env = os.environ.copy()
    for name in ("base_owner", "base_repo", "pull_request", "review_base_ref"):
        env.pop(name, None)
    result = _execute_block(root, relative, env)

    assert result.returncode == 2
    assert "Set base_owner" in result.stderr
    assert result.stdout == ""


def _execute_block(
    root: Path, relative: str, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _codeql_block(relative)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("relative", DOCUMENTS)
@pytest.mark.parametrize("detached", [False, True], ids=["branch", "detached"])
@pytest.mark.parametrize("dirty", [False, True], ids=["clean", "dirty"])
def test_codeql_fetch_passes_upstream_scope_from_fork_checkout(
    relative: str, tmp_path: Path, detached: bool, dirty: bool
) -> None:
    root = _repo(tmp_path)
    launcher = root / ".claude/lib/ptk_run.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("# Checkout marker, not a launcher.\n", encoding="utf-8")
    source_files = ("src/café.py", "src/日本語.py")
    (root / "src").mkdir()
    for name in source_files:
        (root / name).write_text("# Source file.\n", encoding="utf-8")
    _git(root, "config", "core.quotePath", "true")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "launcher")
    _git(root, "remote", "add", "origin", "https://github.com/alice/ai-agents.git")
    _git(root, "remote", "add", "upstream", "https://github.com/rjmurillo/ai-agents.git")
    if detached:
        _git(root, "checkout", "--detach")
    _git(root, "config", "status.showUntrackedFiles", "no")
    if dirty:
        (root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    env = _scan_env(tmp_path)
    env["GH_REPO"] = "another/repository"

    result = _execute_block(root, relative, env)

    assert result.returncode == 0, result.stderr
    captured = json.loads(result.stdout)
    assert captured["launcher"] == str(tmp_path / "installed-plugin/lib/ptk_run.py")
    argv = captured["argv"]
    assert argv[0] == "skills/github/scripts/pr/get_pr_code_scanning_alerts.py"
    assert argv[argv.index("--owner") + 1] == "rjmurillo"
    assert argv[argv.index("--repo") + 1] == "ai-agents"
    assert argv[argv.index("--pull-request") + 1] == "42"
    assert re.fullmatch(r"[0-9a-f]{40}", argv[argv.index("--head-sha") + 1])
    assert argv[argv.index("--tree-state") + 1] == ("dirty" if dirty else "clean")
    assert argv[argv.index("--changed-files-from") + 1] == "-"
    expected = {".claude/lib/ptk_run.py", *source_files}
    if dirty:
        expected.add("untracked.txt")
    assert set(captured["files"].splitlines()) == expected


def _scan_env(tmp_path: Path) -> dict[str, str]:
    plugin = tmp_path / "installed-plugin"
    launcher = plugin / "lib/ptk_run.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text(
        "import json, os, sys\n"
        "if sys.argv[1].endswith('get_pr_context.py'):\n"
        "    print(json.dumps({'Success': True, "
        "'Data': {'base_sha': os.environ['FAKE_PR_BASE_SHA']}}))\n"
        "    sys.exit(0)\n"
        "print(json.dumps({'launcher': __file__, 'argv': sys.argv[1:], "
        "'files': sys.stdin.read()}))\n",
        encoding="utf-8",
    )
    for script in ("get_pr_code_scanning_alerts.py", "get_pr_context.py"):
        target = plugin / "skills/github/scripts/pr" / script
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Reader marker.\n", encoding="utf-8")
    normalizer = Path("skills/github/scripts/pr/code_scanning_sarif.py")
    shutil.copyfile(REPO_ROOT / "src/claude" / normalizer, plugin / normalizer)
    guard = Path("skills/review/scripts/codeql_scanner_guard.py")
    (plugin / guard).parent.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "src/claude" / guard, plugin / guard)
    return {
        **os.environ,
        "CLAUDE_PLUGIN_ROOT": str(plugin),
        "COPILOT_PLUGIN_ROOT": "",
        "base_owner": "rjmurillo",
        "base_repo": "ai-agents",
        "pull_request": "42",
        "review_base_ref": "main",
        "FAKE_PR_BASE_SHA": _sha(tmp_path / "repo", "main"),
    }


def _sha(root: Path, ref: str) -> str:
    """Resolve ``ref`` in ``root``; empty when the repository does not exist yet."""
    if not root.is_dir():
        return ""
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", ref],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    return result.stdout.strip()


@pytest.mark.parametrize("relative", DOCUMENTS)
@pytest.mark.parametrize("base_ref", ["--help", "missing-ref"])
def test_codeql_fetch_rejects_invalid_base_ref(
    relative: str, tmp_path: Path, base_ref: str
) -> None:
    root = _repo(tmp_path)
    env = _scan_env(tmp_path)
    env["review_base_ref"] = base_ref

    result = _execute_block(root, relative, env)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr


@pytest.mark.parametrize("relative", DOCUMENTS)
@pytest.mark.parametrize("location", ["missing", "checkout"])
def test_codeql_fetch_requires_trusted_installation(
    relative: str, tmp_path: Path, location: str
) -> None:
    root = _repo(tmp_path)
    env = _scan_env(tmp_path)
    if location == "checkout":
        plugin = root / ".claude"
        shutil.copytree(env["CLAUDE_PLUGIN_ROOT"], plugin)
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin)
    else:
        env["CLAUDE_PLUGIN_ROOT"] = ""

    result = _execute_block(root, relative, env)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "SKIPPED (trusted plugin installation unavailable)" in result.stderr


@pytest.mark.parametrize("relative", DOCUMENTS)
@pytest.mark.parametrize("change", ["committed", "staged", "untracked"])
def test_codeql_fetch_skips_modified_scanner_inputs(
    relative: str, tmp_path: Path, change: str
) -> None:
    root = _repo(tmp_path)
    env = _scan_env(tmp_path)
    scanner_input = root / ".github/workflows/example.yml"
    scanner_input.parent.mkdir(parents=True)
    scanner_input.write_text("# Documentation fixture.\n", encoding="utf-8")
    _git(root, "config", "status.showUntrackedFiles", "no")
    if change in ("committed", "staged"):
        _git(root, "add", "-A")
    if change == "committed":
        _git(root, "commit", "-qm", "scanner config")

    result = _execute_block(root, relative, env)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "SKIPPED (scanner inputs modified)" in result.stderr


def _tree_state(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stderr
    argv = json.loads(result.stdout)["argv"]
    return str(argv[argv.index("--tree-state") + 1])


def _commit_file(root: Path, name: str, text: str = "content\n") -> None:
    (root / name).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", f"add {name}")


@pytest.mark.parametrize("relative", DOCUMENTS)
@pytest.mark.parametrize("present", [False, True], ids=["absent", "present"])
def test_codeql_fetch_reports_ignored_files_as_dirty(
    relative: str, tmp_path: Path, present: bool
) -> None:
    root = _repo(tmp_path)
    (root / ".git/info/exclude").write_text("ignored.txt\n", encoding="utf-8")
    if present:
        (root / "ignored.txt").write_text("hidden\n", encoding="utf-8")

    result = _execute_block(root, relative, _scan_env(tmp_path))

    assert _tree_state(result) == ("dirty" if present else "clean")


@pytest.mark.parametrize("relative", DOCUMENTS)
@pytest.mark.parametrize("flag", ["skip-worktree", "assume-unchanged"])
@pytest.mark.parametrize("modified", [False, True], ids=["unmodified", "modified"])
def test_codeql_fetch_refuses_clean_for_hidden_index_entries(
    relative: str, tmp_path: Path, flag: str, modified: bool
) -> None:
    root = _repo(tmp_path)
    _commit_file(root, "tracked.txt")
    _git(root, "update-index", f"--{flag}", "tracked.txt")
    if modified:
        (root / "tracked.txt").write_text("changed behind git status\n", encoding="utf-8")

    result = _execute_block(root, relative, _scan_env(tmp_path))

    assert _tree_state(result) == "dirty"


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_codeql_fetch_reports_a_plain_checkout_as_clean(relative: str, tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_file(root, "tracked.txt")
    _git(root, "update-index", "--no-skip-worktree", "tracked.txt")

    result = _execute_block(root, relative, _scan_env(tmp_path))

    assert _tree_state(result) == "clean"


@pytest.mark.parametrize("relative", DOCUMENTS)
@pytest.mark.parametrize("modified", [False, True], ids=["unmodified", "modified"])
def test_codeql_fetch_sees_submodule_changes_hidden_by_ignore_all(
    relative: str, tmp_path: Path, modified: bool
) -> None:
    root = _repo(tmp_path)
    inner = tmp_path / "inner"
    inner.mkdir()
    _git(inner, "init", "-q", "-b", "main")
    _git(inner, "config", "user.email", "test@example.com")
    _git(inner, "config", "user.name", "Test")
    _commit_file(inner, "lib.txt")
    _git(root, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "sub")
    _git(root, "config", "-f", ".gitmodules", "submodule.sub.ignore", "all")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "add submodule")
    if modified:
        (root / "sub/lib.txt").write_text("changed inside submodule\n", encoding="utf-8")

    result = _execute_block(root, relative, _scan_env(tmp_path))

    assert _tree_state(result) == ("dirty" if modified else "clean")


def _feature_commit(root: Path) -> None:
    _commit_file(root, "feature.txt")


def _advance_main(root: Path) -> None:
    _git(root, "checkout", "-q", "main")
    _commit_file(root, "main-only.txt")
    _git(root, "checkout", "-q", "feature")


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_codeql_fetch_accepts_a_branch_that_merged_a_newer_base(
    relative: str, tmp_path: Path
) -> None:
    root = _repo(tmp_path)
    pr_base = _sha(root, "main")
    _feature_commit(root)
    _advance_main(root)
    _git(root, "merge", "-q", "--no-edit", "main")
    env = _scan_env(tmp_path)
    env["FAKE_PR_BASE_SHA"] = pr_base

    result = _execute_block(root, relative, env)

    assert result.returncode == 0, result.stderr
    assert set(json.loads(result.stdout)["files"].splitlines()) == {"feature.txt"}


@pytest.mark.parametrize("relative", DOCUMENTS)
@pytest.mark.parametrize("ref", ["feature", "ahead"])
def test_codeql_fetch_refuses_a_base_ref_that_contains_head(
    relative: str, tmp_path: Path, ref: str
) -> None:
    root = _repo(tmp_path)
    pr_base = _sha(root, "main")
    _feature_commit(root)
    _git(root, "branch", "ahead")
    _git(root, "checkout", "-q", "ahead")
    _commit_file(root, "ahead.txt")
    _git(root, "checkout", "-q", "feature")
    env = _scan_env(tmp_path)
    env["FAKE_PR_BASE_SHA"] = pr_base
    env["review_base_ref"] = ref

    result = _execute_block(root, relative, env)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "SKIPPED (review base already contains HEAD)" in result.stderr


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_codeql_fetch_refuses_a_base_ref_older_than_the_pr_base(
    relative: str, tmp_path: Path
) -> None:
    root = _repo(tmp_path)
    _feature_commit(root)
    pr_base = _sha(root, "HEAD")
    _commit_file(root, "second.txt")
    env = _scan_env(tmp_path)
    env["FAKE_PR_BASE_SHA"] = pr_base

    result = _execute_block(root, relative, env)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "SKIPPED (review base does not descend from the PR base)" in result.stderr


@pytest.mark.parametrize("relative", DOCUMENTS)
@pytest.mark.parametrize("reported", ["", "not-a-sha", "0" * 40])
def test_codeql_fetch_refuses_an_unusable_pr_base(
    relative: str, tmp_path: Path, reported: str
) -> None:
    root = _repo(tmp_path)
    env = _scan_env(tmp_path)
    env["FAKE_PR_BASE_SHA"] = reported

    result = _execute_block(root, relative, env)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "SKIPPED (" in result.stderr
