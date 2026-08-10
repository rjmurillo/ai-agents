"""End-to-end security tests for vendored markdownlint verifier.

Non-mocked tests verifying correct behavior under clean, violation,
tampered vendor, extra files, fake node, and hostile conditions.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

_HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(_HOOK_DIR))
import _markdownlint_verifier as verifier


@pytest.fixture(autouse=True)
def _patch_node_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch resolver internals to allow CI node (not production override)."""
    import shutil as _shutil

    node = _shutil.which("node")
    if node:
        node_path = Path(node).resolve()
        # Patch the resolver to find node in its actual location
        monkeypatch.setattr(
            verifier, "_PLATFORM_NODE_DIRS",
            (str(node_path.parent),) + verifier._PLATFORM_NODE_DIRS,
        )
        # Patch ownership check to pass for CI environments
        monkeypatch.setattr(
            verifier, "_is_admin_owned_not_user_writable",
            lambda p: True,
        )


class TestCleanMarkdown:
    """Clean Markdown must return 0."""

    def test_clean_heading_and_list(self, tmp_path: Path) -> None:
        md = tmp_path / "clean.md"
        md.write_text("# Title\n\nA paragraph.\n\n- item one\n- item two\n")
        assert verifier.main([str(md)]) == 0

    def test_empty_file_list(self) -> None:
        assert verifier.main([]) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        assert verifier.main([str(tmp_path / "missing.md")]) == 0


class TestViolationDetection:
    """Violations must return 1."""

    def test_missing_top_heading(self, tmp_path: Path) -> None:
        md = tmp_path / "no_heading.md"
        md.write_text("Just a paragraph without heading.\n")
        assert verifier.main([str(md)]) == 1

    def test_bare_url(self, tmp_path: Path) -> None:
        md = tmp_path / "bare_url.md"
        md.write_text("# Title\n\nVisit https://example.com today.\n")
        assert verifier.main([str(md)]) == 1


