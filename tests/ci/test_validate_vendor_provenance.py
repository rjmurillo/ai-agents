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
from pathlib import Path, PurePosixPath

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
# New test classes to append

class TestMissingPinnedFile:
    """Defect fix: missing pinned artifacts must be rejected, not silently skipped."""

    def test_missing_bootstrap_rejected(self, tmp_path: Path) -> None:
        """Candidate without _bootstrap.py fails authentication."""
        root = tmp_path / "c"
        root.mkdir()
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "pinned file missing" in r.stdout

    def test_vendor_artifact_absent_ok(self, tmp_path: Path) -> None:
        """Vendor-only pins are allowed to be absent (not yet landed)."""
        import shutil

        from scripts.ci.validate_vendor_provenance import (
            _PINNED_ARTIFACTS,
            _is_vendor_only,
        )
        root = tmp_path / "c"
        repo = Path(__file__).resolve().parents[2]
        for rel, _sha, _label in _PINNED_ARTIFACTS:
            if _is_vendor_only(rel):
                continue  # Skip vendor-only
            src = repo / rel
            dst = root / rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 0, f"Expected 0, got {r.returncode}:\n{r.stdout}"


class TestSymlinkOnPinnedFile:
    """Defect fix: symlinks on pinned files must be rejected."""

    def test_symlink_bootstrap_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        target = root / "real_bootstrap.py"
        link = root / ".claude/hooks/PreToolUse/_bootstrap.py"
        link.parent.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"# real content")
        os.symlink(str(target), str(link))
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "symlink" in r.stdout.lower()


class TestLibImportClosureTamper:
    """Defect fix: lib files must be pinned and tamper-detected."""

    def test_tampered_lib_hook_dispatch_rejected(self, tmp_path: Path) -> None:
        import shutil

        from scripts.ci.validate_vendor_provenance import (
            _PINNED_ARTIFACTS,
            _is_vendor_only,
        )
        root = tmp_path / "c"
        repo = Path(__file__).resolve().parents[2]
        for rel, _sha, _label in _PINNED_ARTIFACTS:
            if _is_vendor_only(rel):
                continue
            src = repo / rel
            dst = root / rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        # Tamper a lib file
        lib_file = root / ".claude/lib/hook_dispatch.py"
        if lib_file.is_file():
            lib_file.write_text("# TAMPERED\nimport os; os.system('evil')\n")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "mismatch" in r.stdout.lower()
        assert "hook_dispatch.py" in r.stdout

    def test_unpinned_new_lib_file_flagged(self, tmp_path: Path) -> None:
        root = tmp_path / "c"
        evil = root / ".claude/lib/evil_module.py"
        evil.parent.mkdir(parents=True, exist_ok=True)
        evil.write_text("# malicious import")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "Unpinned executable" in r.stdout
        assert "evil_module.py" in r.stdout


class TestWorkflowRelevanceDiff:
    """Defect fix: relevance must use git diff, not candidate existence.

    These tests validate the Python-level validator behavior. Workflow-level
    diff logic runs in CI shell steps and is tested by CI itself.
    The validator always runs when invoked; relevance is a workflow concern.
    """

    def test_validator_runs_on_empty_candidate(self, tmp_path: Path) -> None:
        """Validator still returns errors for empty candidate (missing pins)."""
        root = tmp_path / "c"
        root.mkdir()
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "pinned file missing" in r.stdout


def _make_valid_candidate(tmp_path: Path) -> Path:
    """Build a candidate tree that passes all validator checks."""
    import shutil as _shutil

    from scripts.ci.validate_vendor_provenance import _PINNED_ARTIFACTS

    root = tmp_path / "candidate"
    repo = Path(__file__).resolve().parents[2]
    for rel, _sha, _label in _PINNED_ARTIFACTS:
        src = repo / rel
        dst = root / rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            _shutil.copy2(src, dst)
    for extra in [
        "src/copilot-cli/hooks/PreToolUse/_dispatch.py",
        "src/copilot-cli/hooks/PreToolUse/_manifest.json",
    ]:
        ef = root / extra
        if not ef.exists():
            _write(ef, b"# non-executable placeholder")
    return root


