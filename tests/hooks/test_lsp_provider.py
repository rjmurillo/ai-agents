"""Tests for scripts/hook_utilities/lsp_provider.py (ADR-062 LSP detection).

Covers the capability binding (symbol_navigation = programming languages only;
symbols_overview = all 8 configured serena languages), the pure config reads
(.serena/project.yml languages + .mcp.json serena presence), native LSP tier
availability, provider ordering, and every fail-open path (no provider, bad
config, missing capability).
"""

from __future__ import annotations

import json

import pytest

from scripts.hook_utilities import lsp_provider
from scripts.hook_utilities.lsp_provider import (
    SYMBOL_NAVIGATION,
    SYMBOLS_OVERVIEW,
    detect_providers,
    is_code_target,
)

# ---------------------------------------------------------------------------
# Fixtures: build a fake project dir with .serena/project.yml + .mcp.json
# ---------------------------------------------------------------------------

_ALL_LANGUAGES = ["bash", "yaml", "python", "markdown", "powershell", "typescript", "json", "toml"]


@pytest.fixture(autouse=True)
def isolate_home(tmp_path, monkeypatch):
    """Point Path.home() at an empty temp dir so the real ~/.mcp.json and
    ~/.claude.json (which register serena on this machine) never leak into
    config-detection tests. Each test that wants home-level config writes it
    explicitly via the monkeypatched home.
    """
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    monkeypatch.setattr(lsp_provider.Path, "home", classmethod(lambda cls: fake_home))
    return fake_home


def _write_serena_project(project_dir, languages):
    serena_dir = project_dir / ".serena"
    serena_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# leading comment", "encoding: utf-8", "languages:"]
    lines += [f"- {lang}" for lang in languages]
    lines += ["", "ignored_paths:", "- node_modules"]
    (serena_dir / "project.yml").write_text("\n".join(lines), encoding="utf-8")


def _write_mcp(project_dir, servers):
    (project_dir / ".mcp.json").write_text(
        json.dumps({"mcpServers": servers}), encoding="utf-8"
    )


def _configured_project(project_dir, languages=None, *, serena=True):
    _write_serena_project(project_dir, languages or _ALL_LANGUAGES)
    if serena:
        _write_mcp(project_dir, {"serena": {"type": "stdio"}})
    else:
        _write_mcp(project_dir, {"deepwiki": {"type": "http"}})
    return str(project_dir)


# ---------------------------------------------------------------------------
# detect_providers: capability binding (the load-bearing ADR-062 rule)
# ---------------------------------------------------------------------------


class TestCapabilityBinding:
    def test_python_symbol_navigation_has_serena_and_native(self, tmp_path):
        proj = _configured_project(tmp_path)
        result = detect_providers("src/app.py", SYMBOL_NAVIGATION, proj)
        assert result == ["serena", "native_lsp"]

    def test_typescript_symbol_navigation(self, tmp_path):
        proj = _configured_project(tmp_path)
        result = detect_providers("src/app.ts", SYMBOL_NAVIGATION, proj)
        assert result == ["serena", "native_lsp"]

    def test_bash_symbol_navigation(self, tmp_path):
        proj = _configured_project(tmp_path)
        result = detect_providers("run.sh", SYMBOL_NAVIGATION, proj)
        assert result == ["serena", "native_lsp"]

    def test_powershell_symbol_navigation(self, tmp_path):
        proj = _configured_project(tmp_path)
        assert detect_providers("mod.ps1", SYMBOL_NAVIGATION, proj) == ["serena", "native_lsp"]
        assert detect_providers("mod.psm1", SYMBOL_NAVIGATION, proj) == ["serena", "native_lsp"]

    def test_markdown_no_symbol_navigation(self, tmp_path):
        """Markdown has no symbol search that replaces grep (ADR-062 Sec 2)."""
        proj = _configured_project(tmp_path)
        assert detect_providers("README.md", SYMBOL_NAVIGATION, proj) == []

    def test_json_yaml_toml_no_symbol_navigation(self, tmp_path):
        proj = _configured_project(tmp_path)
        assert detect_providers("data.json", SYMBOL_NAVIGATION, proj) == []
        assert detect_providers("ci.yaml", SYMBOL_NAVIGATION, proj) == []
        assert detect_providers("ci.yml", SYMBOL_NAVIGATION, proj) == []
        assert detect_providers("pyproject.toml", SYMBOL_NAVIGATION, proj) == []

    def test_markdown_has_symbols_overview(self, tmp_path):
        """All 8 configured languages get symbols_overview (ADR-062 Sec 3)."""
        proj = _configured_project(tmp_path)
        assert detect_providers("README.md", SYMBOLS_OVERVIEW, proj) == ["serena"]

    def test_json_yaml_toml_have_symbols_overview(self, tmp_path):
        proj = _configured_project(tmp_path)
        assert detect_providers("data.json", SYMBOLS_OVERVIEW, proj) == ["serena"]
        assert detect_providers("ci.yaml", SYMBOLS_OVERVIEW, proj) == ["serena"]
        assert detect_providers("pyproject.toml", SYMBOLS_OVERVIEW, proj) == ["serena"]

    def test_python_symbols_overview_has_both(self, tmp_path):
        proj = _configured_project(tmp_path)
        assert detect_providers("src/app.py", SYMBOLS_OVERVIEW, proj) == ["serena", "native_lsp"]


