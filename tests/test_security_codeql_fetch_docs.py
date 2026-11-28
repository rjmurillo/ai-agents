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
    assert ".claude/lib/ptk_run.py" in captured["files"].splitlines()


def _scan_env(tmp_path: Path) -> dict[str, str]:
    plugin = tmp_path / "installed-plugin"
    launcher = plugin / "lib/ptk_run.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text(
        "import json, sys\n"
        "print(json.dumps({'launcher': __file__, 'argv': sys.argv[1:], "
        "'files': sys.stdin.read()}))\n",
        encoding="utf-8",
    )
    target = plugin / "skills/github/scripts/pr/get_pr_code_scanning_alerts.py"
    target.parent.mkdir(parents=True)
    target.write_text("# Reader marker.\n", encoding="utf-8")
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
    }


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
