"""Tests for sync_mcp_config.py MCP configuration synchronization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.sync_mcp_config import (
    main,
    transform_for_factory,
    transform_for_vscode,
)

SAMPLE_SOURCE: dict[str, Any] = {
    "mcpServers": {
        "serena": {
            "command": "serena",
            "args": ["claude-code", "24282"],
        },
        "other": {
            "command": "other-server",
            "args": ["--flag"],
        },
    },
    "extraKey": "preserved",
}


class TestTransformForVscode:
    def test_renames_mcpservers_to_servers(self) -> None:
        result = transform_for_vscode(SAMPLE_SOURCE)
        assert "servers" in result
        assert "mcpServers" not in result

    def test_transforms_serena_args(self) -> None:
        result = transform_for_vscode(SAMPLE_SOURCE)
        serena_args = result["servers"]["serena"]["args"]
        assert "ide" in serena_args
        assert "24283" in serena_args
        assert "claude-code" not in serena_args

    def test_preserves_other_servers(self) -> None:
        result = transform_for_vscode(SAMPLE_SOURCE)
        assert "other" in result["servers"]
        assert result["servers"]["other"]["args"] == ["--flag"]

    def test_preserves_extra_keys(self) -> None:
        result = transform_for_vscode(SAMPLE_SOURCE)
        assert result["extraKey"] == "preserved"


class TestTransformForFactory:
    def test_preserves_mcpservers_key(self) -> None:
        result = transform_for_factory(SAMPLE_SOURCE)
        assert "mcpServers" in result
        assert "servers" not in result

    def test_deep_copies_data(self) -> None:
        result = transform_for_factory(SAMPLE_SOURCE)
        result["mcpServers"]["serena"]["args"].append("mutated")
        assert "mutated" not in SAMPLE_SOURCE["mcpServers"]["serena"]["args"]

    def test_preserves_extra_keys(self) -> None:
        result = transform_for_factory(SAMPLE_SOURCE)
        assert result["extraKey"] == "preserved"


class TestMain:
    def test_sync_all_with_destination_errors(self) -> None:
        assert main(["--sync-all", "--destination", "/fake"]) == 1

    def test_sync_all_with_target_errors(self) -> None:
        assert main(["--sync-all", "--target", "factory"]) == 1

    def test_sync_to_vscode(self, tmp_path: Path) -> None:
        source = tmp_path / ".mcp.json"
        source.write_text(json.dumps(SAMPLE_SOURCE), encoding="utf-8")
        dest = tmp_path / ".vscode" / "mcp.json"

        result = main([
            "--source", str(source),
            "--destination", str(dest),
            "--target", "vscode",
            "--repo-root-override", str(tmp_path),
        ])
        assert result == 0
        assert dest.exists()
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert "servers" in data