# ---------------------------------------------------------------------------
# detect_providers: availability gating (config-only, fail-open)
# ---------------------------------------------------------------------------


class TestAvailability:
    def test_serena_absent_when_mcp_not_configured(self, tmp_path):
        proj = _configured_project(tmp_path, serena=False)
        # native_lsp still available for python; serena dropped.
        assert detect_providers("src/app.py", SYMBOL_NAVIGATION, proj) == ["native_lsp"]

    def test_serena_absent_when_language_not_configured(self, tmp_path):
        proj = _configured_project(tmp_path, languages=["python"])
        # typescript not in configured list -> serena unavailable; native still has it
        assert detect_providers("src/app.ts", SYMBOL_NAVIGATION, proj) == ["native_lsp"]

    def test_markdown_no_providers_when_serena_unconfigured(self, tmp_path):
        proj = _configured_project(tmp_path, serena=False)
        # markdown has no native LSP and serena is unconfigured -> empty (fail-open)
        assert detect_providers("README.md", SYMBOLS_OVERVIEW, proj) == []

    def test_unknown_extension_returns_empty(self, tmp_path):
        proj = _configured_project(tmp_path)
        assert detect_providers("image.png", SYMBOL_NAVIGATION, proj) == []
        assert detect_providers("image.png", SYMBOLS_OVERVIEW, proj) == []

    def test_serena_mcp_under_home_mcp_json(self, tmp_path, monkeypatch):
        """Serena registered in ~/.mcp.json (not project) is still detected."""
        proj = tmp_path / "proj"
        proj.mkdir()
        _write_serena_project(proj, _ALL_LANGUAGES)
        # project .mcp.json without serena
        _write_mcp(proj, {"deepwiki": {"type": "http"}})
        home = tmp_path / "home"
        home.mkdir()
        _write_mcp(home, {"serena": {"type": "stdio"}})
        monkeypatch.setattr(lsp_provider.Path, "home", classmethod(lambda cls: home))
        result = detect_providers("src/app.py", SYMBOLS_OVERVIEW, str(proj))
        assert result == ["serena", "native_lsp"]


# ---------------------------------------------------------------------------
# detect_providers: input validation / fail-open guards
# ---------------------------------------------------------------------------


class TestDetectProvidersGuards:
    def test_empty_file_path(self, tmp_path):
        proj = _configured_project(tmp_path)
        assert detect_providers("", SYMBOL_NAVIGATION, proj) == []

    def test_invalid_capability(self, tmp_path):
        proj = _configured_project(tmp_path)
        assert detect_providers("src/app.py", "hover", proj) == []

    def test_defaults_project_dir_to_cwd(self, tmp_path, monkeypatch):
        _configured_project(tmp_path)
        monkeypatch.setattr(lsp_provider.os, "getcwd", lambda: str(tmp_path))
        assert detect_providers("src/app.py", SYMBOLS_OVERVIEW) == ["serena", "native_lsp"]


# ---------------------------------------------------------------------------
# Config readers: malformed / missing config never raises
# ---------------------------------------------------------------------------