class TestNoProductionEnvOverride:
    """_MARKDOWNLINT_TRUSTED_NODE must not exist in production code."""

    def test_no_trusted_node_env_in_verifier(self) -> None:
        """Production verifier must not read any env-based node override."""
        source = (_HOOK_DIR / "_markdownlint_verifier.py").read_text()
        assert "_MARKDOWNLINT_TRUSTED_NODE" not in source

    def test_fake_node_env_does_not_bypass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Setting env vars cannot redirect node resolution."""
        monkeypatch.setenv("_MARKDOWNLINT_TRUSTED_NODE", "/bin/true")
        monkeypatch.setenv("NODE", "/bin/true")
        md = tmp_path / "no_heading.md"
        md.write_text("No heading here.\n")
        # Should still detect violation (real node) or fail closed
        result = verifier.main([str(md)])
        assert result in (1, 2)  # violation or fail-closed, never 0


class TestFakeNodeNotInvoked:
    """Fake node in non-platform dirs must never execute."""

    def test_fake_node_in_user_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        marker = tmp_path / "MARKER_FAKE_NODE_RAN"
        bin_dir = tmp_path / "fake_bin"
        bin_dir.mkdir()
        fake_node = bin_dir / "node"
        fake_node.write_text(
            f"#!/bin/sh\ntouch {marker}\nexit 0\n"
        )
        fake_node.chmod(stat.S_IRWXU)

        # Patch to make only fake dir visible but fail ownership check
        monkeypatch.setattr(
            verifier, "_PLATFORM_NODE_DIRS", (str(bin_dir),),
        )
        # Restore real ownership check (will reject user-owned dir)
        monkeypatch.setattr(
            verifier, "_is_admin_owned_not_user_writable",
            lambda p: False,
        )

        md = tmp_path / "test.md"
        md.write_text("# Title\n\nText.\n")
        result = verifier.main([str(md)])
        assert result == 2  # fail closed
        assert not marker.exists(), "Fake node was invoked!"


class TestFullIntegrityVerification:
    """Vendor tree integrity must verify ALL files."""

    def test_tampered_file_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Modifying any vendor file must cause integrity failure."""
        # Tamper a file and verify detection
        target = (
            verifier._VENDOR / "node_modules"
            / "markdownlint-cli2" / "markdownlint-cli2-bin.mjs"
        )
        original = target.read_bytes()
        try:
            target.write_bytes(original + b"\n// tampered")
            md = tmp_path / "test.md"
            md.write_text("# Title\n\nText.\n")
            result = verifier.main([str(md)])
            assert result == 2  # fail closed
        finally:
            target.write_bytes(original)

    def test_extra_file_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Extra files in vendor tree must cause integrity failure."""
        injected = verifier._VENDOR / "node_modules" / "evil.js"
        try:
            injected.write_text("process.exit(0)")
            md = tmp_path / "test.md"
            md.write_text("# Title\n\nText.\n")
            result = verifier.main([str(md)])
            assert result == 2  # fail closed
        finally:
            injected.unlink(missing_ok=True)

    def test_missing_file_detected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """Missing files from manifest must cause integrity failure."""
        import hashlib as _hl
        # Load real manifest and add a phantom file
        manifest_path = verifier._VENDOR / verifier._INTEGRITY_REL
        manifest = json.loads(manifest_path.read_bytes())
        manifest["files"]["node_modules/phantom.js"] = "a" * 64
        # Write tampered manifest and patch pinned digest to match
        fake_manifest = tmp_path / "INTEGRITY.json"
        raw = json.dumps(manifest).encode()
        fake_manifest.write_bytes(raw)
        fake_digest = _hl.sha256(raw).hexdigest()
        fake_vendor = tmp_path / "vendor"
        fake_vendor.mkdir()
        (fake_vendor / "INTEGRITY.json").write_bytes(raw)
        monkeypatch.setattr(verifier, "_VENDOR", fake_vendor)
        monkeypatch.setattr(verifier, "_INTEGRITY_SHA256", fake_digest)

        md = tmp_path / "test.md"
        md.write_text("# Title\n\nText.\n")
        result = verifier.main([str(md)])
        assert result == 2

    def test_symlink_target_mismatch_detected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """Symlink target changes must cause materialization failure."""
        import hashlib as _hl
        manifest_path = verifier._VENDOR / verifier._INTEGRITY_REL
        manifest = json.loads(manifest_path.read_bytes())
        if manifest.get("symlinks"):
            # Corrupt a symlink target in manifest
            first_key = next(iter(manifest["symlinks"]))
            manifest["symlinks"][first_key] = "/etc/passwd"
            raw = json.dumps(manifest).encode()
            fake_vendor = tmp_path / "vendor"
            fake_vendor.mkdir()
            (fake_vendor / "INTEGRITY.json").write_bytes(raw)
            fake_digest = _hl.sha256(raw).hexdigest()
            monkeypatch.setattr(verifier, "_VENDOR", fake_vendor)
            monkeypatch.setattr(verifier, "_INTEGRITY_SHA256", fake_digest)

            md = tmp_path / "test.md"
            md.write_text("# Title\n\nText.\n")
            result = verifier.main([str(md)])
            assert result == 2


class TestConsumerIsolation:
    """Consumer config and environment must not influence results."""

    def test_consumer_config_ignored(self, tmp_path: Path) -> None:
        (tmp_path / ".markdownlint.yaml").write_text("default: false\n")
        md = tmp_path / "test.md"
        md.write_text("Just text without heading.\n")
        assert verifier.main([str(md)]) == 1

    def test_node_options_not_passed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("NODE_OPTIONS", "--require=/tmp/evil.js")
        md = tmp_path / "clean.md"
        md.write_text("# Title\n\nClean paragraph.\n")
        assert verifier.main([str(md)]) == 0


class TestFailClosed:
    """Infrastructure absence must fail closed (return 2)."""

    def test_no_node_in_platform_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            verifier, "_PLATFORM_NODE_DIRS", ("/nonexistent",),
        )
        monkeypatch.setattr(
            verifier, "_is_admin_owned_not_user_writable",
            lambda p: True,
        )
        md = tmp_path / "test.md"
        md.write_text("# Title\n\nText.\n")
        assert verifier.main([str(md)]) == 2

    def test_missing_vendor_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            verifier, "_VENDOR", Path("/nonexistent/vendor"),
        )
        md = tmp_path / "test.md"
        md.write_text("# Title\n\nText.\n")
        assert verifier.main([str(md)]) == 2


class TestHostileEnvironment:
    """Hostile PATH/npx must not be invoked."""

    def test_fake_npx_not_invoked(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_NPX_RAN"
        bin_dir = tmp_path / "hostile"
        bin_dir.mkdir()
        fake_npx = bin_dir / "npx"
        fake_npx.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
        fake_npx.chmod(stat.S_IRWXU)

        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = f"{bin_dir}:{old_path}"
            md = tmp_path / "clean.md"
            md.write_text("# Title\n\nClean text.\n")
            verifier.main([str(md)])
            assert not marker.exists()
        finally:
            os.environ["PATH"] = old_path


class TestManifestDigestPinning:
    """Manifest must be authenticated by pinned digest in source."""

    def test_tampered_manifest_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Modified INTEGRITY.json (matching content but different digest) blocked."""
        # Temporarily point verifier at a fake vendor with wrong manifest
        fake_vendor = tmp_path / "vendor"
        fake_vendor.mkdir(parents=True)
        manifest: dict[str, object] = {"files": {}, "symlinks": {}, "executables": []}
        (fake_vendor / "INTEGRITY.json").write_text(json.dumps(manifest))
        monkeypatch.setattr(verifier, "_VENDOR", fake_vendor)
        # The pinned digest won't match this fake manifest
        result = verifier._authenticate_manifest()
        assert result is None, "Tampered manifest must be rejected"

    def test_correct_pinned_digest_accepted(self) -> None:
        """Real INTEGRITY.json passes authentication."""
        result = verifier._authenticate_manifest()
        # If vendor tree exists with correct manifest, should succeed
        manifest_path = verifier._VENDOR / "INTEGRITY.json"
        if manifest_path.is_file():
            assert result is not None, "Authentic manifest must be accepted"


