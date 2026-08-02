#!/usr/bin/env python3
"""Tests for detect_infrastructure module."""

from __future__ import annotations

import io
import json
import runpy
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/security-detection/detect_infrastructure.py")
matches_pattern = mod.matches_pattern
get_security_risk_level = mod.get_security_risk_level
detect_infrastructure = mod.detect_infrastructure
get_files_from_stdin = mod.get_files_from_stdin
get_staged_files = mod.get_staged_files
CRITICAL_PATTERNS = mod.CRITICAL_PATTERNS
HIGH_PATTERNS = mod.HIGH_PATTERNS
main = mod.main
SKILL_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "security-detection"
)
SKILL_PATH = SKILL_DIR / "SKILL.md"
SCRIPT_PATH = SKILL_DIR / "detect_infrastructure.py"


def test_skill_usage_matches_cli_contract() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "--git-staged" not in text
    assert "detect_infrastructure.py --use-git-staged" in text
    assert (
        "detect_infrastructure.py --files .github/workflows/ci.yml "
        "src/auth/login.cs"
        in text
    )
    ci_section = text.split("### CI Integration", maxsplit=1)[1]
    assert "--use-git-staged" not in ci_section
    assert "fetch-depth: 0" in ci_section
    assert (
        'git diff --no-renames --name-only -z "$BASE_SHA" "$HEAD_SHA"'
        in ci_section
    )
    normalized_ci = " ".join(ci_section.split())
    assert (
        "| python .claude/skills/security-detection/detect_infrastructure.py "
        "--files-from-stdin"
        in normalized_ci
    )


def test_documented_ci_diff_exposes_renamed_sensitive_source(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test User"],
        check=True,
    )
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-qm", "test: add workflow"],
        check=True,
    )
    base = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True, encoding="utf-8",
    ).stdout.strip()
    destination = tmp_path / "docs" / "ci.yml"
    destination.parent.mkdir()
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "mv",
            ".github/workflows/ci.yml",
            "docs/ci.yml",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-qm", "test: move workflow"],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True, encoding="utf-8",
    ).stdout.strip()

    changed = subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "diff",
            "--no-renames",
            "--name-only",
            "-z",
            base,
            head,
        ],
        check=True,
        capture_output=True,
    ).stdout
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--files-from-stdin", "--json"],
        input=changed,
        check=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)

    assert payload["highest_risk"] == "critical"
    assert payload["file_count"] == 2


def test_null_delimited_stdin_treats_option_shaped_filename_as_data() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--files-from-stdin", "--json"],
        input=b"--use-git-staged\0.env.production\0",
        check=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["file_count"] == 2
    assert payload["highest_risk"] == "critical"
    assert payload["findings"] == [
        {"File": ".env.production", "RiskLevel": "critical"},
    ]


def test_null_delimited_stdin_reader_preserves_option_shaped_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("--use-git-staged\0.env\0"))

    assert get_files_from_stdin() == ["--use-git-staged", ".env"]


def test_get_staged_files_returns_git_paths() -> None:
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "one.py\ntwo.yml\n", ""),
    ):
        assert get_staged_files() == ["one.py", "two.yml"]


def test_get_staged_files_returns_empty_on_git_failure() -> None:
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 1, "", "failed"),
    ):
        assert get_staged_files() == []


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError(),
        subprocess.TimeoutExpired(["git"], 30),
    ],
)
def test_get_staged_files_returns_empty_when_git_cannot_run(
    error: BaseException,
) -> None:
    with patch("subprocess.run", side_effect=error):
        assert get_staged_files() == []


def test_detect_infrastructure_can_source_staged_files() -> None:
    with patch.object(mod, "get_staged_files", return_value=["Dockerfile"]):
        result = detect_infrastructure(use_git_staged=True)

    assert result["highest_risk"] == "high"
    assert result["file_count"] == 1


def test_main_reads_null_delimited_stdin(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["detect_infrastructure.py", "--files-from-stdin", "--json"],
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("--use-git-staged\0.env\0"))

    assert main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["file_count"] == 2
    assert payload["highest_risk"] == "critical"


def test_main_reports_high_risk_findings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["detect_infrastructure.py", "--files", "Dockerfile"],
    )

    assert main() == 0

    assert "HIGH: Security agent review RECOMMENDED" in capsys.readouterr().out


def test_script_entry_point_exits_with_main_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT_PATH), "--files", "README.md"],
    )

    with pytest.raises(SystemExit, match="0"):
        runpy.run_path(str(SCRIPT_PATH), run_name="__main__")

    assert "No infrastructure/security files detected." in capsys.readouterr().out


