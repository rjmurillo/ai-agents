"""Tests for scripts/generate_third_party_notices.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import scripts.generate_third_party_notices as notices_mod
from scripts.generate_third_party_notices import (
    FORKED_COMPONENTS,
    find_forked_components,
    format_notices,
    get_shipped_source_paths,
    load_marketplace_config,
    main,
    resolve_output_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

GSTACK_MIT_LICENSE_TEXT = (
    "MIT License\n"
    "\n"
    "Copyright (c) 2026 Garry Tan\n"
    "\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
    'of this software and associated documentation files (the "Software"), to deal\n'
    "in the Software without restriction, including without limitation the rights\n"
    "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
    "copies of the Software, and to permit persons to whom the Software is\n"
    "furnished to do so, subject to the following conditions:\n"
    "\n"
    "The above copyright notice and this permission notice shall be included in all\n"
    "copies or substantial portions of the Software.\n"
    "\n"
    'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n'
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
    "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
    "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
    "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
    "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
    "SOFTWARE.\n"
)

SKILLFORGE_NOTICE_BLOCK = (
    "1. SkillForge ((fork))\n"
    "\n"
    "   License: MIT\n"
    "   Author:  tripleyak\n"
    "   URL:     https://github.com/tripleyak/SkillForge\n"
    "\n"
    "   ------------------------------------------------------------\n"
    "   MIT License\n"
    "   \n"
    "   Copyright (c) 2025\n"
    "   \n"
    "   Permission is hereby granted, free of charge, to any person obtaining a copy\n"
    '   of this software and associated documentation files (the "Software"), to deal\n'
    "   in the Software without restriction, including without limitation the rights\n"
    "   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
    "   copies of the Software, and to permit persons to whom the Software is\n"
    "   furnished to do so, subject to the following conditions:\n"
    "   \n"
    "   The above copyright notice and this permission notice shall be included in all\n"
    "   copies or substantial portions of the Software.\n"
    "   \n"
    '   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n'
    "   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
    "   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
    "   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
    "   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
    "   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
    "   SOFTWARE.\n"
    "   ------------------------------------------------------------\n"
    "\n"
)


def _write_fake_notice_repo(root: Path) -> None:
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"plugins": []}),
        encoding="utf-8",
    )
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / "src" / "copilot-cli").mkdir(parents=True, exist_ok=True)


def _assert_notice_copies_match(root: Path) -> None:
    root_notice = (root / "THIRD-PARTY-NOTICES.TXT").read_bytes()
    assert (root / ".claude" / "THIRD-PARTY-NOTICES.TXT").read_bytes() == root_notice
    assert (root / "src" / "copilot-cli" / "THIRD-PARTY-NOTICES.TXT").read_bytes() == root_notice


class TestLoadMarketplaceConfig:
    """Tests for marketplace config boundary parsing."""

    def test_returns_plugins_from_valid_config(self, tmp_path: Path) -> None:
        marketplace_dir = tmp_path / ".claude-plugin"
        marketplace_dir.mkdir()
        plugins = [{"name": "tool", "source": ".claude"}]
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

    @pytest.mark.parametrize(
        "plugins",
        [{}, [1], [{"source": 123}], [{"source": []}], [{"source": None}]],
    )
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


class TestGstackAttribution:
    """gstack attribution data must produce a shipped notice."""

    def test_entry_metadata_identifies_the_shipped_skill(self) -> None:
        entry = FORKED_COMPONENTS["gstack"]

        assert entry["license"] == "MIT"
        assert entry["url"] == "https://github.com/garrytan/gstack"
        assert entry["author"] == "Garry Tan"
        assert entry["local_path"] == ".claude/skills/dx-review"
        assert entry["license_blank_line_prefix"] == ""

    def test_entry_contains_the_pinned_mit_license(self) -> None:
        assert FORKED_COMPONENTS["gstack"]["license_text"] == GSTACK_MIT_LICENSE_TEXT

    def test_generated_notice_preserves_gstack_paragraph_breaks(self) -> None:
        plugins = load_marketplace_config(PROJECT_ROOT)
        shipped_paths = get_shipped_source_paths(PROJECT_ROOT, plugins)
        notices = format_notices(find_forked_components(PROJECT_ROOT, shipped_paths), [])
        gstack_entry = notices.split("2. gstack ((fork))", maxsplit=1)[1]
        rendered_license = "\n".join(
            f"   {line}" if line else "" for line in GSTACK_MIT_LICENSE_TEXT.strip().splitlines()
        )

        assert "Author:  Garry Tan" in gstack_entry
        assert "URL:     https://github.com/garrytan/gstack" in gstack_entry
        assert rendered_license in gstack_entry
        assert all(not line.endswith((" ", "\t")) for line in gstack_entry.splitlines())


class TestSkillForgeNotice:
    """Existing SkillForge notice output remains stable."""

    def test_existing_skillforge_block_is_byte_identical_to_baseline(self) -> None:
        plugins = load_marketplace_config(PROJECT_ROOT)
        shipped_paths = get_shipped_source_paths(PROJECT_ROOT, plugins)
        notices = format_notices(find_forked_components(PROJECT_ROOT, shipped_paths), [])
        start = notices.index("1. SkillForge ((fork))")
        end = notices.index("2. gstack ((fork))")

        assert notices[start:end].encode("utf-8") == SKILLFORGE_NOTICE_BLOCK.encode("utf-8")


class TestCommittedNotice:
    """The committed notice artifacts must be current generator output."""

    def test_committed_notice_copies_match_generator_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            ["generate_third_party_notices.py", "--check"],
        )

        assert main() == 0

    def test_packaged_notice_copies_match_root_notice(self) -> None:
        _assert_notice_copies_match(PROJECT_ROOT)

    def test_check_rejects_a_stale_notice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_fake_notice_repo(tmp_path)
        monkeypatch.setattr(notices_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.chdir(tmp_path)
        notice_path = tmp_path / "custom" / "THIRD-PARTY-NOTICES.TXT"
        notice_path.parent.mkdir(parents=True)
        notice_path.write_bytes(b"hand-edited notice")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "generate_third_party_notices.py",
                "--check",
                "--output",
                "custom/THIRD-PARTY-NOTICES.TXT",
            ],
        )

        assert main() == 1

    def test_check_rejects_a_missing_notice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_fake_notice_repo(tmp_path)
        monkeypatch.setattr(notices_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "generate_third_party_notices.py",
                "--check",
                "--output",
                "missing/THIRD-PARTY-NOTICES.TXT",
            ],
        )

        assert main() == 1

    def test_default_generation_writes_packaged_notice_copies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_fake_notice_repo(tmp_path)
        monkeypatch.setattr(notices_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["generate_third_party_notices.py"])

        assert main() == 0
        _assert_notice_copies_match(tmp_path)


class TestOutputPathContainment:
    """Output paths must stay within the project root."""

    def test_allows_relative_output_within_project_root(self, tmp_path: Path) -> None:
        resolved = resolve_output_path(tmp_path, "nested/THIRD-PARTY-NOTICES.TXT")
        assert resolved == tmp_path / "nested" / "THIRD-PARTY-NOTICES.TXT"

    def test_allows_absolute_output_within_project_root(self, tmp_path: Path) -> None:
        target = tmp_path / "THIRD-PARTY-NOTICES.TXT"
        assert resolve_output_path(tmp_path, str(target)) == target

    def test_rejects_absolute_output_outside_project_root(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="escapes project root"):
            resolve_output_path(tmp_path, "/tmp/THIRD-PARTY-NOTICES.TXT")

    def test_rejects_parent_traversal_outside_project_root(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="escapes project root"):
            resolve_output_path(tmp_path, "../THIRD-PARTY-NOTICES.TXT")

    def test_rejects_symlink_escape(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        outside = tmp_path / "outside"
        project_root.mkdir()
        outside.mkdir()
        link = project_root / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"symlink creation is unavailable: {error}")

        with pytest.raises(ValueError, match="escapes project root"):
            resolve_output_path(project_root, "linked/THIRD-PARTY-NOTICES.TXT")

    def test_cli_rejects_parent_traversal(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_fake_notice_repo(tmp_path)
        monkeypatch.setattr(notices_mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "generate_third_party_notices.py",
                "--output",
                "../THIRD-PARTY-NOTICES.TXT",
            ],
        )

        assert main() == 2
        assert "output path escapes project root" in capsys.readouterr().err

    def test_cli_rejects_cwd_outside_project_root(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project_root = tmp_path / "project"
        outside = tmp_path / "outside"
        _write_fake_notice_repo(project_root)
        outside.mkdir()
        monkeypatch.setattr(notices_mod, "PROJECT_ROOT", project_root)
        monkeypatch.chdir(outside)
        monkeypatch.setattr(sys, "argv", ["generate_third_party_notices.py"])

        assert main() == 2
        assert "current directory is outside project root" in capsys.readouterr().err
        assert not (project_root / "THIRD-PARTY-NOTICES.TXT").exists()
