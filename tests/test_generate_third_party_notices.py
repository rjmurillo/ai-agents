"""Tests for scripts/generate_third_party_notices.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_third_party_notices import load_marketplace_config


class TestLoadMarketplaceConfig:
    """Tests for marketplace config boundary parsing."""

    def test_returns_plugins_from_valid_config(self, tmp_path: Path) -> None:
        marketplace_dir = tmp_path / ".claude-plugin"
        marketplace_dir.mkdir()
        plugins = [{"name": "tool", "path": ".claude"}]
        (marketplace_dir / "marketplace.json").write_text(
            json.dumps({"plugins": plugins}),
            encoding="utf-8",
        )

        result = load_marketplace_config(tmp_path)

        assert result == plugins

    def test_missing_plugins_key_returns_empty_list(self, tmp_path: Path) -> None:
        marketplace_dir = tmp_path / ".claude-plugin"
        marketplace_dir.mkdir()
        (marketplace_dir / "marketplace.json").write_text(
            json.dumps({"other": []}),
            encoding="utf-8",
        )

        result = load_marketplace_config(tmp_path)

        assert result == []

    def test_malformed_json_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        marketplace_dir = tmp_path / ".claude-plugin"
        marketplace_dir.mkdir()
        (marketplace_dir / "marketplace.json").write_text("{", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            load_marketplace_config(tmp_path)

        assert exc_info.value.code == 2
        assert "Failed to read" in capsys.readouterr().err

    def test_non_object_root_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        marketplace_dir = tmp_path / ".claude-plugin"
        marketplace_dir.mkdir()
        (marketplace_dir / "marketplace.json").write_text("[]", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            load_marketplace_config(tmp_path)

        assert exc_info.value.code == 2
        assert "root must be a JSON object" in capsys.readouterr().err

    @pytest.mark.parametrize("plugins", [{}, [1]])
    def test_wrong_plugins_type_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], plugins: object
    ) -> None:
        marketplace_dir = tmp_path / ".claude-plugin"
        marketplace_dir.mkdir()
        (marketplace_dir / "marketplace.json").write_text(
            json.dumps({"plugins": plugins}),
            encoding="utf-8",
        )

        with pytest.raises(SystemExit) as exc_info:
            load_marketplace_config(tmp_path)

        assert exc_info.value.code == 2
        assert "plugins must be a JSON array of objects" in capsys.readouterr().err

    def test_empty_object_returns_empty_list(self, tmp_path: Path) -> None:
        marketplace_dir = tmp_path / ".claude-plugin"
        marketplace_dir.mkdir()
        (marketplace_dir / "marketplace.json").write_text("{}", encoding="utf-8")

        result = load_marketplace_config(tmp_path)

        assert result == []