class TestMatchesPattern:
    """Tests for matches_pattern function."""

    def test_matches_workflow_file(self) -> None:
        assert matches_pattern(".github/workflows/ci.yml", CRITICAL_PATTERNS) is True

    def test_matches_auth_directory(self) -> None:
        assert matches_pattern("src/Auth/login.cs", CRITICAL_PATTERNS) is True

    def test_no_match_for_regular_file(self) -> None:
        assert matches_pattern("src/utils/helper.py", CRITICAL_PATTERNS) is False
        assert matches_pattern("src/utils/helper.py", HIGH_PATTERNS) is False

    def test_matches_env_file(self) -> None:
        assert matches_pattern(".env.production", CRITICAL_PATTERNS) is True

    def test_matches_dockerfile(self) -> None:
        assert matches_pattern("Dockerfile", HIGH_PATTERNS) is True

    def test_matches_terraform(self) -> None:
        assert matches_pattern("infra/main.tf", HIGH_PATTERNS) is True


class TestGetSecurityRiskLevel:
    """Tests for get_security_risk_level function."""

    def test_critical_for_workflow(self) -> None:
        assert get_security_risk_level(".github/workflows/deploy.yml") == "critical"

    def test_critical_for_auth(self) -> None:
        assert get_security_risk_level("src/Auth/TokenService.cs") == "critical"

    def test_high_for_dockerfile(self) -> None:
        assert get_security_risk_level("Dockerfile") == "high"

    def test_high_for_build_script(self) -> None:
        assert get_security_risk_level("build/deploy.sh") == "high"

    def test_none_for_regular_file(self) -> None:
        assert get_security_risk_level("src/models/user.py") == "none"

    def test_normalizes_backslashes(self) -> None:
        assert get_security_risk_level("src\\Auth\\login.cs") == "critical"

    def test_critical_for_secret_file(self) -> None:
        assert get_security_risk_level("config/secret.json") == "critical"

    def test_critical_for_pem_file(self) -> None:
        assert get_security_risk_level("certs/server.pem") == "critical"

    def test_high_for_config_json(self) -> None:
        assert get_security_risk_level("config/database.json") == "high"

    def test_critical_only_for_git_hook_policy_path(self) -> None:
        assert get_security_risk_level("scripts/validation/git_hook_policy.py") == "critical"
        assert get_security_risk_level("scripts/validation/pre_pr.py") == "none"
        assert get_security_risk_level(".githooks/pre-commit") == "none"

    @pytest.mark.parametrize(
        "config_path",
        [
            f"{base}{suffix}{extension}"
            for base in ("lefthook", ".lefthook", ".config/lefthook")
            for suffix in ("", "-local")
            for extension in (".yml", ".yaml", ".json", ".jsonc", ".toml")
        ],
    )
    def test_auto_discovered_lefthook_configs_are_critical(
        self, config_path: str
    ) -> None:
        assert get_security_risk_level(config_path) == "critical"

    @pytest.mark.parametrize(
        "config_path",
        [
            "config/lefthook.yml",
            "nested/lefthook.yml",
            "nested/.config/lefthook-local.jsonc",
        ],
    )
    def test_non_discovered_lefthook_lookalikes_are_not_critical(
        self, config_path: str
    ) -> None:
        assert get_security_risk_level(config_path) != "critical"


class TestDetectInfrastructure:
    """Tests for detect_infrastructure function."""

    def test_empty_files_returns_no_findings(self) -> None:
        result = detect_infrastructure(changed_files=[])
        assert result["findings"] == []
        assert result["highest_risk"] == "none"

    def test_none_files_returns_no_findings(self) -> None:
        result = detect_infrastructure(changed_files=None)
        assert result["findings"] == []

    def test_detects_critical_files(self) -> None:
        result = detect_infrastructure(changed_files=[".github/workflows/ci.yml"])
        assert len(result["findings"]) == 1
        assert result["highest_risk"] == "critical"
        assert result["findings"][0]["RiskLevel"] == "critical"

    def test_detects_high_files(self) -> None:
        result = detect_infrastructure(changed_files=["Dockerfile"])
        assert len(result["findings"]) == 1
        assert result["highest_risk"] == "high"

    def test_highest_risk_is_critical_when_mixed(self) -> None:
        result = detect_infrastructure(
            changed_files=[".github/workflows/ci.yml", "Dockerfile", "src/app.py"]
        )
        assert result["highest_risk"] == "critical"
        assert len(result["findings"]) == 2

    def test_no_findings_for_safe_files(self) -> None:
        result = detect_infrastructure(changed_files=["src/app.py", "docs/readme.md"])
        assert result["findings"] == []
        assert result["highest_risk"] == "none"

    def test_file_count_reflects_input(self) -> None:
        result = detect_infrastructure(changed_files=["a.py", "b.py", "c.py"])
        assert result["file_count"] == 3


class TestMain:
    """Tests for main entry point."""

    def test_returns_zero_with_no_files(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["detect_infrastructure.py"]):
            result = main()
        assert result == 0

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        argv = [
            "detect_infrastructure.py", "--files",
            ".github/workflows/ci.yml", "--json",
        ]
        with patch("sys.argv", argv):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert '"critical"' in captured.out

    def test_human_output_for_findings(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["detect_infrastructure.py", "--files", ".github/workflows/ci.yml"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "CRITICAL" in captured.out
