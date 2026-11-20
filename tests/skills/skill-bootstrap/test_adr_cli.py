"""Tests for bootstrap_adr.py as a command line: exit codes, --out rules, offline, plugin roots.

Ports the command-level cases of align-cli tests/adr-command.test.ts (MIT, Copyright (c) 2026
Align Tech Ltd, see LICENSE-align): the list step writes nothing, and a write needs an explicit
accept. The CLI contract itself (exit codes, JSON errors, the offline guarantee, the plugin
roots) is new in this port.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import adr_git
import bootstrap_adr
import pytest
from adr_helpers import CLI, commit, git, new_repo, run_cli, write

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = REPO_ROOT / "src" / "claude" / "skills" / "skill-bootstrap"
WHY = "Because the team already runs it in production and needs one fewer system."


def _decision_repo(tmp_path: Path) -> Path:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    commit(repo, f"Adopt Postgres instead of MySQL\n\n{WHY}\n")
    return repo


def _scan(repo: Path, tmp_path: Path, name: str = "scan.json") -> tuple[int, dict[str, Any]]:
    return run_cli("scan", "--repo", str(repo), "--out", str(tmp_path / name))


def test_locate_prints_json_and_exits_zero(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    code, payload = run_cli("locate", "--repo", str(repo), cwd=tmp_path)
    assert code == 0
    assert payload["primary"] == "docs/adr" and payload["next_number"] == 2
    assert payload["examined"] == 1 and payload["folders"][0]["prefix"] == ""


@pytest.mark.parametrize("command", ["locate", "scan"])
def test_a_path_that_is_not_a_repository_exits_two(tmp_path: Path, command: str) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    args = [command, "--repo", str(plain)] + (
        ["--out", str(tmp_path / "o.json")] if command == "scan" else []
    )
    code, payload = run_cli(*args)
    assert code == 2 and payload["error"] == "config"


def test_scan_writes_its_result_outside_the_repo_and_prints_the_path(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    before = git(repo, "status", "--porcelain", "-uall")
    code, payload = _scan(repo, tmp_path)
    assert code == 0 and payload["out"] == str((tmp_path / "scan.json").resolve())
    saved = json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))
    assert saved == {k: v for k, v in payload.items() if k != "out"}
    assert [c["title"] for c in saved["candidates"]] == ["Adopt Postgres instead of MySQL"]
    assert git(repo, "status", "--porcelain", "-uall") == before


@pytest.mark.parametrize("target", ["inside.json", "docs/adr/scan.json", "."])
def test_scan_out_inside_the_repository_exits_two_and_writes_nothing(
    tmp_path: Path, target: str
) -> None:
    repo = _decision_repo(tmp_path)
    before = git(repo, "status", "--porcelain", "-uall")
    code, payload = run_cli("scan", "--repo", str(repo), "--out", str(repo / target))
    assert (
        code == 2 and payload["error"] == "config" and "inside the repository" in payload["message"]
    )
    assert git(repo, "status", "--porcelain", "-uall") == before


def test_scan_out_through_a_symlink_into_the_repository_is_refused(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    link = tmp_path / "link"
    try:
        link.symlink_to(repo, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    code, payload = run_cli("scan", "--repo", str(repo), "--out", str(link / "scan.json"))
    assert code == 2 and not (repo / "scan.json").exists()


def test_scan_out_that_exists_or_is_a_directory_exits_two(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    write(tmp_path, "taken.json", "{}")
    code, _ = run_cli("scan", "--repo", str(repo), "--out", str(tmp_path / "taken.json"))
    assert code == 2 and (tmp_path / "taken.json").read_text(encoding="utf-8") == "{}"
    assert run_cli("scan", "--repo", str(repo), "--out", str(tmp_path))[0] == 2


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--rev", "nope"], "rev does not name a commit"),
        (["--rev=--all"], "may not start with"),
        (["--since=--all"], "--since may not start with"),
    ],
)
def test_a_bad_rev_or_since_exits_two(tmp_path: Path, args: list[str], message: str) -> None:
    repo = _decision_repo(tmp_path)
    code, payload = run_cli("scan", "--repo", str(repo), "--out", str(tmp_path / "o.json"), *args)
    assert code == 2 and message in payload["message"] and not (tmp_path / "o.json").exists()


@pytest.mark.parametrize("flag", ["0", "-1", "many"])
def test_max_commits_must_be_a_positive_integer(tmp_path: Path, flag: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(CLI), "scan", "--repo", str(tmp_path), "--out", "o.json"]
        + ["--max-commits", flag],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2 and "positive integer" in proc.stderr


def test_scan_reports_truncation_on_the_command_line(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    commit(repo, f"Adopt Redis instead of Memcached\n\n{WHY}\n")
    code, payload = run_cli(
        "scan", "--repo", str(repo), "--max-commits", "1", "--out", str(tmp_path / "o.json")
    )
    assert code == 0 and payload["truncated"] is True and payload["examined"]["commits"] == 1


def test_prs_json_adds_pull_request_candidates(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    pr = {
        "number": 5, "title": "Adopt Redis instead of Memcached", "body": WHY,
        "url": "https://github.com/o/r/pull/5", "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }  # fmt: skip
    prs = write(tmp_path, "prs.json", json.dumps([pr]))
    code, payload = run_cli(
        "scan", "--repo", str(repo), "--prs-json", str(prs), "--out", str(tmp_path / "o.json")
    )
    assert code == 0 and {c["id"] for c in payload["candidates"]} >= {"pr-5"}


@pytest.mark.parametrize("body", ["not json", "{}", '"x"'])
def test_a_malformed_prs_json_exits_two_and_writes_nothing(tmp_path: Path, body: str) -> None:
    repo = _decision_repo(tmp_path)
    prs = write(tmp_path, "prs.json", body)
    code, payload = run_cli(
        "scan", "--repo", str(repo), "--prs-json", str(prs), "--out", str(tmp_path / "o.json")
    )
    assert code == 2 and "--prs-json" in payload["message"] and not (tmp_path / "o.json").exists()
    code, _ = run_cli(
        "scan", "--repo", str(repo), "--prs-json", str(tmp_path / "gone.json"),
        "--out", str(tmp_path / "o.json"),
    )  # fmt: skip
    assert code == 2


def test_draft_writes_one_adr_and_prints_its_path(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    _scan(repo, tmp_path)
    scan = json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))
    ident = scan["candidates"][0]["id"]
    folder = repo / "docs" / "adr"
    code, payload = run_cli(
        "draft", "--scan", str(tmp_path / "scan.json"), "--id", ident, "--out", str(folder)
    )
    assert code == 0 and payload["number"] == 2 and payload["in_repo"] is True
    written = Path(payload["path"])
    assert written.parent == folder.resolve() and written.name.startswith("0002-adopt-postgres")
    assert "Proposed" in written.read_text(encoding="utf-8")


def test_draft_onto_an_existing_target_exits_one_and_changes_nothing(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    _scan(repo, tmp_path)
    scan = json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))
    cand = scan["candidates"][0]
    mine = write(tmp_path, "mine.txt", "mine")
    folder = repo / "docs" / "adr"
    link = folder / "0002-adopt-postgres-instead-of-mysql.md"
    try:
        link.symlink_to(mine)
    except OSError:
        pytest.skip("symlinks unavailable")
    code, payload = run_cli(
        "draft", "--scan", str(tmp_path / "scan.json"), "--id", cand["id"], "--out", str(folder)
    )
    assert code == 1 and payload["error"] == "exists"
    assert mine.read_text(encoding="utf-8") == "mine"
    assert sorted(p.name for p in folder.iterdir()) == ["0001-first.md", link.name]


def test_draft_into_an_ignored_path_exits_two(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    _scan(repo, tmp_path)
    ident = json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))["candidates"][0]["id"]
    write(repo, ".gitignore", "docs/adr/0002-*\n")
    code, payload = run_cli(
        "draft",
        "--scan",
        str(tmp_path / "scan.json"),
        "--id",
        ident,
        "--out",
        str(repo / "docs" / "adr"),
    )
    assert code == 2 and "ignored by git" in payload["message"]
    assert sorted(p.name for p in (repo / "docs" / "adr").iterdir()) == ["0001-first.md"]


@pytest.mark.parametrize("args", [["--id", "c-nope"], ["--id", "c-1", "--status", "A\nB"]])
def test_draft_with_an_unknown_id_or_a_bad_status_exits_two(
    tmp_path: Path, args: list[str]
) -> None:
    repo = _decision_repo(tmp_path)
    _scan(repo, tmp_path)
    code, payload = run_cli(
        "draft", "--scan", str(tmp_path / "scan.json"), *args, "--out", str(tmp_path / "out")
    )
    assert code == 2 and payload["error"] == "config" and not (tmp_path / "out").exists()


def test_git_missing_exits_three_with_a_git_error(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    env = {"PATH": str(tmp_path / "empty-bin"), "HOME": str(tmp_path)}
    code, payload = run_cli("locate", "--repo", str(repo), env=env)
    assert code == 3 and payload["error"] == "git"


def test_a_git_timeout_exits_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def hang(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(["git"], 30)

    monkeypatch.setattr(adr_git.subprocess, "run", hang)
    assert bootstrap_adr.main(["locate", "--repo", str(tmp_path)]) == 3
    assert json.loads(capsys.readouterr().out)["error"] == "git"


def test_a_write_failure_exits_two_with_an_io_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def broken(args: Any) -> Any:
        raise PermissionError("disk full")

    monkeypatch.setitem(bootstrap_adr._HANDLERS, "locate", broken)
    assert bootstrap_adr.main(["locate", "--repo", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "io"


def _offline_env(home: Path) -> dict[str, str]:
    keep = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
    return {**keep, "HOME": str(home), "no_proxy": "*", "NO_PROXY": "*"}


_NO_SOCKETS = """
import os, runpy, socket, sys
def boom(*args, **kwargs):
    raise OSError("network access is disabled in this test")
