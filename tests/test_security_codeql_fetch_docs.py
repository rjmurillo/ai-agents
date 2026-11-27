"""Execute the documented PR alert reader from a fork checkout."""

from __future__ import annotations

import json
import os
import re
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
    launcher.write_text(
        "import json, sys\nprint(json.dumps({'argv': sys.argv[1:], 'files': sys.stdin.read()}))\n",
        encoding="utf-8",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "launcher")
    _git(root, "remote", "add", "origin", "https://github.com/alice/ai-agents.git")
    _git(root, "remote", "add", "upstream", "https://github.com/rjmurillo/ai-agents.git")
    if detached:
        _git(root, "checkout", "--detach")
    if dirty:
        (root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    env = {
        **os.environ,
        "GH_REPO": "another/repository",
        "base_owner": "rjmurillo",
        "base_repo": "ai-agents",
        "pull_request": "42",
        "review_base_ref": "main",
    }

    result = _execute_block(root, relative, env)

    assert result.returncode == 0, result.stderr
    captured = json.loads(result.stdout)
    argv = captured["argv"]
    assert argv[0] == "skills/github/scripts/pr/get_pr_code_scanning_alerts.py"
    assert argv[argv.index("--owner") + 1] == "rjmurillo"
    assert argv[argv.index("--repo") + 1] == "ai-agents"
    assert argv[argv.index("--pull-request") + 1] == "42"
    assert re.fullmatch(r"[0-9a-f]{40}", argv[argv.index("--head-sha") + 1])
    assert argv[argv.index("--tree-state") + 1] == ("dirty" if dirty else "clean")
    assert argv[argv.index("--changed-files-from") + 1] == "-"
    assert ".claude/lib/ptk_run.py" in captured["files"].splitlines()
