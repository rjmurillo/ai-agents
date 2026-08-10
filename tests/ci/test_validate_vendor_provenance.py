"""Tests for vendor provenance validator.

Covers: CLI exit codes, artifact authentication (pass and tamper),
unpinned executable detection, mirror parity, lockfile v1/v3, execution
key rejection (block/quoted/flow/nested), symlink containment, .npmrc
rejection, installed-hook entrypoint, and valid-candidate exit-0.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = "scripts/ci/validate_vendor_provenance.py"
WT = Path(__file__).resolve().parents[2]


def _run(extra: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WT / SCRIPT), *extra],
        capture_output=True, encoding="utf-8", errors="replace",
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(p: Path, content: bytes | str = b"") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content.encode() if isinstance(content, str) else content)


# ── CLI exit codes ──

def test_missing_candidate_root_exits_nonzero() -> None:
    r = _run(["--candidate-root", "/nonexistent"])
    assert r.returncode != 0


# ── Valid candidate exits 0 ──

def test_valid_candidate_exits_zero(tmp_path: Path) -> None:
    """Candidate matching all pins and no vendor tree passes."""
    from scripts.ci.validate_vendor_provenance import _PINNED_ARTIFACTS

    root = tmp_path / "candidate"
    for rel, _sha, _label in _PINNED_ARTIFACTS:
        # Write a file whose SHA-256 matches the pin
        fpath = root / rel
        fpath.parent.mkdir(parents=True, exist_ok=True)
        # We can't reverse SHA-256, so patch the pin table.
        # Instead: write known content and validate directly.
    # Simpler: write the real files from main
    import shutil
    repo = Path(__file__).resolve().parents[2]
    for rel, _sha, _label in _PINNED_ARTIFACTS:
        src = repo / rel
        dst = root / rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    # Ensure copilot-cli dispatch + manifest exist (non-executable)
    for extra in [
        "src/copilot-cli/hooks/PreToolUse/_dispatch.py",
        "src/copilot-cli/hooks/PreToolUse/_manifest.json",
    ]:
        ef = root / extra
        if not ef.exists():
            _write(ef, b"# non-executable placeholder")
    r = _run(["--candidate-root", str(root)])
    assert r.returncode == 0, f"Expected exit 0, got {r.returncode}:\n{r.stdout}"


# ── Artifact authentication ──

class TestArtifactAuthentication:
    def test_tampered_bootstrap_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        _write(root / ".claude/hooks/PreToolUse/_bootstrap.py", b"TAMPERED")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "Hook bootstrap" in r.stdout and "mismatch" in r.stdout

    def test_tampered_push_guard_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        _write(root / ".claude/hooks/PreToolUse/push_guard_base.py", b"TAMPERED")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "Push guard" in r.stdout

    def test_tampered_generator_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        _write(root / "build/scripts/generate_hooks_events.py", b"TAMPERED")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "generator" in r.stdout.lower()


# ── Unpinned executable detection ──

class TestUnpinnedExecutables:
    def test_new_py_in_hook_dir_flagged(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        _write(root / ".claude/hooks/PreToolUse/evil_hook.py", b"# evil")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "Unpinned executable" in r.stdout
        assert "evil_hook.py" in r.stdout


# ── Mirror parity ──

class TestMirrorParity:
    def test_mismatched_bootstrap_mirror(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        _write(root / ".claude/hooks/PreToolUse/_bootstrap.py", b"A")
        _write(root / "src/copilot-cli/hooks/PreToolUse/_bootstrap.py", b"B")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "Parity mismatch" in r.stdout


# ── Lockfile policy ──

class TestLockfilePolicy:
    def _vendor(self, root: Path) -> Path:
        return root / ".claude/hooks/PreToolUse/_vendor/markdownlint"

    def test_lockfile_v1_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        v = self._vendor(root)
        lock = {"lockfileVersion": 1, "packages": {
            "": {}, "node_modules/x": {
                "resolved": "https://registry.npmjs.org/x/-/x-1.0.tgz",
                "integrity": "sha512-" + "A" * 86 + "==",
            },
        }}
        _write(v / "package-lock.json", json.dumps(lock))
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "lockfileVersion" in r.stdout

    def test_git_dep_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        v = self._vendor(root)
        lock = {"lockfileVersion": 3, "packages": {
            "": {}, "node_modules/x": {
                "resolved": "git+https://evil.com/r.git",
                "integrity": "sha512-" + "A" * 86 + "==",
            },
        }}
        _write(v / "package-lock.json", json.dumps(lock))
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "Non-canonical" in r.stdout or "Non-HTTPS" in r.stdout

    def test_missing_integrity_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        v = self._vendor(root)
        lock = {"lockfileVersion": 3, "packages": {
            "": {}, "node_modules/x": {
                "resolved": "https://registry.npmjs.org/x/-/x-1.0.tgz",
            },
        }}
        _write(v / "package-lock.json", json.dumps(lock))
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "integrity" in r.stdout.lower()


# ── Config safety ──

class TestConfigSafety:
    def _cfg_path(self, root: Path) -> Path:
        return root / ".claude/hooks/PreToolUse/markdownlint-safe-config.yaml"

    def test_block_customrules_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        _write(self._cfg_path(root), "config:\n  MD040: true\ncustomRules:\n  - x\n")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "customRules" in r.stdout

    def test_quoted_key_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        _write(self._cfg_path(root), '"customRules":\n  - x\n')
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "customRules" in r.stdout

    def test_flow_extends_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        _write(self._cfg_path(root), '{"extends": "./evil.yaml"}')
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "extends" in r.stdout

    def test_nested_key_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        cfg = "overrides:\n  - config:\n      markdownItPlugins:\n        - evil\n"
        _write(self._cfg_path(root), cfg)
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "markdownItPlugins" in r.stdout

    def test_clean_config_no_exec_keys(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        _write(self._cfg_path(root), "config:\n  MD040: true\nignores:\n  - '.git/**'\n")
        r = _run(["--candidate-root", str(root)])
        assert "Execution-capable key" not in r.stdout


# ── Symlink containment ──

class TestSymlinkContainment:
    def test_escaping_symlink_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        vendor = root / ".claude/hooks/PreToolUse/_vendor/markdownlint"
        vendor.mkdir(parents=True)
        os.symlink("/etc/passwd", str(vendor / "escape"))
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "Symlink escapes" in r.stdout


# ── .npmrc rejection ──

class TestNpmrcRejection:
    def test_npmrc_in_vendor_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        vendor = root / ".claude/hooks/PreToolUse/_vendor/markdownlint"
        _write(vendor / ".npmrc", "registry=https://evil.com")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert ".npmrc" in r.stdout


# ── Installed-hook entrypoint test ──

class TestInstalledHookEntrypoint:
    """Verify the validator can be invoked as a subprocess (entrypoint test)."""

    def test_entrypoint_runs_and_returns_int(self) -> None:
        r = _run(["--candidate-root", "/tmp/empty-dir-nonexistent"])
        assert isinstance(r.returncode, int)
        assert r.returncode in (1, 2)
