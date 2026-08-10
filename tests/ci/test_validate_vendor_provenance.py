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

class TestWorkflowContract:
    """Verify the workflow YAML passes both Copilot mirror args."""

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
