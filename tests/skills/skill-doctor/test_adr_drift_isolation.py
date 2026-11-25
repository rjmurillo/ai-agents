"""adr_drift.py isolation: no lazy fetch, git env parity, FIFO inputs, comment tails, fix text."""

from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

import adr_drift
import adr_git
import adr_history
import adr_text
import pytest
from adr_drift_helpers import adr_path, commit, git, kinds, run_cli, scan, seeded_repo
from adr_drift_helpers import adr_text as adr_body
from render_report import main as render_main

REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_SCAN = REPO_ROOT / "src/claude/skills/skill-bootstrap/scripts/adr_scan.py"


def _bootstrap_local_git_env() -> frozenset[str]:
    """skill-bootstrap's `_LOCAL_GIT_ENV`, read from its source: frozenset("...".split())."""
    tree = ast.parse(BOOTSTRAP_SCAN.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_LOCAL_GIT_ENV" for t in node.targets
        ):
            call = node.value
            assert isinstance(call, ast.Call)
            split = call.args[0]
            assert isinstance(split, ast.Call) and isinstance(split.func, ast.Attribute)
            text = split.func.value
            assert isinstance(text, ast.Constant) and isinstance(text.value, str)
            return frozenset(text.value.split())
    raise AssertionError("skill-bootstrap adr_scan.py has no _LOCAL_GIT_ENV")


def test_the_stripped_git_variables_equal_skill_bootstrap_list():
    assert adr_git.LOCAL_GIT_ENV == _bootstrap_local_git_env()


