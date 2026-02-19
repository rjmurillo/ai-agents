"""Test fixtures for memory_sync tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Create a temporary project root with .serena/memories/ structure."""
    memories_dir = tmp_path / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture()
def sample_memory_file(project_root: Path) -> Path:
    """Create a sample Serena memory file."""
    memories_dir = project_root / ".serena" / "memories"
    memory_path = memories_dir / "test-memory.md"
    memory_path.write_text(
        "---\n"
        "id: test-memory\n"
        "subject: Test Memory\n"
        "tags:\n"
        "  - testing\n"
        "  - unit\n"
        "confidence: 0.8\n"
        "---\n"
        "\n"
        "This is a test memory for unit testing.\n",
        encoding="utf-8",
    )
    return memory_path


@pytest.fixture()
def mock_mcp_client() -> MagicMock:
    """Create a mock MCP client."""
    client = MagicMock()
    client.call_tool.return_value = {
        "content": [{"type": "text", "text": json.dumps({"id": 42})}],
    }
    return client


@pytest.fixture()
def state_file(project_root: Path) -> Path:
    """Create a sync state file."""
    state_path = project_root / ".memory_sync_state.json"
    state_path.write_text("{}", encoding="utf-8")
    return state_path


@pytest.fixture()
def mock_server_path() -> Path:
    """Path to the mock Forgetful MCP server."""
    return Path(__file__).parent / "mock_forgetful_server.py"


@pytest.fixture()
def mock_server_command(mock_server_path: Path) -> list[str]:
    """Command to run the mock Forgetful MCP server."""
    return [sys.executable, str(mock_server_path)]