socket.socket = boom
socket.create_connection = boom
socket.getaddrinfo = boom
script = sys.argv[1]
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(script))
runpy.run_path(script, run_name="__main__")
"""


def test_scan_makes_no_network_call_in_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _decision_repo(tmp_path)

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("scan opened a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    argv = ["scan", "--repo", str(repo), "--out", str(tmp_path / "o.json")]
    assert bootstrap_adr.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["candidates"]


def test_scan_succeeds_as_a_subprocess_with_no_proxy_and_no_sockets(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    cmd = [
        sys.executable,
        "-c",
        _NO_SOCKETS,
        str(CLI),
        "scan",
        "--repo",
        str(repo),
        "--out",
        str(tmp_path / "o.json"),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, env=_offline_env(tmp_path), check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["candidates"]


def test_scan_succeeds_as_a_plain_subprocess_with_no_proxy(tmp_path: Path) -> None:
    repo = _decision_repo(tmp_path)
    code, payload = run_cli(
        "scan", "--repo", str(repo), "--out", str(tmp_path / "o.json"), env=_offline_env(tmp_path)
    )
    assert code == 0 and payload["candidates"]


_ALIGN_INVOCATIONS = (
    r"""\[\s*["']align["']""",
    r"""\(\s*["']align["']\s*[,)]""",
    r"""\b(?:which|where|where\.exe|type)\s+align\b""",
    r"""\bcommand\s+-v\s+align\b""",
    r"""\balign\s+(?:adr|connect|init|login|auth|setup|context|--)""",
    r"""\bnpx\s+(?:-y\s+)?(?:@[\w-]+/)?align\b""",
)


def _align_hits(text: str) -> list[str]:
    return [m.group(0) for pattern in _ALIGN_INVOCATIONS for m in re.finditer(pattern, text)]


@pytest.mark.parametrize(
    "sample",
    [
        'subprocess.run(["align", "adr"])',
        "subprocess.run(('align', 'adr'))",
        'shutil.which("align")',
        "shutil.which('align')",
        "which align",
        "command -v align",
        "align adr write",
        "npx -y align init",
        'argv = ["align"]',
    ],
)
def test_the_align_matcher_catches_an_invocation_or_a_probe(sample: str) -> None:
    assert _align_hits(sample)


@pytest.mark.parametrize(
    "sample",
    [
        "Port of aligndottech/align-cli at commit 8d758e9",
        "MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align",
        "align the columns with the heading",
        "alignment and aligned text",
        "https://github.com/aligndottech/align-cli",
    ],
)
def test_the_align_matcher_leaves_attribution_and_prose_alone(sample: str) -> None:
    assert _align_hits(sample) == []


def test_no_file_in_the_skill_invokes_or_probes_an_align_executable() -> None:
    hits: dict[str, list[str]] = {}
    for path in sorted(SKILL_ROOT.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found = _align_hits(text)
        if found:
            hits[str(path.relative_to(SKILL_ROOT))] = found
    assert hits == {}


def _mirrors() -> list[Path]:
    found = list((REPO_ROOT / "src").glob("*/skills/skill-bootstrap/scripts/bootstrap_adr.py"))
    found += (REPO_ROOT / "src" / "hermes").glob(
        "*/skills/skill-bootstrap/scripts/bootstrap_adr.py"
    )
    return sorted(found)


def test_the_cli_is_mirrored_to_every_plugin_root_including_hermes() -> None:
    names = {path.relative_to(REPO_ROOT / "src").parts[0] for path in _mirrors()}
    assert names == {"claude", "codex", "copilot-cli", "cursor", "muse", "hermes"}


@pytest.mark.parametrize(
    "script", _mirrors(), ids=lambda p: p.relative_to(REPO_ROOT / "src").parts[0]
)
def test_locate_runs_from_every_plugin_root(tmp_path: Path, script: Path) -> None:
    repo = _decision_repo(tmp_path)
    code, payload = run_cli("locate", "--repo", str(repo), cwd=tmp_path, script=script)
    assert code == 0 and payload["primary"] == "docs/adr"


def test_locate_runs_from_the_hermes_mirror_path(tmp_path: Path) -> None:
    script = (
        REPO_ROOT / "src" / "hermes" / "project-toolkit-knowledge" / "skills" / "skill-bootstrap"
        / "scripts" / "bootstrap_adr.py"
    )  # fmt: skip
    repo = _decision_repo(tmp_path)
    code, payload = run_cli("locate", "--repo", str(repo), cwd=tmp_path, script=script)
    assert code == 0 and payload["folders"][0]["path"] == "docs/adr"


def test_help_lists_the_exit_codes() -> None:
    proc = subprocess.run(
        [sys.executable, str(CLI), "--help"], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0
    for fragment in ("locate", "scan", "draft", "exit codes", "3  git is missing"):
        assert fragment in proc.stdout
