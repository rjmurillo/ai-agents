"""Tests for `.claude/skills/chestertons-fence/scripts/investigate.py`.

Security-critical: locks the M7 `run_git` verb allowlist and transport-
flag denylist that block git argv-level RCE vectors (`--upload-pack=`,
`--exec=`). Without these tests, a future contributor could relax the
allowlist or swap the order of checks and silently re-introduce the
class of bug.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "chestertons-fence" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import investigate

# ADR encoding --------------------------------------------------------------


def test_find_related_adrs_reads_utf8_explicitly(tmp_path: Path, monkeypatch) -> None:
    adr_dir = tmp_path / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    adr_file = adr_dir / "ADR-999-utf8.md"
    adr_file.write_text(
        '# ADR-999: UTF-8 ”quote”\n\nReferences target_component.py.\n',
        encoding="utf-8",
    )
    original_read_text = Path.read_text

    def read_text_with_cp1252_default(path: Path, encoding=None, **kwargs):
        return original_read_text(path, encoding=encoding or "cp1252", **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text_with_cp1252_default)
    monkeypatch.chdir(tmp_path)

    related_adrs = investigate.find_related_adrs("target_component.py")

    assert related_adrs == ["ADR-999-utf8.md: ADR-999: UTF-8 ”quote”"]


def test_generate_report_reads_template_utf8_explicitly(
    tmp_path: Path, monkeypatch
) -> None:
    skill_dir = tmp_path / "chestertons-fence"
    template_dir = skill_dir / "templates"
    template_dir.mkdir(parents=True)
    template_path = template_dir / "chestertons-fence-investigation.md"
    template_path.write_text(
        "# Report for [Component/System Name]: café “quote”\n",
        encoding="utf-8",
    )
    script_path = skill_dir / "scripts" / "investigate.py"
    script_path.parent.mkdir()
    monkeypatch.setattr(investigate, "__file__", str(script_path))
    original_read_text = Path.read_text

    def read_text_with_cp1252_default(path: Path, encoding=None, **kwargs):
        return original_read_text(path, encoding=encoding or "cp1252", **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text_with_cp1252_default)

    report = investigate.generate_report(
        investigate.InvestigationResult("target.py", "test template encoding")
    )

    assert "# Report for target.py: café “quote”" in report


def test_main_reports_invalid_utf8_adr_path(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    adr_dir = tmp_path / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    adr_file = adr_dir / "ADR-999-invalid.md"
    invalid_content = b"# Invalid UTF-8\n\nReferences target.py.\n\xff"
    adr_file.write_bytes(invalid_content)
    with pytest.raises(UnicodeDecodeError) as expected_error:
        invalid_content.decode("utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "investigate.py",
            "--target",
            "target.py",
            "--change",
            "test invalid ADR",
            "--format",
            "json",
        ],
    )

    exit_code = investigate.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert str(adr_file.relative_to(tmp_path)) in captured.err
    assert "UTF-8" in captured.err
    assert str(expected_error.value) in captured.err


def test_main_reports_invalid_utf8_template_path(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    skill_dir = tmp_path / "chestertons-fence"
    template_dir = skill_dir / "templates"
    template_dir.mkdir(parents=True)
    template_path = template_dir / "chestertons-fence-investigation.md"
    template_path.write_bytes(b"# Invalid UTF-8\n\xff")
    script_path = skill_dir / "scripts" / "investigate.py"
    script_path.parent.mkdir()
    monkeypatch.setattr(investigate, "__file__", str(script_path))
    monkeypatch.setattr(
        investigate,
        "investigate",
        lambda target, change: investigate.InvestigationResult(target, change),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "investigate.py",
            "--target",
            "target.py",
            "--change",
            "test invalid template",
        ],
    )

    exit_code = investigate.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert str(template_path) in captured.err
    assert "UTF-8" in captured.err


def test_find_related_adrs_returns_empty_without_adr_directory(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert investigate.find_related_adrs("target.py") == []


# Allowlist enforcement -----------------------------------------------------


@pytest.mark.parametrize(
    "verb",
    ["log", "grep", "show", "diff", "rev-parse", "rev-list", "ls-files", "cat-file"],
)
def test_run_git_accepts_read_only_verbs(verb: str, monkeypatch) -> None:
    """All eight read-only verbs in the allowlist MUST pass validation."""
    captured: dict[str, list[str]] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return type("R", (), {"stdout": "ok\n", "returncode": 0})()

    monkeypatch.setattr(investigate.subprocess, "run", fake_run)
    investigate.run_git([verb])
    assert captured["args"][0] == "git"
    assert captured["args"][1] == verb


@pytest.mark.parametrize(
    "verb",
    ["push", "fetch", "pull", "reset", "rebase", "merge", "clone", "rm", "config"],
)
def test_run_git_rejects_destructive_verbs(verb: str) -> None:
    """Destructive verbs MUST raise ValueError -- the allowlist is the gate."""
    with pytest.raises(ValueError, match="not in allowlist"):
        investigate.run_git([verb])


def test_run_git_rejects_empty_args() -> None:
    with pytest.raises(ValueError, match="not in allowlist"):
        investigate.run_git([])


# Transport-flag denylist ---------------------------------------------------


@pytest.mark.parametrize(
    "flag",
    [
        "--upload-pack=evil",
        "--exec=evil",
        "--upload-pack=/tmp/evil",
        "--exec=$(rm -rf /)",
    ],
)
def test_run_git_rejects_transport_flag_anywhere(flag: str) -> None:
    """`--upload-pack=` and `--exec=` are git's two argv-RCE vectors.

    They must be rejected even when nested mid-args (after the verb).
    """
    with pytest.raises(ValueError, match="forbidden git option"):
        investigate.run_git(["log", flag])


def test_run_git_accepts_safe_flags(monkeypatch) -> None:
    """Non-transport flags MUST pass through unchanged."""
    monkeypatch.setattr(
        investigate.subprocess,
        "run",
        lambda args, **kw: type("R", (), {"stdout": "", "returncode": 0})(),
    )
    investigate.run_git(["log", "--oneline", "-n", "5", "--", "README.md"])


# Allowlist boundary --------------------------------------------------------


def test_run_git_allowlist_is_frozen() -> None:
    """The allowlist constant MUST be immutable (frozenset, not list/set)."""
    assert isinstance(investigate._GIT_FLAG_ALLOWLIST, frozenset)
    # Defense: ensure no destructive verbs slipped in.
    forbidden = {"push", "fetch", "pull", "reset", "rebase", "merge", "clone", "rm"}
    assert forbidden.isdisjoint(investigate._GIT_FLAG_ALLOWLIST)
