"""Version rollback checks that ask git whether the ref is a real commit."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import rollback_checks


def _head_commit() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        cwd=Path(__file__).resolve().parent,
    )
    return out.stdout.strip()


def test_version_with_a_real_commit_passes() -> None:
    assert rollback_checks.version_reasons({"kind": "version", "ref": _head_commit()}) == []


def test_version_with_an_uppercase_commit_id_passes() -> None:
    rollback = {"kind": "version", "ref": _head_commit().upper()}
    assert rollback_checks.version_reasons(rollback) == []


def test_version_commit_unknown_to_git_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parent)
    reasons = rollback_checks.version_reasons({"kind": "version", "ref": "0" * 40})
    assert len(reasons) == 1
    assert reasons[0].startswith("rollback version ref did not resolve to a commit (git exit 128)")
    assert "Not a valid object name" in reasons[0]


def test_version_outside_a_repository_names_the_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside a repo git also exits 128; the reason must say why, not blame the ref."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    reasons = rollback_checks.version_reasons({"kind": "version", "ref": "a" * 40})
    assert len(reasons) == 1
    assert "not a git repository" in reasons[0]


def test_version_failure_with_no_stderr_still_gives_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def silent(*args: Any, **kwargs: Any) -> Any:
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(rollback_checks.subprocess, "run", silent)
    reasons = rollback_checks.version_reasons({"kind": "version", "ref": "a" * 40})
    assert reasons == ["rollback version ref did not resolve to a commit (git exit 1): no stderr"]


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (
            FileNotFoundError("git"),
            "rollback version ref could not be checked: git did not run: git",
        ),
        (
            subprocess.TimeoutExpired(["git"], 30),
            "rollback version ref could not be checked: git did not finish within 30s",
        ),
    ],
)
def test_version_blocks_when_git_cannot_run(
    monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str
) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr(rollback_checks.subprocess, "run", boom)
    reasons = rollback_checks.version_reasons({"kind": "version", "ref": "a" * 40})
    assert reasons == [reason]


def test_backup_with_matching_content_passes(tmp_path: Path) -> None:
    backup, source = tmp_path / "backup.bin", tmp_path / "source.bin"
    backup.write_bytes(b"same bytes")
    source.write_bytes(b"same bytes")
    rollback = {"kind": "backup", "backup_path": str(backup), "source_path": str(source)}
    assert rollback_checks.backup_reasons(rollback) == []


def test_backup_with_a_different_size_blocks_without_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup, source = tmp_path / "backup.bin", tmp_path / "source.bin"
    backup.write_bytes(b"short")
    source.write_bytes(b"much longer content")

    def no_hash(path: Path) -> str:
        raise AssertionError(f"hashed {path} despite a size mismatch")

    monkeypatch.setattr(rollback_checks, "sha256", no_hash)
    rollback = {"kind": "backup", "backup_path": str(backup), "source_path": str(source)}
    assert rollback_checks.backup_reasons(rollback) == [
        "rollback backup does not match the source file"
    ]


def test_backup_with_same_size_but_different_bytes_blocks(tmp_path: Path) -> None:
    backup, source = tmp_path / "backup.bin", tmp_path / "source.bin"
    backup.write_bytes(b"aaaa")
    source.write_bytes(b"bbbb")
    rollback = {"kind": "backup", "backup_path": str(backup), "source_path": str(source)}
    assert rollback_checks.backup_reasons(rollback) == [
        "rollback backup does not match the source file"
    ]


def test_backup_that_cannot_be_read_blocks_with_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup, source = tmp_path / "backup.bin", tmp_path / "source.bin"
    backup.write_bytes(b"data")
    source.write_bytes(b"data")

    def denied(path: Path) -> str:
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(rollback_checks, "sha256", denied)
    rollback = {"kind": "backup", "backup_path": str(backup), "source_path": str(source)}
    reasons = rollback_checks.backup_reasons(rollback)
    assert len(reasons) == 1
    assert reasons[0].startswith("rollback backup or source file could not be read:")


def test_sha256_matches_hashlib_on_the_whole_file(tmp_path: Path) -> None:
    import hashlib

    data = b"x" * (1 << 20) + b"tail"
    path = tmp_path / "big.bin"
    path.write_bytes(data)
    assert rollback_checks.sha256(path) == hashlib.sha256(data).hexdigest()


def _write_snapshot(
    root: Path,
    *,
    ref: str = "snap-1",
    target: str = "sqlite:users",
    payload_bytes: bytes = b"recovery data",
) -> dict[str, Any]:
    payload = root / "payload.dump"
    payload.write_bytes(payload_bytes)
    manifest = {
        "format": "destructive-change-snapshot",
        "version": 1,
        "ref": ref,
        "target": target,
        "payload": payload.name,
        "sha256": hashlib.sha256(payload_bytes).hexdigest(),
    }
    (root / "snapshot.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _snapshot_rollback(path: Path) -> dict[str, object]:
    return {
        "kind": "snapshot",
        "ref": "snap-1",
        "snapshot_target": "sqlite:users",
        "snapshot_path": str(path),
    }


def test_snapshot_directory_with_a_valid_manifest_passes(tmp_path: Path) -> None:
    _write_snapshot(tmp_path)
    assert rollback_checks.snapshot_reasons(_snapshot_rollback(tmp_path)) == []


def test_snapshot_manifest_file_with_a_valid_payload_passes(tmp_path: Path) -> None:
    _write_snapshot(tmp_path)
    manifest = tmp_path / "snapshot.json"
    assert rollback_checks.snapshot_reasons(_snapshot_rollback(manifest)) == []


def test_snapshot_unrelated_existing_file_blocks(tmp_path: Path) -> None:
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("not a snapshot", encoding="utf-8")
    assert rollback_checks.snapshot_reasons(_snapshot_rollback(unrelated)) == [
        "rollback snapshot_path does not name a valid snapshot manifest"
    ]


def test_snapshot_missing_path_and_empty_directory_block(tmp_path: Path) -> None:
    missing = tmp_path / "gone"
    assert rollback_checks.snapshot_reasons(_snapshot_rollback(missing)) == [
        "rollback snapshot_path does not exist or is empty"
    ]
    assert rollback_checks.snapshot_reasons(_snapshot_rollback(tmp_path)) == [
        "rollback snapshot_path does not exist or is empty"
    ]


def test_snapshot_directory_without_a_manifest_blocks(tmp_path: Path) -> None:
    (tmp_path / "payload.dump").write_bytes(b"recovery data")
    assert rollback_checks.snapshot_reasons(_snapshot_rollback(tmp_path)) == [
        "rollback snapshot directory has no snapshot.json manifest"
    ]


@pytest.mark.parametrize(
    ("manifest_changes", "reason"),
    [
        ({"ref": "snap-2"}, "manifest ref does not match ref"),
        ({"target": "sqlite:orders"}, "manifest target does not match snapshot_target"),
        ({"format": "other-format"}, "manifest format must be destructive-change-snapshot"),
        ({"version": 2}, "manifest version must be 1"),
        ({"sha256": "0" * 64}, "payload does not match the manifest sha256"),
    ],
)
def test_snapshot_manifest_mismatch_blocks(
    tmp_path: Path, manifest_changes: dict[str, object], reason: str
) -> None:
    manifest = _write_snapshot(tmp_path)
    manifest.update(manifest_changes)
    (tmp_path / "snapshot.json").write_text(json.dumps(manifest), encoding="utf-8")
    reasons = rollback_checks.snapshot_reasons(_snapshot_rollback(tmp_path))
    assert len(reasons) == 1
    assert reason in reasons[0]


def test_snapshot_without_a_target_blocks(tmp_path: Path) -> None:
    _write_snapshot(tmp_path)
    rollback = _snapshot_rollback(tmp_path)
    del rollback["snapshot_target"]
    assert rollback_checks.snapshot_reasons(rollback) == [
        "rollback kind snapshot needs a snapshot_target to be verified"
    ]


def test_snapshot_payload_outside_the_snapshot_blocks(tmp_path: Path) -> None:
    manifest = _write_snapshot(tmp_path)
    outside = tmp_path.parent / "outside.dump"
    outside.write_bytes(b"outside")
    manifest["payload"] = "../outside.dump"
    manifest["sha256"] = hashlib.sha256(b"outside").hexdigest()
    (tmp_path / "snapshot.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert rollback_checks.snapshot_reasons(_snapshot_rollback(tmp_path)) == [
        "rollback snapshot payload must be a relative path inside the snapshot"
    ]


def test_snapshot_directory_that_cannot_be_listed_blocks_with_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(self: Path) -> Any:
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(rollback_checks.Path, "iterdir", denied)
    reasons = rollback_checks.snapshot_reasons({"kind": "snapshot", "snapshot_path": str(tmp_path)})
    assert len(reasons) == 1
    assert reasons[0].startswith("rollback snapshot_path could not be read:")


def test_every_referenced_kind_has_a_check() -> None:
    assert set(rollback_checks.KIND_CHECKS) == {"backup", "snapshot", "version"}
