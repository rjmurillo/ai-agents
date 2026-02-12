"""Tests for traceability scripts migrated from PowerShell to Python.

Covers: traceability_cache, spec_utils, rename_spec_id,
update_spec_references, resolve_orphaned_specs, show_traceability_graph.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.traceability.traceability_cache import (
    _memory_cache,
    clear_cache,
    get_cache_key,
    get_cache_stats,
    get_cached_spec,
    get_file_hash,
    initialize_cache,
    set_cached_spec,
)
from scripts.traceability.spec_utils import (
    find_spec_file,
    get_spec_subdir,
    get_spec_type,
    is_valid_spec_id,
    load_all_specs,
    parse_frontmatter_with_content,
    parse_yaml_frontmatter,
)
from scripts.traceability.show_traceability_graph import (
    build_graph,
    format_json_graph,
    format_mermaid_graph,
    format_text_graph,
    main as graph_main,
)
from scripts.traceability.resolve_orphaned_specs import (
    find_orphaned_specs,
    main as orphans_main,
)
from scripts.traceability.rename_spec_id import main as rename_main
from scripts.traceability.update_spec_references import main as update_main


def _create_spec(
    base_path: Path,
    spec_id: str,
    spec_type: str,
    related: list[str] | None = None,
    status: str = "draft",
) -> Path:
    """Create a spec markdown file with YAML frontmatter."""
    subdir_map = {"requirement": "requirements", "design": "design", "task": "tasks"}
    subdir = base_path / subdir_map[spec_type]
    subdir.mkdir(parents=True, exist_ok=True)

    if related:
        related_block = "related:\n" + "".join(f"  - {r}\n" for r in related)
    else:
        related_block = "related: []\n"

    content = (
        f"---\n"
        f"type: {spec_type}\n"
        f"id: {spec_id}\n"
        f"status: {status}\n"
        f"{related_block}"
        f"---\n"
        f"\n"
        f"# {spec_id}\n"
        f"\n"
        f"Test spec content\n"
    )

    file_path = subdir / f"{spec_id}.md"
    file_path.write_text(content, encoding="utf-8")
    return file_path


@pytest.fixture()
def specs_dir(tmp_path: Path) -> Path:
    """Create a temporary specs directory with test data."""
    specs = tmp_path / "specs"
    specs.mkdir()
    _create_spec(specs, "REQ-001", "requirement", status="approved")
    _create_spec(specs, "DESIGN-001", "design", related=["REQ-001"], status="approved")
    _create_spec(specs, "TASK-001", "task", related=["DESIGN-001"], status="complete")
    return specs


@pytest.fixture()
def orphan_specs_dir(tmp_path: Path) -> Path:
    """Create specs directory with orphans for testing."""
    specs = tmp_path / "specs"
    specs.mkdir()
    _create_spec(specs, "REQ-001", "requirement", status="approved")
    _create_spec(specs, "REQ-002", "requirement", status="draft")
    _create_spec(specs, "DESIGN-001", "design", related=["REQ-001"], status="approved")
    _create_spec(specs, "DESIGN-002", "design", status="draft")
    _create_spec(specs, "TASK-001", "task", related=["DESIGN-001"], status="complete")
    _create_spec(specs, "TASK-002", "task", status="draft")
    return specs


class TestTraceabilityCache:
    def setup_method(self) -> None:
        clear_cache()

    def test_initialize_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import scripts.traceability.traceability_cache as cache_mod
        monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path / "cache")
        initialize_cache()
        assert (tmp_path / "cache").exists()

    def test_get_cache_key_sanitizes_path(self) -> None:
        key = get_cache_key("/some/path/to/file.md")
        assert ":" not in key
        assert "?" not in key

    def test_get_file_hash_returns_none_for_missing(self, tmp_path: Path) -> None:
        assert get_file_hash(tmp_path / "nonexistent.md") is None

    def test_get_file_hash_returns_string_for_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("content")
        result = get_file_hash(f)
        assert result is not None
        assert "_" in result

    def test_cache_round_trip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import scripts.traceability.traceability_cache as cache_mod
        monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path / "cache")

        spec = {"type": "requirement", "id": "REQ-001", "status": "draft", "related": ["DESIGN-001"]}
        set_cached_spec("/test/file.md", "hash123", spec)
        result = get_cached_spec("/test/file.md", "hash123")
        assert result is not None
        assert result["id"] == "REQ-001"
        assert "DESIGN-001" in result["related"]

    def test_cache_miss_on_different_hash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import scripts.traceability.traceability_cache as cache_mod
        monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path / "cache")

        spec = {"type": "requirement", "id": "REQ-001", "status": "draft", "related": []}
        set_cached_spec("/test/file.md", "hash123", spec)
        result = get_cached_spec("/test/file.md", "different_hash")
        assert result is None

    def test_clear_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import scripts.traceability.traceability_cache as cache_mod
        monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path / "cache")

        spec = {"type": "requirement", "id": "REQ-001", "status": "draft", "related": []}
        set_cached_spec("/test/file.md", "hash123", spec)
        clear_cache()
        stats = get_cache_stats()
        assert stats["memory_cache_entries"] == 0

    def test_get_cache_stats(self) -> None:
        stats = get_cache_stats()
        assert "memory_cache_entries" in stats
        assert "disk_cache_entries" in stats
        assert "cache_directory" in stats


class TestSpecUtils:
    def test_valid_spec_ids(self) -> None:
        assert is_valid_spec_id("REQ-001")
        assert is_valid_spec_id("DESIGN-ABC")
        assert is_valid_spec_id("TASK-123")

    def test_invalid_spec_ids(self) -> None:
        assert not is_valid_spec_id("INVALID")
        assert not is_valid_spec_id("req-001")
        assert not is_valid_spec_id("")
        assert not is_valid_spec_id("REQ-")

    def test_get_spec_type(self) -> None:
        assert get_spec_type("REQ-001") == "REQ"
        assert get_spec_type("DESIGN-001") == "DESIGN"
        assert get_spec_type("TASK-001") == "TASK"

    def test_get_spec_subdir(self) -> None:
        assert get_spec_subdir("REQ-001") == "requirements"
        assert get_spec_subdir("DESIGN-001") == "design"
        assert get_spec_subdir("TASK-001") == "tasks"

    def test_find_spec_file(self, specs_dir: Path) -> None:
        result = find_spec_file("REQ-001", specs_dir)
        assert result is not None
        assert result.name == "REQ-001.md"

    def test_find_spec_file_missing(self, specs_dir: Path) -> None:
        assert find_spec_file("REQ-999", specs_dir) is None

    def test_parse_yaml_frontmatter(self, specs_dir: Path) -> None:
        spec = parse_yaml_frontmatter(
            specs_dir / "design" / "DESIGN-001.md", use_cache=False
        )
        assert spec is not None
        assert spec["id"] == "DESIGN-001"
        assert spec["type"] == "design"
        assert "REQ-001" in spec["related"]

    def test_parse_frontmatter_with_content(self, specs_dir: Path) -> None:
        result = parse_frontmatter_with_content(
            specs_dir / "design" / "DESIGN-001.md"
        )
        assert result is not None
        assert result["frontmatter"].startswith("---")
        assert "REQ-001" in result["related"]

    def test_load_all_specs(self, specs_dir: Path) -> None:
        specs = load_all_specs(specs_dir, use_cache=False)
        assert "REQ-001" in specs["requirements"]
        assert "DESIGN-001" in specs["designs"]
        assert "TASK-001" in specs["tasks"]
        assert len(specs["all"]) == 3


class TestShowTraceabilityGraph:
    def test_build_graph(self, specs_dir: Path) -> None:
        specs = load_all_specs(specs_dir, use_cache=False)
        graph = build_graph(specs)
        assert "REQ-001" in graph["nodes"]
        assert len(graph["edges"]) > 0

    def test_text_format(self, specs_dir: Path) -> None:
        specs = load_all_specs(specs_dir, use_cache=False)
        graph = build_graph(specs)
        output = format_text_graph(graph, specs, None, 0, False)
        assert "REQ-001" in output
        assert "Traceability Graph" in output

    def test_mermaid_format(self, specs_dir: Path) -> None:
        specs = load_all_specs(specs_dir, use_cache=False)
        graph = build_graph(specs)
        output = format_mermaid_graph(graph, specs, None, 0)
        assert "```mermaid" in output
        assert "graph TD" in output

    def test_json_format(self, specs_dir: Path) -> None:
        specs = load_all_specs(specs_dir, use_cache=False)
        graph = build_graph(specs)
        output = format_json_graph(graph, None, 0)
        data = json.loads(output)
        assert len(data["nodes"]) == 3
        assert len(data["edges"]) > 0

    def test_root_id_filter(self, specs_dir: Path) -> None:
        specs = load_all_specs(specs_dir, use_cache=False)
        graph = build_graph(specs)
        output = format_text_graph(graph, specs, "REQ-001", 0, False)
        assert "REQ-001" in output

    def test_depth_limiting(self, specs_dir: Path) -> None:
        specs = load_all_specs(specs_dir, use_cache=False)
        graph = build_graph(specs)
        output = format_text_graph(graph, specs, None, 1, False)
        assert "REQ-001" in output

    def test_main_text(self, specs_dir: Path) -> None:
        rc = graph_main(["--specs-path", str(specs_dir), "--format", "text", "--no-cache"])
        assert rc == 0

    def test_main_mermaid(self, specs_dir: Path) -> None:
        rc = graph_main(["--specs-path", str(specs_dir), "--format", "mermaid", "--no-cache"])
        assert rc == 0

    def test_main_json(self, specs_dir: Path) -> None:
        rc = graph_main(["--specs-path", str(specs_dir), "--format", "json", "--no-cache"])
        assert rc == 0

    def test_main_dry_run(self, specs_dir: Path) -> None:
        rc = graph_main(["--specs-path", str(specs_dir), "--dry-run"])
        assert rc == 0

    def test_main_root_id(self, specs_dir: Path) -> None:
        rc = graph_main(["--specs-path", str(specs_dir), "--root-id", "REQ-001", "--no-cache"])
        assert rc == 0

    def test_main_invalid_root_id(self, specs_dir: Path) -> None:
        rc = graph_main(["--specs-path", str(specs_dir), "--root-id", "INVALID-999", "--no-cache"])
        assert rc == 1

    def test_main_nonexistent_path(self, tmp_path: Path) -> None:
        rc = graph_main(["--specs-path", str(tmp_path / "nonexistent")])
        assert rc == 1

    def test_main_missing_root_spec(self, specs_dir: Path) -> None:
        rc = graph_main(["--specs-path", str(specs_dir), "--root-id", "REQ-999", "--no-cache"])
        assert rc == 1


class TestResolveOrphanedSpecs:
    def test_find_orphaned_specs(self, orphan_specs_dir: Path) -> None:
        specs = load_all_specs(orphan_specs_dir, use_cache=False)
        orphans = find_orphaned_specs(specs)
        req_ids = [o["id"] for o in orphans["requirements"]]
        assert "REQ-002" in req_ids
        design_ids = [o["id"] for o in orphans["designs"]]
        assert "DESIGN-002" in design_ids
        task_ids = [o["id"] for o in orphans["tasks"]]
        assert "TASK-002" in task_ids

    def test_main_list_finds_orphans(self, orphan_specs_dir: Path) -> None:
        rc = orphans_main(["--specs-path", str(orphan_specs_dir), "--action", "list", "--no-cache"])
        assert rc == 2

    def test_main_list_by_type(self, orphan_specs_dir: Path) -> None:
        rc = orphans_main([
            "--specs-path", str(orphan_specs_dir),
            "--action", "list",
            "--type", "tasks",
            "--no-cache",
        ])
        assert rc == 2

    def test_main_archive_dry_run(self, orphan_specs_dir: Path) -> None:
        rc = orphans_main([
            "--specs-path", str(orphan_specs_dir),
            "--action", "archive",
            "--dry-run",
            "--no-cache",
        ])
        assert rc == 0
        assert (orphan_specs_dir / "requirements" / "REQ-002.md").exists()

    def test_main_archive_force(self, orphan_specs_dir: Path) -> None:
        rc = orphans_main([
            "--specs-path", str(orphan_specs_dir),
            "--action", "archive",
            "--type", "tasks",
            "--force",
            "--no-cache",
        ])
        assert rc == 0
        assert not (orphan_specs_dir / "tasks" / "TASK-002.md").exists()
        assert (orphan_specs_dir / ".archive" / "tasks" / "TASK-002.md").exists()

    def test_main_delete_dry_run(self, orphan_specs_dir: Path) -> None:
        rc = orphans_main([
            "--specs-path", str(orphan_specs_dir),
            "--action", "delete",
            "--dry-run",
            "--no-cache",
        ])
        assert rc == 0
        assert (orphan_specs_dir / "requirements" / "REQ-002.md").exists()

    def test_main_delete_force(self, orphan_specs_dir: Path) -> None:
        rc = orphans_main([
            "--specs-path", str(orphan_specs_dir),
            "--action", "delete",
            "--type", "tasks",
            "--force",
            "--no-cache",
        ])
        assert rc == 0
        assert not (orphan_specs_dir / "tasks" / "TASK-002.md").exists()
        assert (orphan_specs_dir / "tasks" / "TASK-001.md").exists()

    def test_main_nonexistent_path(self, tmp_path: Path) -> None:
        rc = orphans_main(["--specs-path", str(tmp_path / "nonexistent")])
        assert rc == 1

    def test_no_orphans(self, specs_dir: Path) -> None:
        specs = load_all_specs(specs_dir, use_cache=False)
        orphans = find_orphaned_specs(specs)
        assert not orphans["tasks"]


class TestRenameSpecId:
    def test_dry_run(self, specs_dir: Path) -> None:
        rc = rename_main([
            "--old-id", "REQ-001",
            "--new-id", "REQ-100",
            "--specs-path", str(specs_dir),
            "--dry-run",
        ])
        assert rc == 0
        assert (specs_dir / "requirements" / "REQ-001.md").exists()
        assert not (specs_dir / "requirements" / "REQ-100.md").exists()

    def test_invalid_old_id(self, specs_dir: Path) -> None:
        rc = rename_main([
            "--old-id", "INVALID",
            "--new-id", "REQ-100",
            "--specs-path", str(specs_dir),
        ])
        assert rc == 1

    def test_invalid_new_id(self, specs_dir: Path) -> None:
        rc = rename_main([
            "--old-id", "REQ-001",
            "--new-id", "INVALID",
            "--specs-path", str(specs_dir),
        ])
        assert rc == 1

    def test_type_change_rejected(self, specs_dir: Path) -> None:
        rc = rename_main([
            "--old-id", "REQ-001",
            "--new-id", "DESIGN-100",
            "--specs-path", str(specs_dir),
        ])
        assert rc == 1

    def test_nonexistent_source(self, specs_dir: Path) -> None:
        rc = rename_main([
            "--old-id", "REQ-999",
            "--new-id", "REQ-100",
            "--specs-path", str(specs_dir),
        ])
        assert rc == 1

    def test_target_already_exists(self, specs_dir: Path) -> None:
        _create_spec(specs_dir, "REQ-100", "requirement")
        rc = rename_main([
            "--old-id", "REQ-001",
            "--new-id", "REQ-100",
            "--specs-path", str(specs_dir),
        ])
        assert rc == 1

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        rc = rename_main([
            "--old-id", "REQ-001",
            "--new-id", "REQ-100",
            "--specs-path", str(tmp_path / "nonexistent"),
        ])
        assert rc == 1

    def test_rename_with_force(self, specs_dir: Path) -> None:
        rc = rename_main([
            "--old-id", "REQ-001",
            "--new-id", "REQ-100",
            "--specs-path", str(specs_dir),
            "--force",
        ])
        assert rc == 0
        assert not (specs_dir / "requirements" / "REQ-001.md").exists()
        assert (specs_dir / "requirements" / "REQ-100.md").exists()

        design_content = (specs_dir / "design" / "DESIGN-001.md").read_text()
        assert "REQ-100" in design_content
        assert "REQ-001" not in design_content


class TestUpdateSpecReferences:
    def test_dry_run_add(self, specs_dir: Path) -> None:
        _create_spec(specs_dir, "REQ-002", "requirement")
        rc = update_main([
            "--source-id", "DESIGN-001",
            "--add", "REQ-002",
            "--specs-path", str(specs_dir),
            "--dry-run",
        ])
        assert rc == 0
        content = (specs_dir / "design" / "DESIGN-001.md").read_text()
        assert "REQ-002" not in content

    def test_invalid_source_id(self, specs_dir: Path) -> None:
        rc = update_main([
            "--source-id", "INVALID",
            "--add", "REQ-002",
            "--specs-path", str(specs_dir),
        ])
        assert rc == 1

    def test_invalid_reference_id(self, specs_dir: Path) -> None:
        rc = update_main([
            "--source-id", "DESIGN-001",
            "--add", "INVALID",
            "--specs-path", str(specs_dir),
        ])
        assert rc == 1

    def test_nonexistent_source(self, specs_dir: Path) -> None:
        rc = update_main([
            "--source-id", "DESIGN-999",
            "--add", "REQ-002",
            "--specs-path", str(specs_dir),
        ])
        assert rc == 1

    def test_add_reference_with_force(self, specs_dir: Path) -> None:
        _create_spec(specs_dir, "REQ-002", "requirement")
        rc = update_main([
            "--source-id", "DESIGN-001",
            "--add", "REQ-002",
            "--specs-path", str(specs_dir),
            "--force",
        ])
        assert rc == 0
        content = (specs_dir / "design" / "DESIGN-001.md").read_text()
        assert "REQ-002" in content
        assert "REQ-001" in content

    def test_remove_reference_with_force(self, specs_dir: Path) -> None:
        rc = update_main([
            "--source-id", "DESIGN-001",
            "--remove", "REQ-001",
            "--specs-path", str(specs_dir),
            "--force",
        ])
        assert rc == 0
        content = (specs_dir / "design" / "DESIGN-001.md").read_text()
        assert "REQ-001" not in content

    def test_replace_reference_with_force(self, specs_dir: Path) -> None:
        _create_spec(specs_dir, "REQ-002", "requirement")
        rc = update_main([
            "--source-id", "DESIGN-001",
            "--replace", "REQ-001", "REQ-002",
            "--specs-path", str(specs_dir),
            "--force",
        ])
        assert rc == 0
        content = (specs_dir / "design" / "DESIGN-001.md").read_text()
        assert "REQ-002" in content
        assert "REQ-001" not in content

    def test_replace_nonexistent_reference(self, specs_dir: Path) -> None:
        rc = update_main([
            "--source-id", "DESIGN-001",
            "--replace", "REQ-999", "REQ-002",
            "--specs-path", str(specs_dir),
            "--force",
        ])
        assert rc == 1
