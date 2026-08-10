"""Tests for vendor provenance validator.

Covers: trust-anchor authentication, lockfile v1/v3 policy, quoted/flow
execution keys, co-tampered verifier/config, fork fetch (missing mirror),
modes/symlinks, and CLI exit codes.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPT = "scripts/ci/validate_vendor_provenance.py"


# ── helpers ──────────────────────────────────────────────────────────────────

def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",

    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, content: str | bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode()
    path.write_bytes(content)


def _minimal_lockfile(
    version: str = "3",
    packages: dict[str, object] | None = None,
    with_dependencies: bool = False,
) -> bytes:
    lock: dict[str, object] = {"lockfileVersion": int(version)}
    if packages is not None:
        lock["packages"] = packages
    else:
        lock["packages"] = {
            "": {"name": "root"},
            "node_modules/example": {
                "resolved": "https://registry.npmjs.org/example/-/example-1.0.0.tgz",
                "integrity": "sha512-" + "A" * 86 + "==",
            },
        }
    if with_dependencies:
        lock["dependencies"] = {"old": {}}
    return json.dumps(lock).encode()


def _build_candidate(
    tmp_path: Path,
    verifier_content: bytes = b"verifier-content",
    config_content: bytes = b"config-content",
    cli2_config_content: bytes = b"cli2-content",
    manifest_content: bytes = b"manifest-content",
    lockfile: bytes | None = None,
    mirror_content: bytes | None = None,
) -> tuple[Path, dict[str, str]]:
    """Build a candidate tree and return (root, sha256_map)."""
    root = tmp_path / "candidate"
    vendor = root / "v"
    nm = vendor / "node_modules" / "markdownlint-cli2"
    nm.mkdir(parents=True)

    v_path = root / "verifier.py"
    c_path = root / "config.yaml"
    cli2_path = root / "cli2.yaml"
    m_path = vendor / "INTEGRITY.json"

    _write(v_path, verifier_content)
    _write(c_path, config_content)
    _write(cli2_path, cli2_config_content)
    _write(m_path, manifest_content)

    if lockfile is None:
        lockfile = _minimal_lockfile()
    _write(vendor / "package-lock.json", lockfile)
    _write(vendor / "package.json", b'{"name":"test"}')

    if mirror_content is None:
        mirror_content = verifier_content
    _write(root / "mirror.py", mirror_content)

    # Write a dummy entrypoint covered by manifest
    entry = nm / "markdownlint-cli2-bin.mjs"
    _write(entry, b"entry")

    shas = {
        "verifier": _sha256(verifier_content),
        "config": _sha256(config_content),
        "cli2_config": _sha256(cli2_config_content),
        "manifest": _sha256(manifest_content),
    }
    return root, shas


# ── CLI exit codes ───────────────────────────────────────────────────────────

def test_missing_candidate_root_exits_nonzero() -> None:
    """Validator returns nonzero when candidate root does not exist."""
    r = _run([
        "--candidate-root", "/nonexistent/path",
        "--vendor-rel", "v",
        "--verifier-rel", "v.py",
        "--mirror-rel", "m.py",
        "--config-rel", "c.yaml",
    ])
    assert r.returncode != 0


# ── Trust-anchor authentication ──────────────────────────────────────────────

class TestTrustAnchorAuthentication:
    """Defect 1: authentication must not be circular."""

    def test_mismatched_verifier_rejected(self, tmp_path: Path) -> None:
        """Candidate verifier not matching pin is rejected."""
        root, _ = _build_candidate(tmp_path, verifier_content=b"tampered")
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "Verifier" in r.stdout and "mismatch" in r.stdout

    def test_mismatched_config_rejected(self, tmp_path: Path) -> None:
        root, _ = _build_candidate(tmp_path, config_content=b"tampered")
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "Config" in r.stdout and "mismatch" in r.stdout

    def test_co_tampered_verifier_and_config_both_rejected(
        self, tmp_path: Path,
    ) -> None:
        """Simultaneous verifier+config tamper: both flagged."""
        root, _ = _build_candidate(
            tmp_path, verifier_content=b"bad-v", config_content=b"bad-c",
        )
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "Verifier" in r.stdout
        assert "Config" in r.stdout


# ── Lockfile policy ──────────────────────────────────────────────────────────

class TestLockfilePolicy:
    """Defect 2: strict lockfile validation."""

    def test_lockfile_v1_rejected(self, tmp_path: Path) -> None:
        lock = _minimal_lockfile(version="1")
        root, _ = _build_candidate(tmp_path, lockfile=lock)
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "lockfileVersion" in r.stdout

    def test_lockfile_v2_rejected(self, tmp_path: Path) -> None:
        lock = _minimal_lockfile(version="2")
        root, _ = _build_candidate(tmp_path, lockfile=lock)
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "lockfileVersion" in r.stdout

    def test_empty_packages_rejected(self, tmp_path: Path) -> None:
        lock = json.dumps({"lockfileVersion": 3, "packages": {}}).encode()
        root, _ = _build_candidate(tmp_path, lockfile=lock)
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "no non-root" in r.stdout or "no packages" in r.stdout

    def test_git_dep_rejected(self, tmp_path: Path) -> None:
        lock = json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "root"},
                "node_modules/evil": {
                    "resolved": "git+https://evil.com/repo.git",
                    "integrity": "sha512-" + "A" * 86 + "==",
                },
            },
        }).encode()
        root, _ = _build_candidate(tmp_path, lockfile=lock)
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "Non-canonical" in r.stdout or "Non-HTTPS" in r.stdout

    def test_link_dep_rejected(self, tmp_path: Path) -> None:
        lock = json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "root"},
                "node_modules/local": {
                    "resolved": "https://registry.npmjs.org/x/-/x-1.0.0.tgz",
                    "integrity": "sha512-" + "A" * 86 + "==",
                    "link": True,
                },
            },
        }).encode()
        root, _ = _build_candidate(tmp_path, lockfile=lock)
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "link" in r.stdout.lower()

    def test_missing_integrity_rejected(self, tmp_path: Path) -> None:
        lock = json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "root"},
                "node_modules/pkg": {
                    "resolved": "https://registry.npmjs.org/pkg/-/pkg-1.0.0.tgz",
                },
            },
        }).encode()
        root, _ = _build_candidate(tmp_path, lockfile=lock)
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "integrity" in r.stdout.lower()


# ── Config safety (YAML execution keys) ─────────────────────────────────────

class TestConfigSafety:
    """Defect 3: recursive rejection of execution keys."""

    def test_block_style_customrules_rejected(self, tmp_path: Path) -> None:
        cfg = textwrap.dedent("""\
            config:
              MD040: true
            customRules:
              - ./evil.js
        """)
        root, _ = _build_candidate(tmp_path, config_content=cfg.encode())
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "customRules" in r.stdout

    def test_quoted_key_rejected(self, tmp_path: Path) -> None:
        """Quoted execution keys must still be caught."""
        cfg = textwrap.dedent("""\
            config:
              MD040: true
            "customRules":
              - ./evil.js
        """)
        root, _ = _build_candidate(tmp_path, config_content=cfg.encode())
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "customRules" in r.stdout

    def test_flow_mapping_key_rejected(self, tmp_path: Path) -> None:
        """Flow-style {key: value} execution keys rejected."""
        cfg = '{"config": {"MD040": true}, "extends": "./evil.yaml"}'
        root, _ = _build_candidate(tmp_path, config_content=cfg.encode())
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "extends" in r.stdout

    def test_nested_execution_key_rejected(self, tmp_path: Path) -> None:
        """Execution key nested inside overrides must be caught."""
        cfg = textwrap.dedent("""\
            config:
              MD040: true
            overrides:
              - config:
                  markdownItPlugins:
                    - plugin-evil
        """)
        root, _ = _build_candidate(tmp_path, config_content=cfg.encode())
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "markdownItPlugins" in r.stdout

    def test_clean_config_passes(self, tmp_path: Path) -> None:
        """Config with only rule settings passes."""
        cfg = textwrap.dedent("""\
            config:
              MD040: true
              MD024:
                siblings_only: true
            ignores:
              - ".git/**"
        """)
        root, _ = _build_candidate(tmp_path, config_content=cfg.encode())
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        # Will fail on pin mismatch, but NOT on config safety
        assert "Execution-capable key" not in r.stdout


# ── Mirror parity ────────────────────────────────────────────────────────────

class TestMirrorParity:
    """Fork fetch: missing or mismatched mirror."""

    def test_mismatched_mirror_rejected(self, tmp_path: Path) -> None:
        root, _ = _build_candidate(
            tmp_path,
            verifier_content=b"verifier",
            mirror_content=b"different-mirror",
        )
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "Parity mismatch" in r.stdout

    def test_missing_mirror_rejected(self, tmp_path: Path) -> None:
        root, _ = _build_candidate(tmp_path)
        mirror = root / "mirror.py"
        mirror.unlink()
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "Mirror not found" in r.stdout


# ── Modes and symlinks ───────────────────────────────────────────────────────

class TestModesAndSymlinks:
    def test_escaping_symlink_rejected(self, tmp_path: Path) -> None:
        root, _ = _build_candidate(tmp_path)
        vendor = root / "v"
        escape = vendor / "node_modules" / "escape_link"
        os.symlink("/etc/passwd", str(escape))
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "Symlink escapes" in r.stdout