class TestConfigSafetyNoPyYAML:
    """Validates the single deterministic regex path (no PyYAML needed)."""

    def test_no_pyyaml_dependency_needed(self, tmp_path: Path) -> None:
        """Validator works without PyYAML (regex-only path)."""
        root = _make_valid_candidate(tmp_path)
        cfg = root / ".claude" / "hooks" / "PreToolUse" / "markdownlint-safe-config.yaml"
        _write(cfg, "config:\n  MD040: true\n")
        # Place a fake yaml.py that raises ImportError - should not affect result
        fake = tmp_path / "fake_yaml"
        fake.mkdir()
        _write(fake / "yaml.py", "raise ImportError('yaml blocked for test')\n")
        env = {**os.environ, "PYTHONPATH": str(fake), "PYTHONDONTWRITEBYTECODE": "1"}
        r = subprocess.run(
            [sys.executable, str(WT / SCRIPT), "--candidate-root", str(root)],
            capture_output=True, encoding="utf-8", errors="replace",
            env=env,
        )
        # Should still pass: regex path does not need PyYAML
        assert r.returncode == 0

    def test_yaml_mapping_key_customrules_blocked(self, tmp_path: Path) -> None:
        """YAML explicit mapping key '? customRules' is detected."""
        root = _make_valid_candidate(tmp_path)
        cfg = root / ".claude" / "hooks" / "PreToolUse" / "markdownlint-safe-config.yaml"
        # Explicit YAML block mapping key that bypassed the old regex fallback
        _write(cfg, "? customRules\n: [evil]\n")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "customRules" in r.stdout

    def test_malformed_yaml_with_exec_key_fails(self, tmp_path: Path) -> None:
        """Malformed YAML containing exec keys still caught by regex."""
        root = _make_valid_candidate(tmp_path)
        cfg = root / ".claude" / "hooks" / "PreToolUse" / "markdownlint-safe-config.yaml"
        _write(cfg, "{{{\ncustomRules: [evil\n")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "customRules" in r.stdout

    def test_non_utf8_config_fails_closed(self, tmp_path: Path) -> None:
        """Non-UTF-8 config fails closed (cannot scan for keys)."""
        root = _make_valid_candidate(tmp_path)
        cfg = root / ".claude" / "hooks" / "PreToolUse" / "markdownlint-safe-config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_bytes(b"\xff\xfe\x00\x01" * 20)
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "UTF-8" in r.stdout


class TestWorkflowContractRegression:
    """HIGH-2 fix: workflow-contract tests for deletion/rename/directory scenarios.

    The validator itself does not implement diff logic (that's the workflow shell).
    These tests verify the validator catches scenarios that deletion-unaware
    relevance would miss: when watched files are removed, the validator must
    still detect issues (missing pins, unpinned files, etc.)
    """

    def test_lib_tamper_detected_via_validator(self, tmp_path: Path) -> None:
        """Tampered lib file caught even if relevance only triggers on addition."""
        root = _make_valid_candidate(tmp_path)
        # Tamper a lib file
        lib = root / ".claude" / "lib" / "hook_dispatch.py"
        if lib.exists():
            lib.write_text("# tampered\n")
        else:
            _write(lib, "# tampered\n")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "hook_dispatch" in r.stdout

    def test_whole_watched_file_deletion_fails(self, tmp_path: Path) -> None:
        """If a pinned file is deleted from candidate, validator catches it."""
        root = _make_valid_candidate(tmp_path)
        # Remove a pinned hook file
        bootstrap = root / ".claude" / "hooks" / "PreToolUse" / "_bootstrap.py"
        if bootstrap.exists():
            bootstrap.unlink()
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        assert "pinned file missing" in r.stdout or "_bootstrap" in r.stdout

    def test_whole_watched_directory_deletion_fails(self, tmp_path: Path) -> None:
        """If entire watched dir is removed from candidate, validator catches it."""
        root = _make_valid_candidate(tmp_path)
        import shutil
        lib_dir = root / ".claude" / "lib"
        if lib_dir.is_dir():
            shutil.rmtree(lib_dir)
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 1
        # Missing pinned lib files should be detected
        assert "pinned file missing" in r.stdout or "lib" in r.stdout.lower()

    def test_unrelated_candidate_no_watched_changes(self, tmp_path: Path) -> None:
        """Validator with complete valid candidate passes (unrelated change ok)."""
        root = _make_valid_candidate(tmp_path)
        # Add an unrelated file outside watched prefixes
        _write(root / "docs" / "readme.md", "# Hello\n")
        r = _run(["--candidate-root", str(root)])
        assert r.returncode == 0


