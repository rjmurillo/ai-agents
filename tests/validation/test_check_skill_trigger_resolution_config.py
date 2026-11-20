"""Config-error and resolver-failure tests for check_skill_trigger_resolution.py.

Every case exits 2 and names its cause on stderr. Fixtures: `trigger_resolution_fixtures`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.validation import check_skill_trigger_resolution as gate
from tests.validation.trigger_resolution_fixtures import (
    _baseline,
    _run,
    _skill,
    _skills,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    return tmp_path


_RESOLVER_MODULE = "autoplan_resolve_route_gate"


def _quoted_skill(repo: Path) -> None:
    """One skill whose description carries a quoted phrase, so the zero-phrase guard passes."""
    _skill(_skills(repo), "w", 'Use for "write a widget".', ["write widget"])


def _config_error(repo: Path, baseline: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """Run the gate, require exit 2, and return stderr."""
    assert _run(repo, baseline) == gate.EXIT_CONFIG
    err = capsys.readouterr().err
    assert err.startswith("[CONFIG]"), err
    return err


def _full_violations(**overrides: object) -> dict[str, object]:
    """A schema-valid violations map with every check present, then overrides applied."""
    violations: dict[str, object] = {check: {} for check in gate.CHECKS}
    violations.update(overrides)
    return violations


def _stub_resolver(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str) -> None:
    stub = tmp_path / "stub_resolver.py"
    stub.write_text(body, encoding="utf-8")
    monkeypatch.setattr(gate, "RESOLVER", stub)
    monkeypatch.setattr(gate, "_RESOLVER_CACHE", {})
    monkeypatch.delitem(sys.modules, _RESOLVER_MODULE, raising=False)


class TestConfigErrors:
    """Every case carries a quoted phrase so the zero-phrase guard cannot mask the cause."""

    @pytest.mark.parametrize(
        ("payload", "cause"),
        [
            ("not json", "unreadable or not JSON"),
            ("[]", "is not a JSON object"),
            (json.dumps({"schema_version": "9", "violations": {}}), "needs schema_version"),
            (
                json.dumps({"schema_version": "1", "violations": [1]}),
                "needs schema_version",
            ),
            (
                json.dumps({"schema_version": "1", "violations": {gate.CHECK_OWN: {}}}),
                "must hold exactly the checks",
            ),
            (
                json.dumps(
                    {"schema_version": "1", "violations": _full_violations(**{gate.CHECK_OWN: []})}
                ),
                "is not a mapping",
            ),
            (
                json.dumps(
                    {
                        "schema_version": "1",
                        "violations": _full_violations(**{gate.CHECK_OWN: {"s": "p"}}),
                    }
                ),
                "is not a list of phrases",
            ),
            (
                json.dumps(
                    {
                        "schema_version": "1",
                        "violations": _full_violations(**{gate.CHECK_OWN: {"s": [1]}}),
                    }
                ),
                "is not a list of phrases",
            ),
        ],
    )
    def test_bad_baseline_exits_2_naming_the_cause(
        self, repo: Path, capsys: pytest.CaptureFixture[str], payload: str, cause: str
    ) -> None:
        _quoted_skill(repo)
        bad = repo / "bad.json"
        bad.write_text(payload, encoding="utf-8")
        err = _config_error(repo, bad, capsys)
        assert cause in err
        assert str(bad) in err

    def test_missing_baseline_exits_2_naming_the_path(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _quoted_skill(repo)
        absent = repo / "absent.json"
        err = _config_error(repo, absent, capsys)
        assert "unreadable or not JSON" in err
        assert str(absent) in err

    def test_non_utf8_baseline_exits_2(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _quoted_skill(repo)
        bad = repo / "bad.json"
        bad.write_bytes(b"\xff\xfe\x00")
        assert "unreadable or not JSON" in _config_error(repo, bad, capsys)

    def test_zero_trigger_phrases_exits_2_even_with_a_valid_baseline(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _skill(_skills(repo), "w", "Makes widgets.", ["write widget"])
        err = _config_error(repo, _baseline(repo), capsys)
        assert "0 trigger phrases" in err

    def test_missing_skills_dir_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert gate.main(["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "b")]) == 2
        assert "skills directory does not exist" in capsys.readouterr().err

    def test_empty_skills_dir_exits_2(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        err = _config_error(repo, _baseline(repo), capsys)
        assert "no SKILL.md files" in err

    def test_skill_without_frontmatter_exits_2(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        folder = _skills(repo) / "broken"
        folder.mkdir()
        (folder / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")
        assert "no YAML frontmatter" in _config_error(repo, _baseline(repo), capsys)

    def test_skill_without_description_exits_2(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        folder = _skills(repo) / "broken"
        folder.mkdir()
        (folder / "SKILL.md").write_text("---\nname: broken\n---\nBody\n", encoding="utf-8")
        assert "description missing" in _config_error(repo, _baseline(repo), capsys)

    def test_non_list_intents_exit_2(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        folder = _skills(repo) / "broken"
        folder.mkdir()
        (folder / "SKILL.md").write_text(
            "---\nname: broken\ndescription: x y\nmetadata:\n  routing:\n"
            "    role: front-door\n    intents: nope\n---\n",
            encoding="utf-8",
        )
        assert "intents must be a list of strings" in _config_error(repo, _baseline(repo), capsys)

    def test_undecodable_skill_md_exits_2(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        folder = _skills(repo) / "broken"
        folder.mkdir()
        (folder / "SKILL.md").write_bytes(b"---\nname: \xff\xfe\n---\n")
        assert "unreadable" in _config_error(repo, _baseline(repo), capsys)

    def test_skill_md_that_is_a_directory_exits_2(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (_skills(repo) / "broken" / "SKILL.md").mkdir(parents=True)
        assert "unreadable" in _config_error(repo, _baseline(repo), capsys)

    def test_unparseable_frontmatter_exits_2(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        folder = _skills(repo) / "broken"
        folder.mkdir()
        (folder / "SKILL.md").write_text("---\nname: [unclosed\n---\nBody\n", encoding="utf-8")
        assert "frontmatter does not parse" in _config_error(repo, _baseline(repo), capsys)

    def test_non_mapping_frontmatter_exits_2(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        folder = _skills(repo) / "broken"
        folder.mkdir()
        (folder / "SKILL.md").write_text("---\n- a\n- b\n---\nBody\n", encoding="utf-8")
        assert "frontmatter is not a mapping" in _config_error(repo, _baseline(repo), capsys)

    def test_write_baseline_from_outside_the_repo_exits_2_and_writes_nothing(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        _quoted_skill(repo)
        monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))
        target = repo / "out.json"
        assert _run(repo, target, "--write-baseline") == gate.EXIT_CONFIG
        assert "current directory is outside" in capsys.readouterr().err
        assert not target.exists()


class TestResolverFailures:
    """The resolver is loaded from a file and called per phrase; every failure is exit 2."""

    def test_missing_resolver_file_exits_2(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _quoted_skill(repo)
        monkeypatch.setattr(gate, "RESOLVER", tmp_path / "missing_resolver.py")
        monkeypatch.setattr(gate, "_RESOLVER_CACHE", {})
        assert "cannot load resolver" in _config_error(repo, _baseline(repo), capsys)

    def test_resolver_with_no_loader_exits_2(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _quoted_skill(repo)
        not_python = tmp_path / "resolver.txt"
        not_python.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(gate, "RESOLVER", not_python)
        monkeypatch.setattr(gate, "_RESOLVER_CACHE", {})
        assert "cannot load resolver" in _config_error(repo, _baseline(repo), capsys)

    def test_resolver_without_main_exits_2_and_leaves_no_module(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _quoted_skill(repo)
        _stub_resolver(monkeypatch, tmp_path, "VALUE = 1\n")
        assert "defines no callable main" in _config_error(repo, _baseline(repo), capsys)
        assert _RESOLVER_MODULE not in sys.modules

    @pytest.mark.parametrize(
        ("body", "cause"),
        [
            ("undefined_name\n", "NameError"),
            ("raise RuntimeError('boom')\n", "RuntimeError"),
            ("raise KeyError('k')\n", "KeyError"),
            ("def main(:\n", "SyntaxError"),
            ("import module_that_does_not_exist_xyz\n", "ModuleNotFoundError"),
        ],
    )
    def test_import_time_failure_exits_2_and_leaves_no_module(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        body: str,
        cause: str,
    ) -> None:
        _quoted_skill(repo)
        _stub_resolver(monkeypatch, tmp_path, body)
        err = _config_error(repo, _baseline(repo), capsys)
        assert "cannot load resolver" in err
        assert cause in err
        assert _RESOLVER_MODULE not in sys.modules

    @pytest.mark.parametrize(
        ("exc", "cause"),
        [
            ("NameError('n')", "NameError"),
            ("RuntimeError('r')", "RuntimeError"),
            ("KeyError('k')", "KeyError"),
        ],
    )
    def test_main_crash_exits_2_naming_the_exception(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        exc: str,
        cause: str,
    ) -> None:
        _quoted_skill(repo)
        _stub_resolver(monkeypatch, tmp_path, f"def main(argv):\n    raise {exc}\n")
        err = _config_error(repo, _baseline(repo), capsys)
        assert "resolver crashed" in err
        assert cause in err

    @pytest.mark.parametrize(
        ("body", "code"),
        [
            (
                "import sys\n\ndef main(argv):\n    print('bad', file=sys.stderr)\n    return 3\n",
                "3",
            ),
            ("def main(argv):\n    raise SystemExit(4)\n", "4"),
            ("def main(argv):\n    raise SystemExit('text')\n", "2"),
        ],
    )
    def test_resolver_nonzero_exit_exits_2(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        body: str,
        code: str,
    ) -> None:
        _quoted_skill(repo)
        _stub_resolver(monkeypatch, tmp_path, body)
        err = _config_error(repo, _baseline(repo), capsys)
        assert f"resolver exited {code}" in err
        assert "'write a widget'" in err

    def test_resolver_output_that_is_not_json_exits_2(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _quoted_skill(repo)
        _stub_resolver(
            monkeypatch, tmp_path, "def main(argv):\n    print('not json')\n    return 0\n"
        )
        assert "output is not JSON" in _config_error(repo, _baseline(repo), capsys)

    @pytest.mark.parametrize("output", ['{"route": "x"}', "[]", '"kind"'])
    def test_resolver_output_without_kind_exits_2(
        self,
        repo: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        output: str,
    ) -> None:
        _quoted_skill(repo)
        body = f"def main(argv):\n    print({output!r})\n    return 0\n"
        _stub_resolver(monkeypatch, tmp_path, body)
        assert "has no `kind`" in _config_error(repo, _baseline(repo), capsys)

    def test_well_formed_stub_output_is_graded_not_rejected(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Control: the stub harness itself does not force exit 2."""
        _quoted_skill(repo)
        body = 'def main(argv):\n    print(\'{"kind": "none"}\')\n    return 0\n'
        _stub_resolver(monkeypatch, tmp_path, body)
        baseline = _baseline(repo, own={"w": ["write a widget"]})
        assert _run(repo, baseline) == gate.EXIT_OK
