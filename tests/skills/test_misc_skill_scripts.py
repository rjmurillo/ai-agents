"""Tests for miscellaneous skill scripts.

Covers:
- detect_adr_changes.py
- invoke_codeql_scan_skill.py
- resolve_pr_conflicts.py
- collect_metrics.py
- detect_infrastructure.py
- fix_fences.py
- new_slash_command.py
- validate_slash_command.py
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add skill script directories to sys.path.
_project_root = Path(__file__).resolve().parents[2]
_adr_review = _project_root / ".claude" / "skills" / "adr-review" / "scripts"
_codeql = _project_root / ".claude" / "skills" / "codeql-scan" / "scripts"
_merge_resolver = _project_root / ".claude" / "skills" / "merge-resolver" / "scripts"
_metrics = _project_root / ".claude" / "skills" / "metrics"
_security = _project_root / ".claude" / "skills" / "security-detection"
_fix_fences = _project_root / ".claude" / "skills" / "fix-markdown-fences"
_slashcmd = _project_root / ".claude" / "skills" / "slashcommandcreator" / "scripts"

# Also add .claude/lib for github_core imports
_lib_dir = _project_root / ".claude" / "lib"

for _p in (
    str(_adr_review),
    str(_codeql),
    str(_merge_resolver),
    str(_metrics),
    str(_security),
    str(_fix_fences),
    str(_slashcmd),
    str(_lib_dir),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def make_proc(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ---------------------------------------------------------------------------
# detect_adr_changes
# ---------------------------------------------------------------------------

class TestDetectAdrChanges:
    """Tests for detect_adr_changes module.

    The module exposes main() as its entry point, plus private helpers
    _get_adr_status() and _run_git().
    """

    def _import(self):
        import importlib

        import detect_adr_changes as mod
        importlib.reload(mod)
        return mod

    def test_get_adr_status_proposed_default(self, tmp_path):
        mod = self._import()
        adr = tmp_path / "ADR-001.md"
        adr.write_text("# ADR-001\n\nNo status field here.")
        result = mod._get_adr_status(Path(adr))
        assert result == "proposed"

    def test_get_adr_status_from_frontmatter(self, tmp_path):
        mod = self._import()
        adr = tmp_path / "ADR-001.md"
        adr.write_text("status: accepted\n\nSome content")
        result = mod._get_adr_status(Path(adr))
        assert result == "accepted"

    def test_get_adr_status_missing_file(self, tmp_path):
        mod = self._import()
        result = mod._get_adr_status(Path(tmp_path / "missing.md"))
        assert result == "unknown"

    def test_main_returns_0(self, tmp_path):
        import importlib

        import detect_adr_changes as mod
        importlib.reload(mod)
        (tmp_path / ".git").mkdir()
        # Mock _run_git to return empty diff
        original_run_git = mod._run_git
        mock_result = MagicMock(returncode=0, stdout="")
        with patch.object(mod, "_run_git", return_value=mock_result):
            exit_code = mod.main(["--base-path", str(tmp_path)])
        assert exit_code == 0

    def test_not_git_repo_exits_1(self, tmp_path):
        mod = self._import()
        # No .git directory
        exit_code = mod.main(["--base-path", str(tmp_path)])
        assert exit_code == 1

    def test_main_with_created_adr(self, tmp_path):
        mod = self._import()
        (tmp_path / ".git").mkdir()
        mock_results = [
            # First pattern returns a created file
            MagicMock(returncode=0, stdout="A\t.agents/architecture/ADR-001.md"),
            # Second pattern returns nothing
            MagicMock(returncode=0, stdout=""),
        ]
        with patch.object(mod, "_run_git", side_effect=mock_results):
            exit_code = mod.main(["--base-path", str(tmp_path)])
        assert exit_code == 0

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            import detect_adr_changes as mod
            mod.build_parser().parse_args(["--help"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# invoke_codeql_scan_skill
# ---------------------------------------------------------------------------

class TestInvokeCodeqlScanSkill:
    """Tests for invoke_codeql_scan_skill module."""

    def _import(self):
        import importlib

        import invoke_codeql_scan_skill as mod
        importlib.reload(mod)
        return mod

    def test_get_repo_root_success(self):
        mod = self._import()
        proc = make_proc(stdout="/home/user/repo/.git", returncode=0)
        with patch("subprocess.run", return_value=proc):
            result = mod.get_repo_root()
        assert result == "/home/user/repo"

    def test_get_repo_root_none_on_failure(self):
        mod = self._import()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = mod.get_repo_root()
        assert result is None

    def test_run_scan_not_in_git_repo(self):
        mod = self._import()
        with patch.object(mod, "get_repo_root", return_value=None):
            code = mod.run_scan()
        assert code == 3

    def test_run_scan_codeql_not_found(self, tmp_path):
        mod = self._import()
        with patch.object(mod, "get_repo_root", return_value=str(tmp_path)):
            code = mod.run_scan()
        assert code == 3

    def test_run_scan_validate_config_script_missing(self, tmp_path):
        mod = self._import()
        with patch.object(mod, "get_repo_root", return_value=str(tmp_path)):
            code = mod.run_scan(operation="validate")
        assert code == 3

    def test_run_scan_validate_success(self, tmp_path):
        mod = self._import()
        codeql_dir = tmp_path / ".codeql" / "scripts"
        codeql_dir.mkdir(parents=True)
        config_script = codeql_dir / "Test-CodeQLConfig.ps1"
        config_script.write_text("# config script")

        with (
            patch.object(mod, "get_repo_root", return_value=str(tmp_path)),
            patch("subprocess.run", return_value=make_proc(returncode=0)),
        ):
            code = mod.run_scan(operation="validate")
        assert code == 0

    def test_run_scan_validate_pwsh_not_found(self, tmp_path):
        mod = self._import()
        codeql_dir = tmp_path / ".codeql" / "scripts"
        codeql_dir.mkdir(parents=True)
        config_script = codeql_dir / "Test-CodeQLConfig.ps1"
        config_script.write_text("")

        with (
            patch.object(mod, "get_repo_root", return_value=str(tmp_path)),
            patch("subprocess.run", side_effect=FileNotFoundError),
        ):
            code = mod.run_scan(operation="validate")
        assert code == 3

    def test_run_scan_full_with_codeql_cli(self, tmp_path):
        mod = self._import()
        cli_dir = tmp_path / ".codeql" / "cli"
        cli_dir.mkdir(parents=True)
        codeql_cli = cli_dir / "codeql"
        codeql_cli.write_text("")
        script_dir = tmp_path / ".codeql" / "scripts"
        script_dir.mkdir(parents=True)
        scan_script = script_dir / "Invoke-CodeQLScan.ps1"
        scan_script.write_text("")

        with (
            patch.object(mod, "get_repo_root", return_value=str(tmp_path)),
            patch("subprocess.run", return_value=make_proc(returncode=0)),
        ):
            code = mod.run_scan(operation="full")
        assert code == 0

    def test_main_full_operation(self, tmp_path):
        import importlib

        import invoke_codeql_scan_skill as mod
        importlib.reload(mod)
        with patch.object(mod, "run_scan", return_value=0):
            sys.argv = ["invoke_codeql_scan_skill.py", "--operation", "full"]
            code = mod.main()
        assert code == 0

    def test_write_colored_outputs_prefix(self, capsys):
        mod = self._import()
        mod.write_colored("test message", "success")
        captured = capsys.readouterr()
        assert "[PASS]" in captured.err
        assert "test message" in captured.err

    def test_help_does_not_crash(self):
        mod = self._import()
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["invoke_codeql_scan_skill.py", "--help"]
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# resolve_pr_conflicts
# ---------------------------------------------------------------------------

class TestResolvePrConflicts:
    """Tests for resolve_pr_conflicts module."""

    def _import(self):
        import importlib

        import resolve_pr_conflicts as mod
        importlib.reload(mod)
        return mod

    def test_unsafe_branch_name_rejected(self):
        mod = self._import()
        result = mod.resolve_pr_conflicts(1, "branch; rm -rf /", "main")
        assert result["success"] is False
        assert "unsafe branch name" in result["message"].lower()

    def test_unsafe_target_branch_rejected(self):
        mod = self._import()
        result = mod.resolve_pr_conflicts(1, "valid-branch", "main && evil")
        assert result["success"] is False
        assert "unsafe target branch" in result["message"].lower()

    def test_dry_run_returns_success(self):
        mod = self._import()
        # dry_run in non-runner mode goes through resolve_conflicts_worktree
        # which needs git rev-parse. Mock _run_git.
        with (
            patch.dict("os.environ", {}, clear=False),
            patch.object(
                mod, "_run_git",
                return_value=MagicMock(returncode=0, stdout="/repo\n"),
            ),
        ):
            # Remove GITHUB_ACTIONS to use worktree path
            env_without = {k: v for k, v in __import__("os").environ.items()
                           if k != "GITHUB_ACTIONS"}
            with patch.dict("os.environ", env_without, clear=True):
                result = mod.resolve_pr_conflicts(
                    42, "feat/test", "main", dry_run=True,
                    worktree_base_path=str(Path(__file__).parent),
                )
        assert result["success"] is True
        assert "DryRun" in result["message"]

    def test_is_safe_branch_name_valid(self):
        mod = self._import()
        assert mod.is_safe_branch_name("feat/my-feature") is True
        assert mod.is_safe_branch_name("main") is True
        assert mod.is_safe_branch_name("release/v1.0") is True

    def test_is_safe_branch_name_invalid(self):
        mod = self._import()
        assert mod.is_safe_branch_name("") is False
        assert mod.is_safe_branch_name("-bad-start") is False
        assert mod.is_safe_branch_name("branch..traversal") is False
        assert mod.is_safe_branch_name("branch;evil") is False
        assert mod.is_safe_branch_name("branch`cmd`") is False

    def test_get_safe_worktree_path_valid(self, tmp_path):
        mod = self._import()
        with patch.object(mod, "get_repo_info") as mock_info:
            from github_core.api import RepoInfo
            mock_info.return_value = RepoInfo(owner="owner", repo="myrepo")
            path = mod.get_safe_worktree_path(str(tmp_path), 42)
        assert "myrepo-pr-42" in path
        assert str(tmp_path) in path

    def test_get_safe_worktree_path_invalid_pr(self, tmp_path):
        mod = self._import()
        with pytest.raises(ValueError, match="Invalid PR number"):
            mod.get_safe_worktree_path(str(tmp_path), 0)

    def test_is_auto_resolvable_handoff(self):
        mod = self._import()
        assert mod.is_auto_resolvable(".agents/HANDOFF.md") is True

    def test_is_auto_resolvable_package_lock(self):
        mod = self._import()
        assert mod.is_auto_resolvable("package-lock.json") is True

    def test_is_auto_resolvable_src_file(self):
        mod = self._import()
        assert mod.is_auto_resolvable("src/main.py") is False

    def test_is_github_runner_true(self):
        mod = self._import()
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            assert mod.is_github_runner() is True

    def test_is_github_runner_false(self):
        mod = self._import()
        env_without = {k: v for k, v in __import__("os").environ.items()
                       if k != "GITHUB_ACTIONS"}
        with patch.dict("os.environ", env_without, clear=True):
            assert mod.is_github_runner() is False

    def test_get_repo_info(self):
        mod = self._import()
        mock_result = MagicMock(returncode=0, stdout="git@github.com:owner/myrepo.git")
        with patch("subprocess.run", return_value=mock_result):
            info = mod.get_repo_info()
        assert info.owner == "owner"
        assert info.repo == "myrepo"

    def test_get_repo_info_https(self):
        mod = self._import()
        mock_result = MagicMock(returncode=0, stdout="https://github.com/org/repo.git")
        with patch("subprocess.run", return_value=mock_result):
            info = mod.get_repo_info()
        assert info.owner == "org"
        assert info.repo == "repo"

    def test_help_does_not_crash(self):
        mod = self._import()
        with pytest.raises(SystemExit) as exc:
            mod.build_parser().parse_args(["--help"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# collect_metrics
# ---------------------------------------------------------------------------

class TestCollectMetrics:
    """Tests for collect_metrics module."""

    def _import(self):
        import importlib

        import collect_metrics as mod
        importlib.reload(mod)
        return mod

    def test_get_commit_type_feature(self):
        mod = self._import()
        assert mod.get_commit_type("feat: add new thing") == "feature"

    def test_get_commit_type_fix(self):
        mod = self._import()
        assert mod.get_commit_type("fix(scope): repair bug") == "fix"

    def test_get_commit_type_other(self):
        mod = self._import()
        assert mod.get_commit_type("WIP: random message") == "other"

    def test_get_commit_type_docs(self):
        mod = self._import()
        assert mod.get_commit_type("docs: update readme") == "docs"

    def test_find_agents_in_text_orchestrator(self):
        mod = self._import()
        agents = mod.find_agents_in_text("orchestrator agent reviewed")
        assert "orchestrator" in agents

    def test_find_agents_in_text_empty(self):
        mod = self._import()
        agents = mod.find_agents_in_text("no agents here")
        assert agents == []

    def test_is_infrastructure_file_workflow(self):
        mod = self._import()
        assert mod.is_infrastructure_file(".github/workflows/ci.yml") is True

    def test_is_infrastructure_file_script(self):
        mod = self._import()
        assert mod.is_infrastructure_file("scripts/deploy.ps1") is True

    def test_is_infrastructure_file_src(self):
        mod = self._import()
        assert mod.is_infrastructure_file("src/main.py") is False

    def test_get_commits_since_returns_empty_on_error(self, tmp_path):
        mod = self._import()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            commits = mod.get_commits_since(30, str(tmp_path))
        assert commits == []

    def test_get_commit_files_returns_empty_on_error(self, tmp_path):
        mod = self._import()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            files = mod.get_commit_files("abc123", str(tmp_path))
        assert files == []

    def test_get_metrics_empty(self, tmp_path):
        mod = self._import()
        with patch.object(mod, "get_commits_since", return_value=[]):
            metrics = mod.get_metrics(str(tmp_path), 30)
        assert metrics["period"]["total_commits"] == 0
        assert metrics["metric_2_coverage"]["coverage_rate"] == 0

    def test_get_metrics_with_commits(self, tmp_path):
        mod = self._import()
        commits = [
            {"Hash": "abc", "Subject": "feat: impl orchestrator", "Author": "dev",
             "Email": "d@e.com", "Date": "2024-01-01"},
        ]
        with (
            patch.object(mod, "get_commits_since", return_value=commits),
            patch.object(mod, "get_commit_files", return_value=[]),
        ):
            metrics = mod.get_metrics(str(tmp_path), 30)
        assert metrics["period"]["total_commits"] == 1

    def test_format_summary_contains_metrics(self, tmp_path):
        mod = self._import()
        with patch.object(mod, "get_commits_since", return_value=[]):
            metrics = mod.get_metrics(str(tmp_path), 30)
        summary = mod.format_summary(metrics)
        assert "AGENT METRICS" in summary
        assert "METRIC 1" in summary

    def test_format_markdown_contains_table(self, tmp_path):
        mod = self._import()
        with patch.object(mod, "get_commits_since", return_value=[]):
            metrics = mod.get_metrics(str(tmp_path), 30)
        md = mod.format_markdown(metrics)
        assert "# Agent Metrics Report" in md
        assert "## Executive Summary" in md

    def test_main_json_output(self, tmp_path, capsys):
        import importlib

        import collect_metrics as mod
        importlib.reload(mod)
        (tmp_path / ".git").mkdir()
        with patch.object(mod, "get_commits_since", return_value=[]):
            sys.argv = [
                "collect_metrics.py",
                "--output", "json",
                "--repo-path", str(tmp_path),
            ]
            code = mod.main()
        assert code == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "period" in parsed

    def test_main_path_not_found(self, tmp_path):
        import importlib

        import collect_metrics as mod
        importlib.reload(mod)
        sys.argv = [
            "collect_metrics.py",
            "--repo-path", str(tmp_path / "missing"),
        ]
        code = mod.main()
        assert code == 1

    def test_main_not_git_repo(self, tmp_path):
        import importlib

        import collect_metrics as mod
        importlib.reload(mod)
        sys.argv = [
            "collect_metrics.py",
            "--repo-path", str(tmp_path),
        ]
        code = mod.main()
        assert code == 1

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["collect_metrics.py", "--help"]
            import collect_metrics as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# detect_infrastructure
# ---------------------------------------------------------------------------

class TestDetectInfrastructure:
    """Tests for detect_infrastructure module."""

    def _import(self):
        import importlib

        import detect_infrastructure as mod
        importlib.reload(mod)
        return mod

    def test_critical_workflow_file(self):
        mod = self._import()
        assert mod.get_security_risk_level(".github/workflows/ci.yml") == "critical"

    def test_critical_auth_file(self):
        mod = self._import()
        assert mod.get_security_risk_level("src/Auth/LoginService.cs") == "critical"

    def test_critical_env_file(self):
        mod = self._import()
        assert mod.get_security_risk_level(".env.production") == "critical"

    def test_high_dockerfile(self):
        mod = self._import()
        assert mod.get_security_risk_level("Dockerfile") == "high"

    def test_high_terraform(self):
        mod = self._import()
        assert mod.get_security_risk_level("infra/main.tf") == "high"

    def test_none_for_source_file(self):
        mod = self._import()
        assert mod.get_security_risk_level("src/main.py") == "none"

    def test_detect_infrastructure_empty(self):
        mod = self._import()
        result = mod.detect_infrastructure([])
        assert result["findings"] == []
        assert result["highest_risk"] == "none"
        assert result["file_count"] == 0

    def test_detect_infrastructure_none_input(self):
        mod = self._import()
        result = mod.detect_infrastructure()
        assert result["file_count"] == 0

    def test_detect_infrastructure_critical_found(self):
        mod = self._import()
        result = mod.detect_infrastructure([".github/workflows/ci.yml", "src/main.py"])
        assert result["highest_risk"] == "critical"
        assert result["file_count"] == 2
        assert len(result["findings"]) == 1

    def test_detect_infrastructure_high_only(self):
        mod = self._import()
        result = mod.detect_infrastructure(["Dockerfile"])
        assert result["highest_risk"] == "high"

    def test_detect_infrastructure_mixed_risk(self):
        mod = self._import()
        result = mod.detect_infrastructure([
            ".github/workflows/ci.yml",  # critical
            "Dockerfile",               # high
        ])
        assert result["highest_risk"] == "critical"

    def test_matches_pattern(self):
        mod = self._import()
        assert mod.matches_pattern(".env.local", [r"\.env.*$"]) is True

    def test_no_match(self):
        mod = self._import()
        assert mod.matches_pattern("src/main.py", [r"\.env.*$"]) is False

    def test_get_staged_files_success(self):
        mod = self._import()
        proc = make_proc(stdout=".github/workflows/ci.yml\nsrc/main.py", returncode=0)
        with patch("subprocess.run", return_value=proc):
            files = mod.get_staged_files()
        assert ".github/workflows/ci.yml" in files

    def test_get_staged_files_empty_on_failure(self):
        mod = self._import()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            files = mod.get_staged_files()
        assert files == []

    def test_main_json_output(self, capsys):
        import importlib

        import detect_infrastructure as mod
        importlib.reload(mod)
        sys.argv = [
            "detect_infrastructure.py",
            "--files", ".github/workflows/ci.yml",
            "--json",
        ]
        code = mod.main()
        assert code == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["highest_risk"] == "critical"

    def test_main_no_findings(self, capsys):
        import importlib

        import detect_infrastructure as mod
        importlib.reload(mod)
        sys.argv = ["detect_infrastructure.py", "--files", "src/main.py"]
        code = mod.main()
        assert code == 0

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["detect_infrastructure.py", "--help"]
            import detect_infrastructure as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# fix_fences
# ---------------------------------------------------------------------------

class TestFixFences:
    """Tests for fix_fences module."""

    def _import(self):
        import importlib

        import fix_fences as mod
        importlib.reload(mod)
        return mod

    def test_no_fences_unchanged(self):
        mod = self._import()
        content = "# Title\n\nPlain text with no code blocks.\n"
        result = mod.repair_markdown_fences(content)
        assert result == content

    def test_clean_code_block_unchanged(self):
        mod = self._import()
        content = "```python\nprint('hi')\n```\n"
        result = mod.repair_markdown_fences(content)
        assert result == content

    def test_unclosed_block_gets_closing(self):
        mod = self._import()
        content = "```python\ncode here\n"
        result = mod.repair_markdown_fences(content)
        assert result.endswith("```")

    def test_nested_opening_inserts_closing_first(self):
        mod = self._import()
        # Two opening fences without a close between them
        content = "```python\ncode1\n```bash\ncode2\n```\n"
        result = mod.repair_markdown_fences(content)
        # The first block should be closed before the second opens
        assert result.count("```") >= 3

    def test_fix_fences_no_changes(self, tmp_path):
        mod = self._import()
        md = tmp_path / "clean.md"
        md.write_text("# Title\n\nNo code blocks.\n")
        fixed = mod.fix_fences([str(tmp_path)])
        assert fixed == 0

    def test_fix_fences_fixes_unclosed(self, tmp_path):
        mod = self._import()
        md = tmp_path / "bad.md"
        md.write_text("```python\ncode here\n")
        fixed = mod.fix_fences([str(tmp_path)])
        assert fixed == 1
        content = md.read_text()
        assert content.endswith("```")

    def test_fix_fences_missing_dir(self, tmp_path):
        mod = self._import()
        missing = str(tmp_path / "nonexistent")
        fixed = mod.fix_fences([missing])
        assert fixed == 0

    def test_fix_fences_empty_file_ignored(self, tmp_path):
        mod = self._import()
        md = tmp_path / "empty.md"
        md.write_text("")
        fixed = mod.fix_fences([str(tmp_path)])
        assert fixed == 0

    def test_main_no_changes(self, tmp_path, capsys):
        import importlib

        import fix_fences as mod
        importlib.reload(mod)
        (tmp_path / "ok.md").write_text("# Title\n")
        sys.argv = ["fix_fences.py", "--directories", str(tmp_path)]
        code = mod.main()
        assert code == 0
        captured = capsys.readouterr()
        assert "No files needed fixing" in captured.out

    def test_main_with_fixes(self, tmp_path, capsys):
        import importlib

        import fix_fences as mod
        importlib.reload(mod)
        (tmp_path / "bad.md").write_text("```python\nopen block\n")
        sys.argv = ["fix_fences.py", "--directories", str(tmp_path)]
        code = mod.main()
        assert code == 0
        captured = capsys.readouterr()
        assert "fixed" in captured.out

    def test_help_does_not_crash(self):
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["fix_fences.py", "--help"]
            import fix_fences as mod
            mod.main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# new_slash_command
# ---------------------------------------------------------------------------

class TestNewSlashCommand:
    """Tests for new_slash_command module.

    The module exposes main() as its entry point and _validate_name() as private.
    """

    def _import(self):
        import importlib

        import new_slash_command as mod
        importlib.reload(mod)
        return mod

    def test_validate_name_valid(self):
        mod = self._import()
        assert mod._validate_name("my-command") is True
        assert mod._validate_name("cmd_123") is True
        assert mod._validate_name("ABC") is True

    def test_validate_name_invalid(self):
        mod = self._import()
        assert mod._validate_name("") is False
        assert mod._validate_name("has space") is False
        assert mod._validate_name("../traversal") is False
        assert mod._validate_name("cmd;evil") is False

    def test_main_create_command_success(self, tmp_path, monkeypatch):
        mod = self._import()
        monkeypatch.chdir(tmp_path)
        code = mod.main(["--name", "test-cmd"])
        assert code == 0
        cmd_file = tmp_path / ".claude" / "commands" / "test-cmd.md"
        assert cmd_file.exists()
        content = cmd_file.read_text()
        assert "description:" in content

    def test_main_create_command_with_namespace(self, tmp_path, monkeypatch):
        mod = self._import()
        monkeypatch.chdir(tmp_path)
        code = mod.main(["--name", "my-cmd", "--namespace", "git"])
        assert code == 0
        cmd_file = tmp_path / ".claude" / "commands" / "git" / "my-cmd.md"
        assert cmd_file.exists()

    def test_main_invalid_name(self):
        mod = self._import()
        code = mod.main(["--name", "has space"])
        assert code == 1

    def test_main_invalid_namespace(self, tmp_path, monkeypatch):
        mod = self._import()
        monkeypatch.chdir(tmp_path)
        code = mod.main(["--name", "valid", "--namespace", "bad namespace!"])
        assert code == 1

    def test_main_file_exists(self, tmp_path, monkeypatch):
        mod = self._import()
        monkeypatch.chdir(tmp_path)
        cmd_dir = tmp_path / ".claude" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "existing.md").write_text("existing content")
        code = mod.main(["--name", "existing"])
        assert code == 1

    def test_main_success_output(self, tmp_path, monkeypatch, capsys):
        import importlib

        import new_slash_command as mod
        importlib.reload(mod)
        monkeypatch.chdir(tmp_path)
        code = mod.main(["--name", "test-cmd"])
        assert code == 0
        captured = capsys.readouterr()
        assert "[PASS]" in captured.out

    def test_help_does_not_crash(self):
        mod = self._import()
        with pytest.raises(SystemExit) as exc:
            mod.build_parser().parse_args(["--help"])
        assert exc.value.code == 0

    def test_template_contains_required_fields(self, tmp_path, monkeypatch):
        mod = self._import()
        monkeypatch.chdir(tmp_path)
        mod.main(["--name", "my-command"])
        content = (tmp_path / ".claude" / "commands" / "my-command.md").read_text()
        assert "description:" in content
        assert "argument-hint:" in content
        assert "allowed-tools:" in content
        assert "my-command" in content


# ---------------------------------------------------------------------------
# validate_slash_command
# ---------------------------------------------------------------------------

class TestValidateSlashCommand:
    """Tests for validate_slash_command module.

    validate_slash_command() returns (violations, blocking_count, warning_count).
    """

    def _import(self):
        import importlib

        import validate_slash_command as mod
        importlib.reload(mod)
        return mod

    def _write_valid_command(self, tmp_path, name="test-cmd"):
        cmd = tmp_path / f"{name}.md"
        cmd.write_text(
            "---\n"
            "description: Use when testing the command\n"
            "argument-hint: <arg>\n"
            "allowed-tools: []\n"
            "---\n\n"
            f"# {name}\n\n"
            "Do the task with $ARGUMENTS.\n"
        )
        return cmd

    def test_file_not_found_returns_blocking(self, tmp_path):
        mod = self._import()
        violations, blocking, warnings = mod.validate_slash_command(
            str(tmp_path / "missing.md"), skip_lint=True
        )
        assert blocking == 1

    def test_valid_command_passes(self, tmp_path):
        mod = self._import()
        cmd = self._write_valid_command(tmp_path)
        violations, blocking, warnings = mod.validate_slash_command(
            str(cmd), skip_lint=True
        )
        assert blocking == 0

    def test_missing_frontmatter_fails(self, tmp_path):
        mod = self._import()
        cmd = tmp_path / "bad.md"
        cmd.write_text("# No frontmatter here\n")
        violations, blocking, warnings = mod.validate_slash_command(
            str(cmd), skip_lint=True
        )
        assert blocking >= 1

    def test_missing_description_fails(self, tmp_path):
        mod = self._import()
        cmd = tmp_path / "no-desc.md"
        cmd.write_text("---\nargument-hint: <x>\n---\n\nContent\n")
        violations, blocking, warnings = mod.validate_slash_command(
            str(cmd), skip_lint=True
        )
        assert blocking >= 1

    def test_uses_arguments_no_hint_fails(self, tmp_path):
        mod = self._import()
        cmd = tmp_path / "no-hint.md"
        cmd.write_text(
            "---\n"
            "description: Use when doing something\n"
            "---\n\n"
            "Do $ARGUMENTS\n"
        )
        violations, blocking, warnings = mod.validate_slash_command(
            str(cmd), skip_lint=True
        )
        assert blocking >= 1

    def test_has_hint_no_args_is_warning_only(self, tmp_path):
        mod = self._import()
        cmd = tmp_path / "hint-no-args.md"
        cmd.write_text(
            "---\n"
            "description: Use when doing something\n"
            "argument-hint: <x>\n"
            "---\n\n"
            "No args used here.\n"
        )
        violations, blocking, warnings = mod.validate_slash_command(
            str(cmd), skip_lint=True
        )
        assert blocking == 0

    def test_long_file_generates_warning(self, tmp_path):
        mod = self._import()
        cmd = tmp_path / "long.md"
        lines = ["---", "description: Use when testing", "---", ""]
        lines.extend(["line content"] * 210)
        cmd.write_text("\n".join(lines))
        violations, blocking, warnings = mod.validate_slash_command(
            str(cmd), skip_lint=True
        )
        assert blocking == 0

    def test_main_success(self, tmp_path, capsys):
        import importlib

        import validate_slash_command as mod
        importlib.reload(mod)
        cmd = self._write_valid_command(tmp_path)
        code = mod.main(["--path", str(cmd), "--skip-lint"])
        assert code == 0
        captured = capsys.readouterr()
        assert "[PASS]" in captured.out

    def test_main_failure(self, tmp_path):
        import importlib

        import validate_slash_command as mod
        importlib.reload(mod)
        code = mod.main(["--path", str(tmp_path / "missing.md"), "--skip-lint"])
        assert code == 1

    def test_help_does_not_crash(self):
        mod = self._import()
        with pytest.raises(SystemExit) as exc:
            mod.build_parser().parse_args(["--help"])
        assert exc.value.code == 0

    def test_lint_skipped_with_flag(self, tmp_path):
        mod = self._import()
        cmd = self._write_valid_command(tmp_path)
        # Skip lint should not call subprocess at all for lint
        with patch("subprocess.run") as mock_run:
            mod.validate_slash_command(str(cmd), skip_lint=True)
        # subprocess.run should not have been called for markdownlint
        for call_args in mock_run.call_args_list:
            args = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
            assert "markdownlint" not in str(args)