def _bootstrap_constant(name: str) -> ast.expr:
    tree = ast.parse(BOOTSTRAP_SCAN.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node.value
    raise AssertionError(f"skill-bootstrap adr_scan.py has no {name}")


def _pattern_of(name: str) -> str:
    call = _bootstrap_constant(name)
    assert isinstance(call, ast.Call) and isinstance(call.args[0], ast.Constant)
    pattern = call.args[0].value
    assert isinstance(pattern, str)
    return pattern


def test_the_lazy_fetch_rules_equal_skill_bootstrap_rules():
    assert ast.literal_eval(_bootstrap_constant("_NO_LAZY_FETCH_GIT")) == adr_git.NO_LAZY_FETCH_GIT
    backports = ast.literal_eval(_bootstrap_constant("_NO_LAZY_FETCH_BACKPORTS"))
    assert backports == adr_git.NO_LAZY_FETCH_BACKPORTS
    assert _pattern_of("_PROMISOR") == adr_git.PROMISOR.pattern
    assert _pattern_of("_GIT_VERSION") == adr_git.GIT_VERSION.pattern


def test_the_git_env_turns_off_lazy_fetch():
    assert adr_git._git_env()["GIT_NO_LAZY_FETCH"] == "1"


def _missing_objects(repo: Path) -> int:
    out = git(repo, "rev-list", "--objects", "--all", "--missing=print")
    return sum(1 for line in out.splitlines() if line.startswith("?"))


def test_a_partial_clone_fetches_nothing(tmp_path, capsys):
    source = seeded_repo(tmp_path / "source", {adr_path(1, "old"): adr_body(1)})
    git(source, "mv", adr_path(1, "old"), adr_path(1, "new"))
    commit(source, {adr_path(1, "new"): adr_body(1, body="edited")}, "docs: rename and edit")
    git(source, "config", "uploadpack.allowFilter", "true")
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", "--no-checkout", "--filter=blob:none", source.as_uri(), str(clone)],
        check=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    before = _missing_objects(clone)
    if before == 0:
        pytest.skip("this git did not make a blobless clone")
    out = tmp_path / "out" / "scan.json"

    code, _, err = run_cli(capsys, "scan", "--repo", str(clone), "--out", str(out))

    assert _missing_objects(clone) == before
    if adr_git.old_git_refusal(clone) is not None:  # this git may fetch, so it refuses
        assert code == 2 and "partial clone" in err
        return
    assert code == 0, err
    assert json.loads(out.read_text(encoding="utf-8"))["examined"] == 2


@pytest.mark.parametrize("spec", ["tree:0", "combine:blob:none+tree:0"])
def test_a_treeless_clone_exits_2_with_its_reason(tmp_path, capsys, spec):
    source = seeded_repo(tmp_path / "source", {adr_path(1): adr_body(1)})
    commit(source, {"x.txt": "1"}, "chore: second")
    git(source, "config", "uploadpack.allowFilter", "true")
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", "--no-checkout", f"--filter={spec}", source.as_uri(), str(clone)],
        check=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if _missing_objects(clone) == 0:
        pytest.skip("this git did not make a treeless clone")
    before = _missing_objects(clone)
    out = tmp_path / "out" / "scan.json"

    code, _, err = run_cli(capsys, "scan", "--repo", str(clone), "--out", str(out))

    assert code == 2 and "can omit the trees" in err and not out.exists()
    assert _missing_objects(clone) == before


def test_an_old_git_refuses_a_partial_clone(monkeypatch, tmp_path):
    replies = {"config": "remote.origin.promisor true\n", "version": "git version 2.44.0\n"}
    monkeypatch.setattr(adr_git, "run_git", lambda repo, args: replies[args[0]])

    refusal = adr_git.partial_clone_refusal(tmp_path)

    assert refusal is not None and "partial clone" in refusal and "2.44.0" in refusal


@pytest.mark.parametrize("version", ["git version 2.45.1\n", "git version 2.43.4\n"])
def test_a_git_that_honors_no_lazy_fetch_allows_a_blobless_clone(monkeypatch, tmp_path, version):
    replies = {"config": "remote.origin.promisor true\n", "version": version}
    monkeypatch.setattr(adr_git, "run_git", lambda repo, args: replies[args[0]])

    assert adr_git.partial_clone_refusal(tmp_path) is None


def test_a_config_probe_that_git_rejects_raises(monkeypatch, tmp_path):
    def fail(repo, args):
        raise adr_git.GitError("bad config file", returncode=128)

    monkeypatch.setattr(adr_git, "run_git", fail)

    with pytest.raises(adr_git.GitError, match="bad config file"):
        adr_git.partial_clone_refusal(tmp_path)


def test_a_config_probe_with_no_matching_key_is_a_full_clone(monkeypatch, tmp_path):
    def no_match(repo, args):
        raise adr_git.GitError("", returncode=1)

    monkeypatch.setattr(adr_git, "run_git", no_match)

    assert adr_git.partial_clone_refusal(tmp_path) is None


def test_a_failed_partial_clone_probe_exits_3(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")

    def fail(repo):
        raise adr_git.GitError("git config --get-regexp failed")

    monkeypatch.setattr(adr_drift, "partial_clone_refusal", fail)
    out = tmp_path / "out" / "scan.json"

    code, _, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(out))

    assert code == 3 and "git config --get-regexp failed" in err and not out.exists()


def test_a_truncated_rename_record_raises():
    with pytest.raises(adr_git.GitError, match="unexpected git log output"):
        adr_history._parse_paths(["R100", "docs/adr/0001-old.md"], 0)


def test_the_refusal_exits_2(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")
    monkeypatch.setattr(adr_drift, "partial_clone_refusal", lambda repo: "this is a partial clone")
    out = tmp_path / "out" / "scan.json"

    code, _, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(out))

    assert code == 2 and "partial clone" in err and not out.exists()


@pytest.mark.parametrize(
    ("lines", "live"),
    [
        (["<!-- note --> Superseded by ADR-5"], [" Superseded by ADR-5"]),
        (["<!-- a --> <!-- b", "hidden", "-->", "after"], ["after"]),
        (["<!-- only a comment -->", "next"], ["next"]),
        (["<!-- a --> ADR-5 <!-- b --> tail"], [" ADR-5  tail"]),
        (["<!--", "x", "--> <!-- y", "hidden", "-->", "after"], ["after"]),
        (["<!--", "--> Superseded by ADR-5"], [" Superseded by ADR-5"]),
    ],
    ids=["tail", "reopened", "whole-line", "between", "closing-reopens", "closing-tail"],
)
def test_text_after_a_one_line_comment_stays_live(lines, live):
    assert [text for _, text in adr_text.prose_lines(lines)] == live


def test_a_fifo_scan_file_exits_2_without_blocking(tmp_path, capsys):
    if not hasattr(os, "mkfifo"):
        pytest.skip("no FIFOs on this platform")
    (tmp_path / "adr_drift").mkdir()
    os.mkfifo(tmp_path / "adr_drift" / "my-repo.json")
    report = {
        "mode": "adr_only",
        "adr_drift": {"repos": [{"repo": "r", "scan": "adr_drift/my-repo.json"}]},
    }
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        render_main([str(tmp_path / "report.json")])

    assert raised.value.code == 2 and "not a regular file" in capsys.readouterr().err


def test_the_cited_path_fix_leads_with_the_current_path(tmp_path, capsys):
    body = "The code lives in `src/gone/module.py`."
    repo = seeded_repo(tmp_path / "repo", {adr_path(1): adr_body(1, body=body), "src/keep.py": "x"})

    (found,) = kinds(scan(capsys, repo), "adr-cited-path-missing")

    assert found["suggested_fix"].index("current path") < found["suggested_fix"].index("Supersede")


@pytest.mark.parametrize(
    ("config", "refused"),
    [
        ("remote.origin.promisor true\nremote.origin.partialclonefilter blob:none\n", False),
        ("remote.origin.promisor true\nremote.origin.partialclonefilter tree:0\n", True),
    ],
    ids=["blobless", "treeless"],
)
def test_only_a_tree_dropping_filter_is_refused_on_a_new_git(
    monkeypatch, tmp_path, config, refused
):
    replies = {"config": config, "version": "git version 2.55.0\n"}
    monkeypatch.setattr(adr_git, "run_git", lambda repo, args: replies[args[0]])

    refusal = adr_git.partial_clone_refusal(tmp_path)

    assert (refusal is not None and "can omit the trees" in refusal) is refused


@pytest.mark.parametrize(
    ("spec", "keeps"),
    [
        ("blob:none", True),
        ("blob:limit=1k", True),
        ("sparse:oid=abc123", True),
        ("combine:blob:none+blob:limit=1", True),
        ("tree:0", False),
        ("tree:1", False),
        ("object:type=commit", False),
        ("combine:blob:none+tree:0", False),
        ("combine:blob:none+tree%3A0", False),
    ],
)
def test_keeps_trees_reads_every_part_of_a_filter(spec, keeps):
    assert adr_git.keeps_trees(spec) is keeps