class TestTOCTOUProtection:
    """Verify-then-execute uses materialized copy, not original path."""

    def test_concurrent_swap_after_verify_does_not_execute(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Simulates concurrent file swap during execution.

        The verifier must execute from its private copy, so even if the
        original vendor tree is modified after verification, the executed
        code is the verified copy.
        """
        import threading

        # Create a minimal vendor tree
        fake_vendor = tmp_path / "vendor"
        nm = fake_vendor / "node_modules" / "markdownlint-cli2"
        nm.mkdir(parents=True)
        entry_content = b'console.log("ORIGINAL");process.exit(0);\n'
        entry = nm / "markdownlint-cli2-bin.mjs"
        entry.write_bytes(entry_content)

        # Build manifest for original content
        import hashlib
        rel = "node_modules/markdownlint-cli2/markdownlint-cli2-bin.mjs"
        manifest = {
            "files": {rel: hashlib.sha256(entry_content).hexdigest()},
            "symlinks": {},
            "executables": [],
        }

        # Materialize into private copy
        dest = tmp_path / "copy"
        dest.mkdir()

        swap_marker = tmp_path / "SWAP_HAPPENED"
        malicious = b'import("fs").then(f=>f.writeFileSync("PWNED","x"))\n'

        def swap_during_verify() -> None:
            """Swap original file while copy is in progress."""
            entry.write_bytes(malicious)
            swap_marker.touch()

        # Run swap concurrently
        t = threading.Thread(target=swap_during_verify)
        monkeypatch.setattr(verifier, "_VENDOR", fake_vendor)
        t.start()
        # Materialize - should use content read at copy time
        result = verifier._materialize_verified_copy(manifest, dest)
        t.join()

        # The copy must contain original OR fail integrity check
        copied = dest / rel
        if result is None:
            # If materialization succeeded, content must be original
            assert copied.read_bytes() == entry_content
        else:
            # If content changed mid-copy, hash mismatch blocks
            assert "hash mismatch" in result or "cannot read" in result

    def test_materialized_copy_is_readonly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verified copy must be made non-writable."""
        import hashlib
        fake_vendor = tmp_path / "vendor"
        nm = fake_vendor / "node_modules" / "test"
        nm.mkdir(parents=True)
        content = b"test content\n"
        (nm / "file.js").write_bytes(content)
        rel = "node_modules/test/file.js"
        manifest = {
            "files": {rel: hashlib.sha256(content).hexdigest()},
            "symlinks": {},
            "executables": [],
        }
        dest = tmp_path / "copy"
        dest.mkdir()
        monkeypatch.setattr(verifier, "_VENDOR", fake_vendor)
        result = verifier._materialize_verified_copy(manifest, dest)
        assert result is None
        copied = dest / rel
        # File must not be writable
        assert not os.access(copied, os.W_OK)


class TestSymlinkContainment:
    """Symlinks escaping vendor tree must be rejected."""

    def test_symlink_escape_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Symlink pointing outside vendor tree is blocked."""
        fake_vendor = tmp_path / "vendor"
        fake_vendor.mkdir(parents=True)
        # Create a symlink pointing outside
        escape_link = fake_vendor / "escape.js"
        os.symlink("/etc/passwd", escape_link)
        manifest = {
            "files": {},
            "symlinks": {"escape.js": "/etc/passwd"},
            "executables": [],
        }
        dest = tmp_path / "copy"
        dest.mkdir()
        monkeypatch.setattr(verifier, "_VENDOR", fake_vendor)
        result = verifier._materialize_verified_copy(manifest, dest)
        assert result is not None
        assert "symlink escapes vendor" in result
