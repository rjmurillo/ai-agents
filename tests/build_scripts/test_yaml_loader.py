"""Tests for yaml_loader shared module.

Covers ConfigError raising paths, schemaVersion handling, anchor/alias
rejection, and validate_relative_path edge cases. Pos + neg + edge per
TESTING-RIGOR.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BUILD_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "build" / "scripts"
sys.path.insert(0, str(_BUILD_SCRIPTS))

from yaml_loader import (  # noqa: E402
    ConfigError,
    load_platform_config,
    validate_relative_path,
)


# --- load_platform_config: happy path ------------------------------------


class TestLoadPlatformConfigHappyPath:
    def test_minimal_valid_config(self, tmp_path: Path) -> None:
        cfg = tmp_path / "ok.yaml"
        cfg.write_text('schemaVersion: "1.0"\nprovider: "test"\n')
        data = load_platform_config(cfg)
        assert data["provider"] == "test"
        assert data["schemaVersion"] == "1.0"

    def test_higher_minor_version_accepted(self, tmp_path: Path) -> None:
        cfg = tmp_path / "ok.yaml"
        cfg.write_text('schemaVersion: "1.99"\nprovider: "x"\n')
        data = load_platform_config(cfg)
        assert data["schemaVersion"] == "1.99"


# --- load_platform_config: error paths -----------------------------------


class TestLoadPlatformConfigErrors:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="missing file"):
            load_platform_config(tmp_path / "does-not-exist.yaml")

    def test_anchor_rejected(self, tmp_path: Path) -> None:
        cfg = tmp_path / "anchor.yaml"
        cfg.write_text(
            'schemaVersion: "1.0"\n'
            "provider: &p test\n"
            "alias_field: *p\n"
        )
        with pytest.raises(ConfigError, match="anchor detected"):
            load_platform_config(cfg)

    def test_alias_rejected(self, tmp_path: Path) -> None:
        cfg = tmp_path / "alias.yaml"
        cfg.write_text('schemaVersion: "1.0"\nprovider: *p\n')
        with pytest.raises(ConfigError, match="alias detected"):
            load_platform_config(cfg)

    def test_quoted_ampersand_not_an_anchor(self, tmp_path: Path) -> None:
        # Regression: blocklist patterns like "@[a-f0-9]{40}\\b" must not
        # trigger the alias scanner.
        cfg = tmp_path / "quoted.yaml"
        cfg.write_text(
            'schemaVersion: "1.0"\n'
            'provider: "x"\n'
            'note: "see &amp; or *star inside quotes"\n'
        )
        data = load_platform_config(cfg)
        assert data["provider"] == "x"

    def test_missing_schema_version(self, tmp_path: Path) -> None:
        cfg = tmp_path / "noversion.yaml"
        cfg.write_text('provider: "x"\n')
        with pytest.raises(ConfigError, match="missing required `schemaVersion`"):
            load_platform_config(cfg)

    def test_non_string_schema_version(self, tmp_path: Path) -> None:
        cfg = tmp_path / "intversion.yaml"
        cfg.write_text("schemaVersion: 1\nprovider: x\n")
        with pytest.raises(ConfigError, match="must be a string"):
            load_platform_config(cfg)

    def test_malformed_schema_version(self, tmp_path: Path) -> None:
        cfg = tmp_path / "bad.yaml"
        cfg.write_text('schemaVersion: "1"\nprovider: x\n')
        with pytest.raises(ConfigError, match="not a valid SemVer"):
            load_platform_config(cfg)

    def test_unsupported_major(self, tmp_path: Path) -> None:
        cfg = tmp_path / "v2.yaml"
        cfg.write_text('schemaVersion: "2.0"\nprovider: x\n')
        with pytest.raises(ConfigError, match="major version 2 unsupported"):
            load_platform_config(cfg)

    def test_custom_supported_major(self, tmp_path: Path) -> None:
        cfg = tmp_path / "v2.yaml"
        cfg.write_text('schemaVersion: "2.0"\nprovider: x\n')
        data = load_platform_config(cfg, supported_major=2)
        assert data["schemaVersion"] == "2.0"

    def test_top_level_must_be_mapping(self, tmp_path: Path) -> None:
        cfg = tmp_path / "list.yaml"
        cfg.write_text("- one\n- two\n")
        with pytest.raises(ConfigError, match="must be a mapping"):
            load_platform_config(cfg)

    def test_yaml_parse_error(self, tmp_path: Path) -> None:
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("schemaVersion: '1.0'\nprovider: [unclosed\n")
        with pytest.raises(ConfigError, match="YAML parse error"):
            load_platform_config(cfg)


class TestLoadPlatformConfigEnhancements:
    """P1 fixes from /test gate-5 critic review."""

    def test_string_path_coerced(self, tmp_path: Path) -> None:
        """Caller passing a str (not Path) gets clean ConfigError, not AttributeError."""
        cfg = tmp_path / "ok.yaml"
        cfg.write_text('schemaVersion: "1.0"\nprovider: "x"\n')
        # Pass a STRING, not a Path. Should still work via internal coercion.
        data = load_platform_config(str(cfg))
        assert data["schemaVersion"] == "1.0"

    def test_missing_file_string_path(self, tmp_path: Path) -> None:
        """Missing file with str input also raises ConfigError, not AttributeError."""
        with pytest.raises(ConfigError, match="missing file"):
            load_platform_config(str(tmp_path / "nope.yaml"))

    def test_schema_version_error_includes_file_path(self, tmp_path: Path) -> None:
        """schemaVersion failures must name the file (gate-5 finding F2)."""
        cfg = tmp_path / "v2.yaml"
        cfg.write_text('schemaVersion: "2.0"\nprovider: x\n')
        with pytest.raises(ConfigError) as exc_info:
            load_platform_config(cfg)
        # File path must be in the message so contributors know which file
        assert str(cfg) in str(exc_info.value)

    def test_anchor_error_includes_file_path(self, tmp_path: Path) -> None:
        """Anchor rejection error must include file path."""
        cfg = tmp_path / "anchor.yaml"
        cfg.write_text(
            'schemaVersion: "1.0"\nprovider: x\nfoo: &a 1\nbar: *a\n'
        )
        with pytest.raises(ConfigError) as exc_info:
            load_platform_config(cfg)
        assert str(cfg) in str(exc_info.value)


# --- validate_relative_path ----------------------------------------------


class TestValidateRelativePath:
    def test_valid_relative_path(self) -> None:
        assert validate_relative_path("f", "src/claude") == []

    def test_absolute_path_rejected(self) -> None:
        errs = validate_relative_path("f", "/etc/passwd")
        assert errs and "absolute path" in errs[0]

    def test_traversal_rejected(self) -> None:
        errs = validate_relative_path("f", "src/../etc")
        assert errs and "traversal" in errs[0]

    def test_empty_string_rejected(self) -> None:
        errs = validate_relative_path("f", "")
        assert errs and "must not be empty" in errs[0]

    def test_non_string_rejected(self) -> None:
        errs = validate_relative_path("f", 42)
        assert errs and "must be a string path" in errs[0]

    def test_none_rejected(self) -> None:
        errs = validate_relative_path("f", None)
        assert errs and "must be a string path" in errs[0]