# ── Config safety: deterministic regex path (no PyYAML) ──

class TestConfigSafetyDeterministic:
    """Exercises the single regex-based config safety path directly.

    These tests import _validate_config_safe and verify it detects
    execution-capable keys in all YAML key syntactic forms without PyYAML.
    """

    def _cfg(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "test.yaml"
        p.write_text(content)
        return p

    def test_block_mapping_explicit_key_rejected(self, tmp_path: Path) -> None:
        """YAML '? customRules' syntax must be caught."""
        from scripts.ci.validate_vendor_provenance import _validate_config_safe

        p = self._cfg(tmp_path, "? customRules\n: [evil]\n")
        errors = _validate_config_safe(p)
        assert any("customRules" in e for e in errors), f"Expected rejection: {errors}"

    def test_bare_key_rejected(self, tmp_path: Path) -> None:
        from scripts.ci.validate_vendor_provenance import _validate_config_safe

        p = self._cfg(tmp_path, "customRules:\n  - x\n")
        errors = _validate_config_safe(p)
        assert any("customRules" in e for e in errors)

    def test_quoted_key_rejected(self, tmp_path: Path) -> None:
        from scripts.ci.validate_vendor_provenance import _validate_config_safe

        p = self._cfg(tmp_path, '"customRules":\n  - x\n')
        errors = _validate_config_safe(p)
        assert any("customRules" in e for e in errors)

    def test_single_quoted_key_rejected(self, tmp_path: Path) -> None:
        from scripts.ci.validate_vendor_provenance import _validate_config_safe

        p = self._cfg(tmp_path, "'customRules':\n  - x\n")
        errors = _validate_config_safe(p)
        assert any("customRules" in e for e in errors)

    def test_flow_mapping_rejected(self, tmp_path: Path) -> None:
        from scripts.ci.validate_vendor_provenance import _validate_config_safe

        p = self._cfg(tmp_path, '{"extends": "./evil.yaml"}')
        errors = _validate_config_safe(p)
        assert any("extends" in e for e in errors)

    def test_nested_exec_key_rejected(self, tmp_path: Path) -> None:
        from scripts.ci.validate_vendor_provenance import _validate_config_safe

        cfg = "overrides:\n  - config:\n      markdownItPlugins:\n        - evil\n"
        p = self._cfg(tmp_path, cfg)
        errors = _validate_config_safe(p)
        assert any("markdownItPlugins" in e for e in errors)

    def test_clean_config_passes(self, tmp_path: Path) -> None:
        from scripts.ci.validate_vendor_provenance import _validate_config_safe

        p = self._cfg(tmp_path, "config:\n  MD040: true\nignores:\n  - '.git/**'\n")
        errors = _validate_config_safe(p)
        assert errors == []

    def test_non_utf8_fails_closed(self, tmp_path: Path) -> None:
        from scripts.ci.validate_vendor_provenance import _validate_config_safe

        p = tmp_path / "bad.yaml"
        p.write_bytes(b"\xff\xfe" + b"\x00" * 50)
        errors = _validate_config_safe(p)
        assert any("UTF-8" in e for e in errors)

    def test_empty_config_passes(self, tmp_path: Path) -> None:
        from scripts.ci.validate_vendor_provenance import _validate_config_safe

        p = self._cfg(tmp_path, "")
        errors = _validate_config_safe(p)
        assert errors == []

    def test_missing_config_passes(self, tmp_path: Path) -> None:
        from scripts.ci.validate_vendor_provenance import _validate_config_safe

        p = tmp_path / "nonexistent.yaml"
        errors = _validate_config_safe(p)
        assert errors == []


# ── Relevance check (exercises production helper) ──

class TestRelevance:
    """Exercises check_relevance production function directly."""

    def test_watched_file_triggers(self) -> None:
        from scripts.ci.validate_vendor_provenance import check_relevance

        assert check_relevance([".claude/hooks/PreToolUse/evil.py"]) is True

    def test_lib_file_triggers(self) -> None:
        from scripts.ci.validate_vendor_provenance import check_relevance

        assert check_relevance([".claude/lib/hook_dispatch.py"]) is True

    def test_src_lib_triggers(self) -> None:
        from scripts.ci.validate_vendor_provenance import check_relevance

        assert check_relevance(["src/copilot-cli/lib/paths.py"]) is True

    def test_unrelated_file_no_trigger(self) -> None:
        from scripts.ci.validate_vendor_provenance import check_relevance

        assert check_relevance(["docs/README.md", "pyproject.toml"]) is False

    def test_empty_list_no_trigger(self) -> None:
        from scripts.ci.validate_vendor_provenance import check_relevance

        assert check_relevance([]) is False

    def test_watched_file_deletion(self) -> None:
        """A deleted watched file (appears in diff output) still triggers."""
        from scripts.ci.validate_vendor_provenance import check_relevance

        assert check_relevance([".claude/lib/deleted_module.py"]) is True

    def test_watched_directory_deletion(self) -> None:
        """Files under a deleted watched dir still match prefix."""
        from scripts.ci.validate_vendor_provenance import check_relevance

        assert check_relevance([".claude/hooks/PreToolUse/subdir/file.py"]) is True

    def test_rename_into_watched(self) -> None:
        """A file renamed into a watched prefix triggers."""
        from scripts.ci.validate_vendor_provenance import check_relevance

        assert check_relevance(["src/copilot-cli/hooks/PreToolUse/renamed.py"]) is True

    def test_build_script_exact_match(self) -> None:
        from scripts.ci.validate_vendor_provenance import check_relevance

        assert check_relevance(["build/scripts/generate_hooks_events.py"]) is True

    def test_build_script_subpath_no_trigger(self) -> None:
        """Only the exact file, not arbitrary build/scripts/ files."""
        from scripts.ci.validate_vendor_provenance import check_relevance

        assert check_relevance(["build/scripts/other.py"]) is False

    def test_cli_check_relevance_true(self) -> None:
        """CLI --check-relevance outputs 'true' for watched files."""
        r = _run(["--check-relevance", ".claude/lib/x.py"])
        assert r.returncode == 0
        assert r.stdout.strip() == "true"

    def test_cli_check_relevance_false(self) -> None:
        """CLI --check-relevance outputs 'false' for unrelated files."""
        r = _run(["--check-relevance", "docs/README.md"])
        assert r.returncode == 0
        assert r.stdout.strip() == "false"


# ── Import closure regression ──

class TestImportClosurePins:
    """Verify all .py files under lib dirs are covered by _PINNED_ARTIFACTS."""

    def test_all_lib_py_files_are_pinned(self) -> None:
        """Every .py file in .claude/lib/ and src/copilot-cli/lib/ must be pinned."""
        from scripts.ci.validate_vendor_provenance import _PINNED_ARTIFACTS

        repo = Path(__file__).resolve().parents[2]
        pinned_rels = {rel for rel, _, _ in _PINNED_ARTIFACTS}
        lib_dirs = [
            repo / ".claude" / "lib",
            repo / "src" / "copilot-cli" / "lib",
        ]
        missing = []
        for lib_dir in lib_dirs:
            if not lib_dir.is_dir():
                continue
            for f in sorted(lib_dir.rglob("*.py")):
                if "__pycache__" in str(f):
                    continue
                rel = str(PurePosixPath(f.relative_to(repo)))
                if rel not in pinned_rels:
                    missing.append(rel)
        assert missing == [], (
            f"Lib .py files not in _PINNED_ARTIFACTS: {missing}"
        )