class TestConfigReaders:
    def test_missing_serena_yml_returns_empty_languages(self, tmp_path):
        assert lsp_provider._read_serena_languages(str(tmp_path)) == set()

    def test_unreadable_serena_yml_returns_empty(self, tmp_path):
        serena_dir = tmp_path / ".serena"
        serena_dir.mkdir()
        # Create project.yml as a directory so read_text raises OSError
        (serena_dir / "project.yml").mkdir()
        assert lsp_provider._read_serena_languages(str(tmp_path)) == set()

    def test_languages_empty_inline_list(self, tmp_path):
        serena_dir = tmp_path / ".serena"
        serena_dir.mkdir()
        (serena_dir / "project.yml").write_text(
            "languages: []\nencoding: utf-8\n", encoding="utf-8"
        )
        assert lsp_provider._read_serena_languages(str(tmp_path)) == set()

    def test_languages_block_stops_at_next_key(self, tmp_path):
        serena_dir = tmp_path / ".serena"
        serena_dir.mkdir()
        text = "languages:\n- python\n- typescript\nencoding: utf-8\n- not_a_language\n"
        (serena_dir / "project.yml").write_text(text, encoding="utf-8")
        result = lsp_provider._read_serena_languages(str(tmp_path))
        assert result == {"python", "typescript"}

    def test_languages_block_skips_comments_and_blanks(self, tmp_path):
        serena_dir = tmp_path / ".serena"
        serena_dir.mkdir()
        text = "languages:\n# a comment\n\n- python\n"
        (serena_dir / "project.yml").write_text(text, encoding="utf-8")
        assert lsp_provider._read_serena_languages(str(tmp_path)) == {"python"}

    def test_read_json_silent_missing_file(self, tmp_path):
        assert lsp_provider._read_json_silent(tmp_path / "nope.json") is None

    def test_read_json_silent_malformed(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert lsp_provider._read_json_silent(bad) is None

    def test_read_json_silent_directory(self, tmp_path):
        d = tmp_path / "adir.json"
        d.mkdir()
        assert lsp_provider._read_json_silent(d) is None

    def test_serena_mcp_configured_non_dict_servers(self, tmp_path):
        _write_mcp(tmp_path, [])  # mcpServers will be a list value below
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": ["serena"]}), encoding="utf-8"
        )
        assert lsp_provider._serena_mcp_configured(str(tmp_path)) is False

    def test_serena_mcp_configured_top_level_not_dict(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(json.dumps(["serena"]), encoding="utf-8")
        assert lsp_provider._serena_mcp_configured(str(tmp_path)) is False

    def test_serena_mcp_configured_plugin_wrapped_name(self, tmp_path):
        _write_mcp(tmp_path, {"plugin_x_serena": {"type": "stdio"}})
        assert lsp_provider._serena_mcp_configured(str(tmp_path)) is True

    def test_parse_languages_no_block(self):
        assert lsp_provider._parse_languages_block("encoding: utf-8\nname: x\n") == set()

    def test_language_offers_capability_invalid(self):
        # Defensive guard: an unknown capability never qualifies.
        assert lsp_provider._language_offers_capability("python", "hover") is False

    def test_native_lsp_available_invalid_capability(self):
        assert lsp_provider._native_lsp_available("app.py", "hover") is False


# ---------------------------------------------------------------------------
# is_code_target
# ---------------------------------------------------------------------------


class TestIsCodeTarget:
    def test_python_symbol_navigation(self):
        assert is_code_target("app.py", SYMBOL_NAVIGATION) is True

    def test_markdown_no_symbol_navigation(self):
        assert is_code_target("README.md", SYMBOL_NAVIGATION) is False

    def test_markdown_symbols_overview(self):
        assert is_code_target("README.md", SYMBOLS_OVERVIEW) is True

    def test_native_only_extension_symbol_navigation(self):
        # .go is not a serena-configured ext here but is native LSP code
        assert is_code_target("main.go", SYMBOL_NAVIGATION) is True

    def test_native_only_extension_symbols_overview(self):
        assert is_code_target("main.go", SYMBOLS_OVERVIEW) is True

    def test_unknown_extension(self):
        assert is_code_target("photo.png", SYMBOL_NAVIGATION) is False
        assert is_code_target("photo.png", SYMBOLS_OVERVIEW) is False

    def test_empty_target(self):
        assert is_code_target("", SYMBOL_NAVIGATION) is False

    def test_invalid_capability(self):
        assert is_code_target("app.py", "hover") is False


# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_serena_tools_present(self):
        tools = lsp_provider.PROVIDERS["serena"]["tools"]
        assert tools["definition"] == "find_symbol"
        assert tools["references"] == "find_referencing_symbols"
        assert tools["overview"] == "get_symbols_overview"
        assert tools["implementation"] == "find_implementations"
        assert tools["diagnostics"] == "get_diagnostics_for_file"

    def test_native_lsp_tools_present(self):
        tools = lsp_provider.PROVIDERS["native_lsp"]["tools"]
        assert tools["definition"] == "goToDefinition"
        assert tools["references"] == "findReferences"
        assert tools["symbol_search"] == "workspaceSymbol"
        assert tools["implementation"] == "goToImplementation"


# ---------------------------------------------------------------------------
# Issue #2199: YAML language parsing hardening
# ---------------------------------------------------------------------------


class TestYamlLanguageParsingFixes:
    """Regression tests for #2199 problem 3: brittle YAML parsing.

    The original parser dropped flow-style lists (``languages: [python]``)
    and inline comments (``- python  # comment``) silently, leaving the
    configured-languages set empty and degrading every guard to allow.
    """

    def test_flow_style_languages_list(self, tmp_path):
        serena_dir = tmp_path / ".serena"
        serena_dir.mkdir()
        (serena_dir / "project.yml").write_text(
            "languages: [python, typescript, go]\nencoding: utf-8\n",
            encoding="utf-8",
        )
        result = lsp_provider._read_serena_languages(str(tmp_path))
        assert result == {"python", "typescript", "go"}

    def test_flow_style_with_quotes(self, tmp_path):
        serena_dir = tmp_path / ".serena"
        serena_dir.mkdir()
        (serena_dir / "project.yml").write_text(
            "languages: ['python', \"typescript\"]\n",
            encoding="utf-8",
        )
        assert lsp_provider._read_serena_languages(str(tmp_path)) == {
            "python",
            "typescript",
        }

    def test_block_style_with_inline_comments(self, tmp_path):
        serena_dir = tmp_path / ".serena"
        serena_dir.mkdir()
        (serena_dir / "project.yml").write_text(
            "languages:\n- python  # primary language\n- typescript # frontend\n- bash#nospace_no_comment\n",
            encoding="utf-8",
        )
        # Inline comments stripped only when '#' has leading whitespace; the
        # third entry's '#' is part of the token (intentional behavior).
        result = lsp_provider._read_serena_languages(str(tmp_path))
        assert "python" in result
        assert "typescript" in result

    def test_flow_style_with_inline_comment(self, tmp_path):
        serena_dir = tmp_path / ".serena"
        serena_dir.mkdir()
        (serena_dir / "project.yml").write_text(
            "languages: [python, typescript]  # primary stack\n",
            encoding="utf-8",
        )
        assert lsp_provider._read_serena_languages(str(tmp_path)) == {
            "python",
            "typescript",
        }

    def test_flow_style_empty_brackets(self, tmp_path):
        serena_dir = tmp_path / ".serena"
        serena_dir.mkdir()
        (serena_dir / "project.yml").write_text(
            "languages: [ ]\nencoding: utf-8\n", encoding="utf-8"
        )
        assert lsp_provider._read_serena_languages(str(tmp_path)) == set()

    def test_strip_inline_comment_helper(self):
        assert lsp_provider._strip_inline_comment("- python  # note") == "- python"
        assert lsp_provider._strip_inline_comment("# whole line") == ""
        assert lsp_provider._strip_inline_comment("- name#tight") == "- name#tight"


# ---------------------------------------------------------------------------
# Issue #2199: MCP config discovery broadened to ~/.claude locations
# ---------------------------------------------------------------------------


class TestClaudeMcpConfigDiscovery:
    """Regression tests for #2199 problem 2: Serena registered under
    ``~/.claude/settings.json`` or ``~/.claude/mcp.json`` was previously
    invisible, so every guard degraded to allow on those installs.
    """

    def test_serena_under_claude_settings_json(self, tmp_path, monkeypatch):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write_serena_project(proj, _ALL_LANGUAGES)
        # No project .mcp.json, no ~/.mcp.json, only ~/.claude/settings.json
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "settings.json").write_text(
            json.dumps({"mcpServers": {"serena": {"type": "stdio"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(lsp_provider.Path, "home", classmethod(lambda cls: home))
        assert lsp_provider._serena_mcp_configured(str(proj)) is True

    def test_serena_under_claude_mcp_json(self, tmp_path, monkeypatch):
        proj = tmp_path / "proj"
        proj.mkdir()
        _write_serena_project(proj, _ALL_LANGUAGES)
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "mcp.json").write_text(
            json.dumps({"mcpServers": {"my_serena": {"type": "stdio"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(lsp_provider.Path, "home", classmethod(lambda cls: home))
        assert lsp_provider._serena_mcp_configured(str(proj)) is True

    def test_candidate_list_includes_claude_locations(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(lsp_provider.Path, "home", classmethod(lambda cls: home))
        candidates = lsp_provider._mcp_config_candidates(str(tmp_path))
        # Should include the two ~/.claude/* paths added for #2199.
        assert (home / ".claude" / "settings.json") in candidates
        assert (home / ".claude" / "mcp.json") in candidates


# ---------------------------------------------------------------------------
# Issue #2199: Representative-extension helper + public configured_languages
# ---------------------------------------------------------------------------


class TestRepresentativeExtension:
    def test_python(self):
        assert lsp_provider.representative_extension_for_language("python") == ".py"

    def test_typescript(self):
        assert lsp_provider.representative_extension_for_language("typescript") == ".ts"

    def test_case_insensitive(self):
        assert lsp_provider.representative_extension_for_language("Python") == ".py"

    def test_unknown(self):
        assert (
            lsp_provider.representative_extension_for_language("rust") is None
        )

    def test_configured_languages_public(self, tmp_path):
        _configured_project(tmp_path, ["python", "typescript"])
        assert lsp_provider.configured_languages(str(tmp_path)) == {
            "python",
            "typescript",
        }
