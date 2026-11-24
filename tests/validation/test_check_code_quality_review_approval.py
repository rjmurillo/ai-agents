"""Exercise exact approvals against committed Git objects and the real assessor."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_code_quality_review_approval as gate

pytestmark = pytest.mark.skipif(os.name != "posix", reason="trusted POSIX process lookup")

_REPO = Path(__file__).resolve().parents[2]
_COMMENT = 123
_ISSUE = 7512


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def _write(repo: Path, path: str, text: str) -> None:
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "-m", message)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "candidate"
    target.mkdir()
    _git(target, "init", "--quiet", "--initial-branch=main")
    _git(target, "config", "user.email", "test@example.invalid")
    _git(target, "config", "user.name", "Test")
    _git(target, "config", "commit.gpgsign", "false")
    for path in (gate.ASSESSOR_PATH, gate.CONFIG_PATH):
        _write(target, path, (_REPO / path).read_text(encoding="utf-8"))
    _write(target, "first.py", "def ready():\n    return True\n")
    _write(target, "second.py", "def ready():\n    return True\n")
    _commit(target, "Duplicate setup")
    _git(target, "update-ref", gate.INTEGRATION_REF, "HEAD")
    _git(target, "switch", "--quiet", "-c", "candidate")
    # A new third-party import is a regression the issue #7525 admission
    # refuses, so it still needs an owner approval.
    _write(target, "second.py", "import requests\n\n\ndef check():\n    return requests.get\n")
    _commit(target, "Add a third-party dependency")
    monkeypatch.chdir(target)
    return target


def test_shared_helper_extraction_needs_no_approval(repo, capsys):
    _git(repo, "reset", "--quiet", "--hard", gate.INTEGRATION_REF)
    _write(repo, "second.py", "from first import ready\n\n\ndef check():\n    return ready()\n")
    _commit(repo, "Extract shared setup")

    rc = _run(repo)

    output = capsys.readouterr()
    assert rc != 0
    assert json.loads(output.out)["raw_exit"] == 0
    assert "approval does not apply to assessor exit 0" in output.err
    raw = json.loads((repo.parent / "raw.json").read_text(encoding="utf-8"))
    comparison = next(c for c in raw["comparisons"] if c["file_path"] == "second.py")
    assert comparison["regressions"] == ["coupling"]
    assert comparison["change_admissions"]["coupling"]["rule"] == "no_new_third_party_import"


def _run(repo: Path, *args: str) -> int:
    base = _git(repo, "rev-parse", gate.INTEGRATION_REF)
    head = _git(repo, "rev-parse", "HEAD")
    return gate.main(
        ["--base", base, "--head", head, "--assessment", str(repo.parent / "raw.json"), *args]
    )


def _inventory(repo: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert _run(repo) == 0
    return json.loads(capsys.readouterr().out)


def _approval(digest: object) -> dict[str, object]:
    return {
        "id": _COMMENT,
        "issue_url": f"{gate.API_ROOT}/{_ISSUE}",
        "user": {"login": "rjmurillo"},
        "author_association": "OWNER",
        "created_at": "2026-11-21T12:00:00Z",
        "updated_at": "2026-11-21T12:00:00Z",
        "body": f"Code-quality review approval SHA256: {digest}",
    }


def _verify(repo: Path) -> int:
    return _run(repo, "--issue", str(_ISSUE), "--comment", str(_COMMENT))


def test_inventory_lists_only_rows_the_assessor_did_not_admit(repo, capsys):
    _git(repo, "switch", "--quiet", "--detach", gate.INTEGRATION_REF)
    _write(repo, "third.py", "def ready():\n    return True\n")
    _commit(repo, "Add a third duplicate")
    _git(repo, "update-ref", gate.INTEGRATION_REF, "HEAD")
    _git(repo, "switch", "--quiet", "-c", "mixed")
    _write(repo, "second.py", "import requests\n\n\ndef check():\n    return requests.get\n")
    _write(repo, "third.py", "from first import ready\n\n\ndef check():\n    return ready()\n")
    _commit(repo, "Add a dependency and extract shared setup")

    inventory = _inventory(repo, capsys)

    raw = json.loads((repo.parent / "raw.json").read_text(encoding="utf-8"))
    third = next(c for c in raw["comparisons"] if c["file_path"] == "third.py")
    assert third["regressions"] == ["coupling"]
    assert third["change_admissions"]["coupling"]["rule"] == "no_new_third_party_import"
    assert [row["path"] for row in inventory["regressions"]] == ["second.py"]


def test_trusted_approval_keeps_raw_scores_and_reports_warn(repo, capsys, monkeypatch):
    inventory = _inventory(repo, capsys)
    assert inventory["regressions"] == [
        {"path": "second.py", "quality": "coupling", "base": 10.0, "head": 9.0}
    ]
    assert inventory["raw_exit"] == 10
    assert "verdict" not in inventory
    monkeypatch.setattr(gate, "_comment", lambda _: _approval(inventory["approval_sha256"]))

    assert _verify(repo) == 0

    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["verdict"] == "WARN"
    assert not output.err
    raw_stderr = (repo.parent / "raw.json.stderr").read_bytes()
    assert report["stderr_sha256"] == hashlib.sha256(raw_stderr).hexdigest()
    assert report["regressions"] == inventory["regressions"]
    assert report["reviewed_sha"] == _git(repo, "rev-parse", "HEAD")
    raw_bytes = (repo.parent / "raw.json").read_bytes()
    assert report["assessment_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    raw = json.loads(raw_bytes)
    assert raw["comparisons"][0]["regressions"] == ["coupling"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("user", {"login": "other"}),
        ("author_association", "CONTRIBUTOR"),
        ("issue_url", f"{gate.API_ROOT}/123"),
        ("body", "No approval."),
        ("updated_at", "2026-11-21T13:00:00Z"),
    ],
)
def test_unverified_comment_leaves_failure(repo, capsys, monkeypatch, key, value):
    inventory = _inventory(repo, capsys)
    approval = {**_approval(inventory["approval_sha256"]), key: value}
    monkeypatch.setattr(gate, "_comment", lambda _: approval)

    assert _verify(repo) == 1
    output = capsys.readouterr()
    assert "no matching approval" in output.err
    report = json.loads(output.out)
    assert report["raw_exit"] == 10
    raw_stderr = (repo.parent / "raw.json.stderr").read_bytes()
    assert b"coupling regressed" in raw_stderr
    assert b"no matching approval" not in raw_stderr
    assert report["stderr_sha256"] == hashlib.sha256(raw_stderr).hexdigest()


def test_source_change_invalidates_approval_even_with_same_scores(repo, capsys, monkeypatch):
    inventory = _inventory(repo, capsys)
    monkeypatch.setattr(gate, "_comment", lambda _: _approval(inventory["approval_sha256"]))
    _write(repo, "first.py", "def ready():\n    return False\n")
    _commit(repo, "Change behavior without adding imports")

    assert _verify(repo) == 1


@pytest.mark.parametrize("omit", ["hidden", "sparse"])
def test_assessor_reads_committed_files_despite_local_changes(repo, capsys, omit):
    inventory = _inventory(repo, capsys)
    if omit == "sparse":
        _git(repo, "sparse-checkout", "set", "--no-cone", "/first.py")
        assert not (repo / "second.py").exists()
    else:
        _git(repo, "update-index", "--assume-unchanged", "second.py")
        _write(repo, "second.py", "def check():\n    return True\n")

    assert _inventory(repo, capsys) == inventory


@pytest.mark.parametrize("path", [gate.ASSESSOR_PATH, gate.CONFIG_PATH])
def test_candidate_cannot_change_the_trusted_scoring_inputs(repo, capsys, path):
    _write(repo, path, "{}\n")
    _commit(repo, "Replace the working-tree assessment input")

    assert _run(repo) == 1
    assert f"trusted assessment input {path}" in capsys.readouterr().err


def test_absolute_threshold_failure_stays_blocking_alongside_regression(repo, capsys):
    _write(repo, "repetitive.py", "print('duplicate line')\n" * 80)
    _commit(repo, "Add a file below the absolute threshold")

    assert _verify(repo) == 1
    assert "absolute threshold failure" in capsys.readouterr().err


def test_moved_base_cannot_reuse_a_valid_comment(repo, capsys, monkeypatch):
    inventory = _inventory(repo, capsys)

    def move_base(_: int) -> dict[str, object]:
        _git(repo, "update-ref", gate.INTEGRATION_REF, "HEAD")
        return _approval(inventory["approval_sha256"])

    monkeypatch.setattr(gate, "_comment", move_base)

    assert _verify(repo) == 1
    assert "differs from the pinned review" in capsys.readouterr().err


def test_nonregular_changed_source_cannot_hide_evidence(repo, capsys):
    source = repo / "first.py"
    source.rename(repo / "renamed-original.py")
    try:
        source.symlink_to("nonexistent.py")
    except OSError:
        pytest.skip("creating symlinks is unavailable")
    _commit(repo, "Replace source with a dangling symlink")

    assert _run(repo) == 1
    assert "cannot verify nonregular diff entry" in capsys.readouterr().err


@pytest.mark.parametrize("extension", ["go", "GO"])
def test_go_module_context_outside_snapshot_cannot_influence_approval(
    repo, capsys, monkeypatch, extension
):
    monkeypatch.setattr(gate.tempfile, "tempdir", str(repo.parent))
    _write(repo.parent, "go.mod", "module unwanted\n")
    _write(repo, f"pkg/tool.{extension}", "package pkg\n")
    _commit(repo, "Add Go source")

    assert _run(repo) == 1
    assert "Go module context escapes snapshot" in capsys.readouterr().err


def test_api_error_retains_raw_score_evidence(repo, capsys, monkeypatch):
    def offline(_: int) -> dict[str, object]:
        raise OSError("API unavailable")

    monkeypatch.setattr(gate, "_comment", offline)

    assert _verify(repo) == 3
    output = capsys.readouterr()
    assert "API unavailable" in output.err
    assert json.loads(output.out)["raw_exit"] == 10


def test_trusted_path_excludes_checkout_and_relative_entries(repo, monkeypatch):
    trusted = repo.parent / "trusted-bin"
    monkeypatch.setenv(
        "PATH", os.pathsep.join([str(trusted), "", ".", "relative", str(repo / "bin")])
    )

    assert gate._git_env()["PATH"] == str(trusted)


def test_snapshot_validation_requires_committed_blob_bytes(repo):
    base = _git(repo, "rev-parse", gate.INTEGRATION_REF)
    head = _git(repo, "rev-parse", "HEAD")
    _write(repo, "second.py", "def check():\n    return True\n")

    with pytest.raises(gate.UnapprovedError, match="differs from the committed blob"):
        gate._validate_snapshot(repo, base, head)


def test_unwritable_assessment_path_keeps_raw_exit_and_stderr(repo, capsys):
    raw = repo.parent / "raw.json"
    raw.mkdir()

    assert _run(repo) == 3

    output = capsys.readouterr()
    assert json.loads(output.out)["raw_exit"] == 10
    assert b"coupling regressed" in (repo.parent / "raw.json.stderr").read_bytes()


def test_evidence_loss_blocks_otherwise_comparable_regression(repo, capsys):
    (repo / "first.py").write_bytes(b"\xff")
    _commit(repo, "Remove readable source evidence")

    assert _verify(repo) == 1

    output = capsys.readouterr()
    assert json.loads(output.out)["raw_exit"] == 10
    assert "reported lost evidence" in output.err


def test_comment_lookup_has_an_outer_deadline_and_response_limit(monkeypatch):
    def run(argv, **kwargs):
        assert argv[-2] == f"{gate.API_ROOT}/comments/{_COMMENT}"
        assert int(argv[-1]) == gate._MAX_COMMENT_BYTES + 1
        assert kwargs["timeout"] == 15
        return subprocess.CompletedProcess(argv, 0, b"x" * (gate._MAX_COMMENT_BYTES + 1))

    monkeypatch.setattr(gate.subprocess, "run", run)

    with pytest.raises(ValueError, match="response limit"):
        gate._comment(_COMMENT)
