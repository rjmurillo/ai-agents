"""Tests for vendor provenance validator.

Covers: trust-anchor authentication, lockfile v1/v3 policy, quoted/flow
execution keys, co-tampered verifier/config, fork fetch (missing mirror),
modes/symlinks, and CLI exit codes.
"""

from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

SCRIPT = "scripts/ci/validate_vendor_provenance.py"


# ── helpers ──────────────────────────────────────────────────────────────────

def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",

    )


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_vendor_provenance", SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def test_explicit_mapping_key_rejected(self, tmp_path: Path) -> None:
        """YAML explicit mapping keys must use the parser path."""
        cfg = textwrap.dedent("""\
            ? customRules
            :
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

    def test_yaml_parser_unavailable_fails_closed(self, tmp_path: Path) -> None:
        """Missing PyYAML must not fall back to partial text scanning."""
        root, _ = _build_candidate(tmp_path)
        validator = _load_validator()
        original_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> object:
            if name == "yaml":
                raise ImportError("blocked")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            errors = validator._validate_config_safe(root / "config.yaml")

        assert errors == ["PyYAML is required for config validation"]

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
        # Containment check catches missing file before mirror parity
        assert "Cannot resolve" in r.stdout or "Mirror not found" in r.stdout


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

    def test_broken_symlink_rejected(self, tmp_path: Path) -> None:
        """Broken symlinks are rejected (cannot resolve)."""
        root, _ = _build_candidate(tmp_path)
        vendor = root / "v"
        broken = vendor / "node_modules" / "broken_link"
        os.symlink("/nonexistent/target/that/does/not/exist", str(broken))
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "Broken symlink" in r.stdout


# ── Path containment (CWE-59/CWE-22) ────────────────────────────────────────

class TestPathContainment:
    """Thread 1: reject symlinked vendor roots and prefix-collision."""

    def test_symlinked_vendor_root_rejected(self, tmp_path: Path) -> None:
        """Vendor dir that is a symlink escaping candidate root is blocked."""
        root, _ = _build_candidate(tmp_path)
        # Create a real vendor outside root and symlink to it
        evil_vendor = tmp_path / "evil_vendor"
        evil_vendor.mkdir()
        (evil_vendor / "package.json").write_bytes(b'{"name":"evil"}')
        (evil_vendor / "package-lock.json").write_bytes(
            _minimal_lockfile(),
        )
        nm = evil_vendor / "node_modules" / "markdownlint-cli2"
        nm.mkdir(parents=True)

        # Replace vendor dir with symlink to evil
        vendor = root / "v"
        import shutil
        shutil.rmtree(vendor)
        os.symlink(str(evil_vendor), str(vendor))

        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "escapes" in r.stdout.lower() or "containment" in r.stdout.lower()

    def test_prefix_collision_rejected(self, tmp_path: Path) -> None:
        """Path like /tmp/candidate/v-evil must not pass for root /tmp/candidate/v."""
        root, _ = _build_candidate(tmp_path)
        # Create a sibling dir whose name is a prefix collision
        evil = tmp_path / "candidate" / "v-evil"
        evil.mkdir(parents=True)
        (evil / "package.json").write_bytes(b'{"name":"evil"}')

        # Try to use v-evil as vendor dir via symlink
        vendor = root / "v"
        import shutil
        shutil.rmtree(vendor)
        os.symlink(str(evil), str(vendor))

        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        # v-evil is still under candidate root, but vendor symlink resolves
        # outside the expected subtree. The containment check uses
        # is_relative_to so this is fine if evil is under root.
        # The real prefix collision test: evil dir is OUTSIDE root.
        evil_outside = tmp_path / "candidate-evil"
        evil_outside.mkdir(parents=True)
        (evil_outside / "package.json").write_bytes(b'{"name":"evil"}')
        vendor2 = root / "v2"
        os.symlink(str(evil_outside), str(vendor2))
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v2",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "escapes" in r.stdout.lower()

    def test_symlinked_parent_directory_rejected(self, tmp_path: Path) -> None:
        """Symlinked parent in path chain escapes containment."""
        root, _ = _build_candidate(tmp_path)
        escape_target = tmp_path / "outside"
        escape_target.mkdir()
        (escape_target / "verifier.py").write_bytes(b"evil-verifier")

        # Create a symlink inside root that points outside
        link_dir = root / "escape"
        os.symlink(str(escape_target), str(link_dir))

        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "escape/verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
        ])
        assert r.returncode == 1
        assert "escapes" in r.stdout.lower()


# ── Manifest tree coverage (every hash, symlink, mode, and set difference) ──

def _generate_manifest(vendor: Path) -> dict[str, Any]:
    """Build an INTEGRITY.json body that describes the current vendor tree.

    Mirrors the entry set the shipped verifier walks in
    `.claude/hooks/PreToolUse/_markdownlint_verifier.py`
    (`_materialize_verified_copy`): every file and symlink under the vendor
    root except `INTEGRITY.json` itself, plus the executable paths.
    """
    files: dict[str, str] = {}
    symlinks: dict[str, str] = {}
    executables: list[str] = []
    for item in sorted(vendor.rglob("*")):
        rel = str(item.relative_to(vendor))
        if rel == "INTEGRITY.json":
            continue
        if item.is_symlink():
            symlinks[rel] = os.readlink(item)
        elif item.is_file():
            files[rel] = _sha256(item.read_bytes())
            if os.access(item, os.X_OK):
                executables.append(rel)
    return {"files": files, "symlinks": symlinks, "executables": executables}


def _write_manifest(vendor: Path, manifest: object) -> None:
    _write(vendor / "INTEGRITY.json", json.dumps(manifest).encode())


def _run_manifest_case(root: Path) -> subprocess.CompletedProcess[str]:
    return _run([
        "--candidate-root", str(root),
        "--vendor-rel", "v",
        "--verifier-rel", "verifier.py",
        "--mirror-rel", "mirror.py",
        "--config-rel", "config.yaml",
    ])


def _candidate_with_manifest(tmp_path: Path) -> tuple[Path, Path]:
    """Build a candidate whose INTEGRITY.json describes its vendor tree."""
    root, _ = _build_candidate(tmp_path)
    vendor = root / "v"
    _write_manifest(vendor, _generate_manifest(vendor))
    return root, vendor


class TestManifestTreeCoverage:
    """Thread PRRT_kwDOQoWRls6YBJvt: validate every manifest entry, not one.

    A candidate can swap a dependency for a different canonical tarball,
    update the lockfile and vendored tree so reconstruction agrees, and keep
    the pinned INTEGRITY.json. Every case below is that attack shape.
    """

    def test_consistent_manifest_reports_pass(self, tmp_path: Path) -> None:
        """A manifest that describes the tree exactly clears this section."""
        root, _ = _candidate_with_manifest(tmp_path)
        r = _run_manifest_case(root)
        assert "PASS: Vendor tree matches every INTEGRITY.json entry" in r.stdout

    def test_swapped_dependency_content_rejected(self, tmp_path: Path) -> None:
        """Changed vendored bytes with a retained manifest are blocked."""
        root, vendor = _candidate_with_manifest(tmp_path)
        swapped = vendor / "node_modules" / "markdownlint-cli2" / "other.js"
        _write(swapped, b"original")
        _write_manifest(vendor, _generate_manifest(vendor))
        _write(swapped, b"swapped-tarball-content")

        r = _run_manifest_case(root)
        assert r.returncode == 1
        assert "Manifest hash mismatch: node_modules/markdownlint-cli2/other.js" in r.stdout

    def test_extra_tree_file_rejected(self, tmp_path: Path) -> None:
        """A vendor file the manifest never lists is blocked."""
        root, vendor = _candidate_with_manifest(tmp_path)
        _write(vendor / "node_modules" / "extra.js", b"extra")

        r = _run_manifest_case(root)
        assert r.returncode == 1
        assert "Files in vendor tree absent from manifest" in r.stdout
        assert "node_modules/extra.js" in r.stdout

    def test_missing_tree_file_rejected(self, tmp_path: Path) -> None:
        """A manifest entry deleted from the tree is blocked."""
        root, vendor = _candidate_with_manifest(tmp_path)
        (vendor / "package.json").unlink()

        r = _run_manifest_case(root)
        assert r.returncode == 1
        assert "Manifest entries missing from vendor tree" in r.stdout
        assert "package.json" in r.stdout

    def test_symlink_target_drift_rejected(self, tmp_path: Path) -> None:
        """A symlink retargeted inside the vendor tree is blocked."""
        root, vendor = _candidate_with_manifest(tmp_path)
        nm = vendor / "node_modules"
        _write(nm / "real.js", b"real")
        _write(nm / "decoy.js", b"decoy")
        link = nm / "link.js"
        os.symlink("real.js", str(link))
        _write_manifest(vendor, _generate_manifest(vendor))
        link.unlink()
        os.symlink("decoy.js", str(link))

        r = _run_manifest_case(root)
        assert r.returncode == 1
        assert "Manifest symlink target mismatch: node_modules/link.js" in r.stdout

    def test_symlink_replaced_by_regular_file_rejected(
        self, tmp_path: Path,
    ) -> None:
        """A symlink swapped for a regular file is blocked."""
        root, vendor = _candidate_with_manifest(tmp_path)
        nm = vendor / "node_modules"
        _write(nm / "real.js", b"real")
        link = nm / "link.js"
        os.symlink("real.js", str(link))
        _write_manifest(vendor, _generate_manifest(vendor))
        link.unlink()
        _write(link, b"real")

        r = _run_manifest_case(root)
        assert r.returncode == 1
        assert "Manifest symlink missing or not a symlink" in r.stdout

    def test_manifest_executable_without_exec_bit_rejected(
        self, tmp_path: Path,
    ) -> None:
        """A manifest executable that lost its mode bit is blocked."""
        root, vendor = _candidate_with_manifest(tmp_path)
        binary = vendor / "node_modules" / "tool.js"
        _write(binary, b"tool")
        binary.chmod(0o755)
        _write_manifest(vendor, _generate_manifest(vendor))
        binary.chmod(0o644)

        r = _run_manifest_case(root)
        assert r.returncode == 1
        assert "Manifest executables not executable in tree" in r.stdout

    def test_unlisted_executable_bit_rejected(self, tmp_path: Path) -> None:
        """Stricter than the shipped verifier: added exec bits are drift."""
        root, vendor = _candidate_with_manifest(tmp_path)
        plain = vendor / "node_modules" / "plain.js"
        _write(plain, b"plain")
        _write_manifest(vendor, _generate_manifest(vendor))
        plain.chmod(0o755)

        r = _run_manifest_case(root)
        assert r.returncode == 1
        assert "Executable files absent from manifest executables" in r.stdout
        assert "node_modules/plain.js" in r.stdout

    def test_non_object_manifest_rejected(self, tmp_path: Path) -> None:
        """A JSON array manifest fails closed instead of crashing."""
        root, _ = _build_candidate(tmp_path, manifest_content=b'["files"]')
        r = _run_manifest_case(root)
        assert r.returncode == 1
        assert "INTEGRITY.json is not a JSON object" in r.stdout
        assert "Traceback" not in r.stderr

    def test_wrong_section_shape_rejected(self, tmp_path: Path) -> None:
        """A manifest whose sections have the wrong JSON type is blocked."""
        root, vendor = _candidate_with_manifest(tmp_path)
        _write_manifest(
            vendor,
            {"files": ["a.js"], "symlinks": {}, "executables": "all"},
        )
        r = _run_manifest_case(root)
        assert r.returncode == 1
        assert "Manifest 'files' is not a mapping of path to string" in r.stdout
        assert "Manifest 'executables' is not a list of paths" in r.stdout
        assert "Traceback" not in r.stderr


# ── Candidate materialization (export-ignore trap) ──────────────────────────

def _git(
    cwd: Path, env: dict[str, str], *args: str,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc


def _git_env(home: Path) -> dict[str, str]:
    """Isolate Git from developer and system configuration."""
    home.mkdir(parents=True, exist_ok=True)
    (home / "gitconfig").write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.update({
        "GIT_CONFIG_GLOBAL": str(home / "gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(home),
    })
    return env


def _commit_candidate_repo(repo: Path, env: dict[str, str]) -> str:
    _git(repo.parent, env, "init", "-q", "-b", "main", str(repo))
    _git(repo, env, "config", "user.email", "ci@example.com")
    _git(repo, env, "config", "user.name", "ci")
    _git(repo, env, "add", "-A")
    _git(repo, env, "commit", "-qm", "candidate commit")
    return _git(repo, env, "rev-parse", "HEAD").stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
class TestCandidateMaterialization:
    """Thread PRRT_kwDOQoWRls6YABvq: candidate `.gitattributes` must not hide files.

    `git archive` honours `export-ignore` from the candidate commit, so a PR
    could mark a vendor file `export-ignore`, keep it in the tree that merges,
    and keep it out of the extracted candidate the gate inspects. The workflow
    materializes through a temporary index instead, the same control
    `scripts/ci/merge_tree_materialization.py` uses and
    `tests/ci/test_merge_tree_materialization.py::test_export_ignored_scored_file_is_still_materialized`
    covers for the merge ratchets.
    """

    def test_export_ignored_vendor_file_reaches_the_gate(
        self, tmp_path: Path,
    ) -> None:
        """An export-ignored vendor file is materialized and then blocked."""
        from scripts.ci.merge_tree_materialization import materialize_tree

        repo = tmp_path / "repo"
        repo.mkdir()
        root, vendor = _candidate_with_manifest(repo)
        hidden_rel = "candidate/v/node_modules/hidden.js"
        _write(repo / hidden_rel, b"hidden-payload")
        _write(repo / ".gitattributes", f"{hidden_rel} export-ignore\n".encode())
        env = _git_env(tmp_path / "git-home")
        head = _commit_candidate_repo(repo, env)

        archive = tmp_path / "candidate.tar"
        _git(repo, env, "archive", "--format=tar", "--output", str(archive), head)
        with tarfile.open(archive) as tar:
            archived = set(tar.getnames())
        # Witness the trap: the archive path drops the file the tree keeps.
        assert "candidate/v/package.json" in archived
        assert hidden_rel not in archived

        destination = tmp_path / "materialized"
        assert materialize_tree(repo, head, destination)
        assert (destination / hidden_rel).is_file()

        r = _run_manifest_case(destination / "candidate")
        assert r.returncode == 1
        assert "Files in vendor tree absent from manifest" in r.stdout
        assert "node_modules/hidden.js" in r.stdout
        assert vendor.is_dir()


# ── CLI2 config authentication (fail closed) ────────────────────────────────
class TestCli2ConfigAuth:
    """Thread 2: missing CLI2 config fails closed when arg is supplied."""

    def test_missing_cli2_config_fails_closed(self, tmp_path: Path) -> None:
        """Supplying --cli2-config-rel for a deleted file must fail."""
        root, _ = _build_candidate(tmp_path)
        cli2_path = root / "cli2.yaml"
        cli2_path.unlink()  # delete the file

        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
            "--cli2-config-rel", "cli2.yaml",
        ])
        assert r.returncode == 1
        # Should report missing file, not silently skip
        assert "not found" in r.stdout.lower() or "cannot resolve" in r.stdout.lower()

    def test_present_cli2_config_authenticated(self, tmp_path: Path) -> None:
        """Present CLI2 config with wrong hash is rejected."""
        root, _ = _build_candidate(tmp_path, cli2_config_content=b"wrong")
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
            "--cli2-config-rel", "cli2.yaml",
        ])
        assert r.returncode == 1
        assert "CLI2 config" in r.stdout and "mismatch" in r.stdout


# ── Copilot config mirror parity ─────────────────────────────────────────────

class TestCopilotConfigMirrorParity:
    """Thread 3: Copilot config mirrors enforced for byte parity."""

    def test_mismatched_copilot_config_rejected(self, tmp_path: Path) -> None:
        """Copilot safe-config differing from primary is rejected."""
        root, _ = _build_candidate(tmp_path, config_content=b"primary-cfg")
        copilot_cfg = root / "copilot-config.yaml"
        _write(copilot_cfg, b"different-cfg")
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
            "--copilot-config-rel", "copilot-config.yaml",
        ])
        assert r.returncode == 1
        assert "Parity mismatch" in r.stdout

    def test_mismatched_copilot_cli2_config_rejected(self, tmp_path: Path) -> None:
        """Copilot CLI2 config differing from primary CLI2 is rejected."""
        root, _ = _build_candidate(tmp_path, cli2_config_content=b"primary-cli2")
        copilot_cli2 = root / "copilot-cli2.yaml"
        _write(copilot_cli2, b"different-cli2")
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
            "--cli2-config-rel", "cli2.yaml",
            "--copilot-cli2-config-rel", "copilot-cli2.yaml",
        ])
        assert r.returncode == 1
        assert "Parity mismatch" in r.stdout

    def test_copilot_config_with_execution_key_rejected(
        self, tmp_path: Path,
    ) -> None:
        """Copilot config with execution key rejected even if parity matches."""
        evil_cfg = b"customRules:\n  - ./evil.js\n"
        root, _ = _build_candidate(tmp_path, config_content=evil_cfg)
        copilot_cfg = root / "copilot-config.yaml"
        _write(copilot_cfg, evil_cfg)  # byte-identical but evil
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
            "--copilot-config-rel", "copilot-config.yaml",
        ])
        assert r.returncode == 1
        assert "customRules" in r.stdout

    def test_matching_copilot_mirrors_pass_parity(self, tmp_path: Path) -> None:
        """Byte-identical Copilot mirrors do not add parity errors."""
        cfg = b"config:\n  MD040: true\n"
        cli2 = b"config:\n  MD024: true\n"
        root, _ = _build_candidate(
            tmp_path, config_content=cfg, cli2_config_content=cli2,
        )
        copilot_cfg = root / "copilot-config.yaml"
        copilot_cli2 = root / "copilot-cli2.yaml"
        _write(copilot_cfg, cfg)
        _write(copilot_cli2, cli2)
        r = _run([
            "--candidate-root", str(root),
            "--vendor-rel", "v",
            "--verifier-rel", "verifier.py",
            "--mirror-rel", "mirror.py",
            "--config-rel", "config.yaml",
            "--cli2-config-rel", "cli2.yaml",
            "--copilot-config-rel", "copilot-config.yaml",
            "--copilot-cli2-config-rel", "copilot-cli2.yaml",
        ])
        # Will still fail on pin mismatch, but NOT on parity
        assert "Parity mismatch" not in r.stdout


# ── Workflow contract: both mirror arguments present ─────────────────────────

# Matches an ``astral-sh/setup-uv`` reference pinned to a full 40-character
# commit SHA. Shared by the contract test and its discrimination probe so the
# property asserted and the property proven falsifiable are the same pattern,
# not two that could drift apart.
_SETUP_UV_PIN_RE = re.compile(r"astral-sh/setup-uv@[0-9a-f]{40}\b")


class TestWorkflowContract:
    """Verify the workflow YAML passes both Copilot mirror args."""

    def test_workflow_sets_up_uv(self) -> None:
        """vendor-provenance.yml must install uv, from a SHA-pinned action.

        Two properties, taken from the two fixes that met here.

        Structural, from PR #5219: parse the ``provenance`` job's steps and
        assert on the single ``Setup uv`` step's ``uses`` field rather than
        searching the file as text. A substring match still passes if the step
        is deleted and its ``uses:`` line survives in a comment or on an
        unrelated step (testing.md MUST 9).

        Drift-proof, from PR #5209: do not restate the SHA. Renovate bumps the
        pin and a duplicated literal turns every bump into an identical red
        run. PR #5215 moved this action from ae62891f to 20cfd1bf, the
        workflow changed, the test did not, and it went red on main for a
        reason unrelated to anything it tests. Asserting the pin *shape*, a
        full 40-character commit SHA rather than a floating tag
        (universal.md MUST-8), keeps the real contract and survives the bump.

        Restating a SHA is right only when the assertion depends on that
        specific build. Contrast
        ``tests/ci/test_pytest_paths_filter_covers_episodes.py``, where the
        duplicated ``dorny/paths-filter`` SHA is load-bearing because that test
        models the action's internal ``MatchOptions``. This one does not.
        """
        import yaml

        wf = Path(".github/workflows/vendor-provenance.yml").read_text()
        steps = yaml.safe_load(wf)["jobs"]["provenance"]["steps"]
        setup_uv_steps = [step for step in steps if step.get("name") == "Setup uv"]
        assert len(setup_uv_steps) == 1, "expected exactly one 'Setup uv' step"
        uses = setup_uv_steps[0]["uses"]
        assert _SETUP_UV_PIN_RE.fullmatch(uses), (
            f"'Setup uv' must use astral-sh/setup-uv pinned to a full commit "
            f"SHA; found {uses!r}"
        )

    def test_setup_uv_pin_pattern_rejects_an_unpinned_reference(self) -> None:
        """The pin detector goes dead on every shape it is meant to reject.

        ``test_workflow_sets_up_uv`` matches a pattern against a value that
        already satisfies it, so on its own that assertion proves nothing: a
        pattern loose enough to match anything would pass it too. This is the
        discriminating half (testing.md SHOULD 17). Each value below is a real
        way the pin could regress, and each must fail to match.
        """
        rejected = {
            "floating major tag": "astral-sh/setup-uv@v10",
            "floating semver tag": "astral-sh/setup-uv@v10.0.1",
            "branch ref": "astral-sh/setup-uv@main",
            "abbreviated sha": "astral-sh/setup-uv@20cfd1bf",
            "uppercase sha": "astral-sh/setup-uv@" + "A" * 40,
            "different action": "actions/setup-python@" + "a" * 40,
            "trailing junk": "astral-sh/setup-uv@" + "0" * 40 + "x",
        }
        for label, value in rejected.items():
            assert _SETUP_UV_PIN_RE.fullmatch(value) is None, (
                f"pin detector matched {label!r}, so it cannot fail and proves "
                f"nothing about the real workflow"
            )

        accepted = "astral-sh/setup-uv@" + "0" * 40
        assert _SETUP_UV_PIN_RE.fullmatch(accepted) is not None, (
            "pin detector rejected a correctly SHA-pinned reference"
        )

    def test_required_check_context_matches_job_name(self) -> None:
        """The documented required-check context must be the emitted context.

        GitHub reports a job's ``name:`` as the check-run context; the
        workflow-level ``name:`` is never emitted as a context. A rollout
        instruction naming the workflow would leave branch protection waiting
        on a context that never arrives, so the documented context is pinned
        to the job name here and drifts loudly instead of silently.
        """
        import yaml

        wf = Path(".github/workflows/vendor-provenance.yml").read_text()
        job_name = yaml.safe_load(wf)["jobs"]["provenance"]["name"]
        assert f"\n# Required status check context: {job_name}\n" in wf

    def test_workflow_runs_validator_with_uv_frozen(self) -> None:
        """vendor-provenance.yml must run the validator in the uv env."""
        wf = Path(".github/workflows/vendor-provenance.yml").read_text()
        assert "uv run --frozen python scripts/ci/validate_vendor_provenance.py" in wf
        assert "python3 scripts/ci/validate_vendor_provenance.py" not in wf

    def test_workflow_materializes_candidate_tree_without_archive(self) -> None:
        """Candidate materialization must ignore export-ignore attributes."""
        wf = Path(".github/workflows/vendor-provenance.yml").read_text()
        assert "materialize_tree(Path.cwd(), sys.argv[1], Path(sys.argv[2]))" in wf
        assert "git archive" not in wf

    def test_workflow_uses_runner_temp_candidate_root(self) -> None:
        """Candidate root must come from runner temp, not a hard-coded path."""
        wf = Path(".github/workflows/vendor-provenance.yml").read_text()
        assert 'CANDIDATE_ROOT="$RUNNER_TEMP/candidate"' in wf
        assert '--candidate-root "$CANDIDATE_ROOT"' in wf

    def test_workflow_passes_copilot_config_rel(self) -> None:
        """vendor-provenance.yml must pass --copilot-config-rel."""
        wf = Path(".github/workflows/vendor-provenance.yml").read_text()
        assert "--copilot-config-rel" in wf

    def test_workflow_passes_copilot_cli2_config_rel(self) -> None:
        """vendor-provenance.yml must pass --copilot-cli2-config-rel."""
        wf = Path(".github/workflows/vendor-provenance.yml").read_text()
        assert "--copilot-cli2-config-rel" in wf

    def test_workflow_copilot_config_points_to_src_copilot_cli(self) -> None:
        """Copilot config path must be under src/copilot-cli."""
        wf = Path(".github/workflows/vendor-provenance.yml").read_text()
        assert "src/copilot-cli/hooks/PreToolUse/markdownlint-safe-config.yaml" in wf

    def test_workflow_copilot_cli2_config_points_to_src_copilot_cli(self) -> None:
        """Copilot CLI2 config path must be under src/copilot-cli."""
        wf = Path(".github/workflows/vendor-provenance.yml").read_text()
        assert "src/copilot-cli/hooks/PreToolUse/markdownlint-cli2.yaml" in wf
