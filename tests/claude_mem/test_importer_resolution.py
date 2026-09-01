"""Tests for importer path resolution in .claude-mem/scripts/import_claude_mem_memories.py.

Split out of tests/test_claude_mem_scripts.py, which covers the export scripts.
The importer's resolution contract (precedence, blank handling, tilde expansion,
exit codes) grew past the point where one module could hold both without
breaching the 500-line taste-lint ceiling.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Import the module under test by file path since it lives outside scripts/.

_base = os.path.join(os.path.dirname(__file__), "..", "..", ".claude-mem", "scripts")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_base, filename))
    assert spec is not None, f"Failed to find {filename}"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None, f"Module spec for {filename} has no loader"
    # dataclasses resolves a class's module through sys.modules, so a module
    # executed without registration raises AttributeError at class creation.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_import_mem = _load("import_claude_mem_memories", "import_claude_mem_memories.py")


# Pinned independently of the implementation. Deriving this by calling
# claude_default_importer() would make the fixture and the assertions share one
# derivation, so a default that moved to the wrong location would move both
# together and every test below would stay green.
_CLAUDE_DEFAULT_SUFFIX = Path(".claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts")


def _make_claude_default(home: Path) -> Path:
    """Create the Claude Code plugin importer under a fake home."""
    importer = home / _CLAUDE_DEFAULT_SUFFIX
    importer.parent.mkdir(parents=True, exist_ok=True)
    importer.write_text("// stub importer", encoding="utf-8")
    return importer


class TestClaudeDefaultImporter:
    def test_default_location_matches_the_pinned_marketplace_path(self, tmp_path: Path) -> None:
        """Anchor the derivation every default-path test depends on."""
        assert _import_mem.claude_default_importer(tmp_path) == tmp_path / _CLAUDE_DEFAULT_SUFFIX


class TestResolveImporter:
    def test_uses_claude_plugin_default_when_nothing_configured(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        _make_claude_default(home)

        resolution = _import_mem.resolve_importer(None, {}, home)

        assert resolution.path == home / _CLAUDE_DEFAULT_SUFFIX
        assert resolution.is_configured is False

    def test_explicit_argument_outranks_environment_and_default(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        _make_claude_default(home)
        explicit = tmp_path / "explicit.ts"
        env = {_import_mem.IMPORTER_ENV_VAR: str(tmp_path / "from-env.ts")}

        resolution = _import_mem.resolve_importer(str(explicit), env, home)

        assert resolution.path == explicit
        assert resolution.is_configured is True

    def test_environment_outranks_default(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        _make_claude_default(home)
        from_env = tmp_path / "from-env.ts"
        env = {_import_mem.IMPORTER_ENV_VAR: str(from_env)}

        resolution = _import_mem.resolve_importer(None, env, home)

        assert resolution.path == from_env
        assert resolution.is_configured is True

    @pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "whitespace"])
    def test_blank_environment_value_falls_through_to_default(
        self, blank: str, tmp_path: Path
    ) -> None:
        home = tmp_path / "home"
        expected = _make_claude_default(home)
        env = {_import_mem.IMPORTER_ENV_VAR: blank}

        resolution = _import_mem.resolve_importer(None, env, home)

        assert resolution.path == expected
        assert resolution.is_configured is False

    def test_expands_tilde_against_injected_home_not_process_environment(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # The process HOME points somewhere real and different, so a resolution
        # that leaked to Path.expanduser() would resolve there instead.
        process_home = tmp_path / "process-home"
        process_home.mkdir()
        monkeypatch.setenv("HOME", str(process_home))
        monkeypatch.setenv("USERPROFILE", str(process_home))
        injected_home = tmp_path / "injected-home"

        resolution = _import_mem.resolve_importer("~/importer.ts", {}, injected_home)

        assert resolution.path == injected_home / "importer.ts"
        assert resolution.path != process_home / "importer.ts"

    def test_expands_tilde_in_environment_value_against_injected_home(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        process_home = tmp_path / "process-home"
        process_home.mkdir()
        monkeypatch.setenv("HOME", str(process_home))
        monkeypatch.setenv("USERPROFILE", str(process_home))
        injected_home = tmp_path / "injected-home"
        env = {_import_mem.IMPORTER_ENV_VAR: "~/from-env.ts"}

        resolution = _import_mem.resolve_importer(None, env, injected_home)

        assert resolution.path == injected_home / "from-env.ts"

    def test_leaves_other_user_tilde_literal(self, tmp_path: Path) -> None:
        resolution = _import_mem.resolve_importer("~someone/importer.ts", {}, tmp_path)

        assert resolution.path == Path("~someone/importer.ts")

    def test_other_user_tilde_stays_relative_and_reaches_no_home(self, tmp_path: Path) -> None:
        """The security-relevant half of the documented behavior.

        expand_home documents this branch as a non-expansion, not a rejection.
        What must hold is that the result stays relative and keeps the literal
        segment, so it can never resolve against a stranger's home. Whether the
        caller's existence check later fails depends on the process working
        directory and is deliberately not asserted.
        """
        resolution = _import_mem.resolve_importer("~someone/importer.ts", {}, tmp_path)

        assert resolution.path is not None
        assert not resolution.path.is_absolute()
        assert resolution.path.parts[0] == "~someone"

    def test_bare_tilde_resolves_to_home(self, tmp_path: Path) -> None:
        assert _import_mem.expand_home("~", tmp_path) == tmp_path

    def test_backslash_tilde_resolves_against_home(self, tmp_path: Path) -> None:
        """The `~\\` branch a Windows-style argument reaches."""
        assert _import_mem.expand_home("~\\importer.ts", tmp_path) == tmp_path / "importer.ts"

    def test_plain_path_is_left_alone(self, tmp_path: Path) -> None:
        assert _import_mem.expand_home("/opt/importer.ts", tmp_path) == Path("/opt/importer.ts")

    @pytest.mark.parametrize(
        "raw",
        ["~//importer.ts", "~///importer.ts", "~\\\\importer.ts", "~/\\importer.ts"],
        ids=["double-slash", "triple-slash", "double-backslash", "mixed"],
    )
    def test_repeated_separator_still_resolves_under_home(self, raw: str, tmp_path: Path) -> None:
        """Path.__truediv__ discards its left operand when the right side is rooted.

        Slicing `~/` off `~//importer.ts` leaves `/importer.ts`, so joining it
        unstripped returns `/importer.ts` and drops home entirely.
        """
        assert _import_mem.expand_home(raw, tmp_path) == tmp_path / "importer.ts"

    @pytest.mark.parametrize("raw", ["~/", "~//"], ids=["slash", "double-slash"])
    def test_tilde_with_only_separators_is_home(self, raw: str, tmp_path: Path) -> None:
        assert _import_mem.expand_home(raw, tmp_path) == tmp_path

    @pytest.mark.parametrize(
        "raw",
        [" /opt/spaced.ts", "/opt/spaced.ts ", " /opt/spaced.ts "],
        ids=["leading", "trailing", "both"],
    )
    def test_argument_edge_whitespace_survives_into_the_path(
        self, raw: str, tmp_path: Path
    ) -> None:
        """Blankness is detected with strip(); the resolved path keeps the original."""
        resolution = _import_mem.resolve_importer(raw, {}, tmp_path)

        assert resolution.path == Path(raw)
        assert resolution.source == _import_mem._SOURCE_ARGUMENT

    def test_environment_edge_whitespace_survives_into_the_path(self, tmp_path: Path) -> None:
        raw = " /opt/spaced.ts "
        env = {_import_mem.IMPORTER_ENV_VAR: raw}

        resolution = _import_mem.resolve_importer(None, env, tmp_path)

        assert resolution.path == Path(raw)
        assert resolution.source == _import_mem._SOURCE_ENVIRONMENT

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("", True), ("   ", True), ("\t\n", True), ("/opt/x.ts", False), (" /opt/x.ts ", False)],
        ids=["empty", "spaces", "tabs-newline", "path", "spaced-path"],
    )
    def test_is_blank_detects_only_all_whitespace(self, raw: str, expected: bool) -> None:
        assert _import_mem.is_blank(raw) is expected

    @pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "whitespace"])
    def test_blank_explicit_argument_is_configured_not_unset(
        self, blank: str, tmp_path: Path
    ) -> None:
        home = tmp_path / "home"
        _make_claude_default(home)
        env = {_import_mem.IMPORTER_ENV_VAR: str(tmp_path / "from-env.ts")}

        resolution = _import_mem.resolve_importer(blank, env, home)

        assert resolution.path is None
        assert resolution.source == _import_mem._SOURCE_ARGUMENT_BLANK
        assert resolution.is_configured is True

    def test_reports_unset_when_plugin_absent(self, tmp_path: Path) -> None:
        resolution = _import_mem.resolve_importer(None, {}, tmp_path / "empty-home")

        assert resolution.path is None
        assert resolution.is_configured is False


class TestImporterReachesSubprocess:
    """Prove the resolved path is what gets executed, not just what gets resolved.

    Every other subprocess stub here ignores argv, so hardcoding a wrong path at
    the call site would leave them all green. These assert on the recorded argv.
    """

    @staticmethod
    def _record_calls(monkeypatch) -> list[list[str]]:
        calls: list[list[str]] = []

        def _fake_run(argv, **_kwargs):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")

        monkeypatch.setattr(_import_mem.subprocess, "run", _fake_run)
        return calls

    @staticmethod
    def _memories_with_one_file(tmp_path: Path, monkeypatch) -> Path:
        memories = tmp_path / "memories"
        memories.mkdir()
        memory_file = memories / "shared.json"
        memory_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)
        return memory_file

    def test_explicit_importer_is_passed_to_subprocess(self, tmp_path: Path, monkeypatch) -> None:
        importer = tmp_path / "explicit-importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memory_file = self._memories_with_one_file(tmp_path, monkeypatch)
        calls = self._record_calls(monkeypatch)

        assert _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path) == 0

        assert calls == [["npx", "tsx", str(importer), str(memory_file)]]

    def test_environment_importer_is_passed_to_subprocess(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        importer = tmp_path / "env-importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        self._memories_with_one_file(tmp_path, monkeypatch)
        calls = self._record_calls(monkeypatch)
        env = {_import_mem.IMPORTER_ENV_VAR: str(importer)}

        assert _import_mem.main([], env=env, home=tmp_path) == 0

        assert str(importer) in calls[0]

    def test_subprocess_decodes_utf8_with_replacement(self, tmp_path: Path, monkeypatch) -> None:
        """Locale-independent decoding: npx output must not raise UnicodeDecodeError."""
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        self._memories_with_one_file(tmp_path, monkeypatch)
        recorded: dict[str, object] = {}

        def _fake_run(argv, **kwargs):
            recorded.update(kwargs)
            return subprocess.CompletedProcess(argv, 0, "", "")

        monkeypatch.setattr(_import_mem.subprocess, "run", _fake_run)

        assert _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path) == 0

        assert recorded["encoding"] == "utf-8"
        assert recorded["errors"] == "replace"


class TestVanishedImporterUsesStoredClassification:
    """The exit code must come from the stored source, not a second existence check.

    resolve_importer returns a default only when it exists, so a default that is
    removed between resolution and use reaches main as a non-None path that no
    longer exists. Deciding from existence alone reports exit 1 for an optional
    plugin the caller never configured. These tests build that post-race state
    directly by returning a crafted ImporterResolution.
    """

    @staticmethod
    def _resolve_to(monkeypatch, path: Path, source: str) -> None:
        monkeypatch.setattr(
            _import_mem,
            "resolve_importer",
            lambda *_args, **_kwargs: _import_mem.ImporterResolution(path, source),
        )

    def test_exits_0_when_default_vanishes_after_resolution(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        self._resolve_to(monkeypatch, tmp_path / "vanished.ts", _import_mem._SOURCE_DEFAULT)

        result = _import_mem.main([], env={}, home=tmp_path)

        assert result == 0
        assert "SKIP" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "source",
        [_import_mem._SOURCE_ARGUMENT, _import_mem._SOURCE_ENVIRONMENT],
        ids=["argument", "environment"],
    )
    def test_exits_1_when_configured_path_vanishes_after_resolution(
        self, source: str, tmp_path: Path, monkeypatch
    ) -> None:
        self._resolve_to(monkeypatch, tmp_path / "vanished.ts", source)

        result = _import_mem.main([], env={}, home=tmp_path)

        assert result == 1


class TestImportMemoriesMain:
    def test_exits_0_and_skips_when_optional_plugin_absent(self, tmp_path: Path, capsys) -> None:
        result = _import_mem.main([], env={}, home=tmp_path / "empty-home")

        assert result == 0
        assert "SKIP" in capsys.readouterr().out

    def test_exits_1_when_explicit_importer_does_not_exist(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing-importer.ts"

        result = _import_mem.main(["--importer", str(missing)], env={}, home=tmp_path)

        assert result == 1

    def test_exits_1_when_configured_environment_importer_does_not_exist(
        self, tmp_path: Path
    ) -> None:
        env = {_import_mem.IMPORTER_ENV_VAR: str(tmp_path / "missing-importer.ts")}

        result = _import_mem.main([], env=env, home=tmp_path)

        assert result == 1

    def test_exits_1_when_configured_importer_fails(self, tmp_path: Path, monkeypatch) -> None:
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "memories"
        memories.mkdir()
        (memories / "shared.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)
        monkeypatch.setattr(
            _import_mem.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 3, "", "boom"),
        )

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 1

    def test_exits_0_when_configured_importer_succeeds(self, tmp_path: Path, monkeypatch) -> None:
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "memories"
        memories.mkdir()
        (memories / "shared.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)
        monkeypatch.setattr(
            _import_mem.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, "", ""),
        )

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 0

    def test_exits_0_when_no_memory_files_present(self, tmp_path: Path, monkeypatch) -> None:
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "memories"
        memories.mkdir()
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 0

    def test_creates_the_memories_dir_when_it_is_absent(self, tmp_path: Path, monkeypatch) -> None:
        """The absent-directory branch, which the empty-directory case never reaches."""
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "memories"
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)
        assert not memories.exists()

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 0
        assert memories.is_dir()

    def test_creates_nested_memories_dir_when_parents_are_absent(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """parents=True is load-bearing: the parent may not exist either."""
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "absent-parent" / "memories"
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 0
        assert memories.is_dir()

    @pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "whitespace"])
    def test_exits_1_when_explicit_argument_is_blank(self, blank: str, tmp_path: Path) -> None:
        home = tmp_path / "home"
        _make_claude_default(home)
        env = {_import_mem.IMPORTER_ENV_VAR: str(_make_claude_default(tmp_path / "other"))}

        result = _import_mem.main(["--importer", blank], env=env, home=home)

        # A usable env value and a usable default both exist; the blank argument
        # must still fail rather than fall through to either of them.
        assert result == 1

    def test_exits_1_when_importer_binary_is_unavailable(self, tmp_path: Path, monkeypatch) -> None:
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "memories"
        memories.mkdir()
        (memories / "shared.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

        def _raise(*_args, **_kwargs):
            raise FileNotFoundError("npx not on PATH")

        monkeypatch.setattr(_import_mem.subprocess, "run", _raise)

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 1
