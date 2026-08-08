"""Tests for invoke_markdownlint_guard.

Covers acceptance criteria from issue #1884 TASK-015-2: clean files pass,
violations block with structured output, missing binary fails closed,
TimeoutExpired and OSError fail closed, empty changeset short-circuits in
the framework, and the hooks.json registration includes the guard.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

import invoke_markdownlint_guard as guard


def _stdin(command: str) -> str:
    return json.dumps({"tool_input": {"command": command}})


def _ok(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["x"], returncode=0, stdout=stdout, stderr=stderr
    )


def _fail(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["x"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def push_command(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(_stdin("git push")))


def _make_dispatcher(diff_out, lint_handler):
    """Single subprocess.run side_effect that routes git diff vs markdownlint.

    Both push_guard_base and invoke_markdownlint_guard call subprocess.run on
    the same module global. Patching with one dispatcher avoids the two-patch
    collision while still letting tests express git-diff and lint behavior
    separately.
    """
    def dispatch(args, **_kw):
        if args and args[0] == "git":
            return _ok(diff_out)
        return lint_handler(args)
    return dispatch


def _run(
    diff_out,
    lint_handler,
    tmp_path,
    which_value="/usr/bin/markdownlint-cli2",
):
    for relative_path in diff_out.splitlines():
        if not relative_path:
            continue
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Test\n", encoding="utf-8")
    dispatcher = _make_dispatcher(diff_out, lint_handler)
    with patch("push_guard_base.subprocess.run", side_effect=dispatcher), \
         patch("push_guard_base._validate_strict_push_configuration"), \
         patch("push_guard_base.get_project_directory", return_value=str(tmp_path)), \
         patch.object(guard.shutil, "which", return_value=which_value), \
         patch("invoke_markdownlint_guard.get_project_directory", return_value=str(tmp_path)):
        return guard.main()


class TestCleanFiles:
    def test_clean_returns_zero(self, push_command, tmp_path, capsys):
        def lint(args):
            if "--version" in args:
                return _ok(stdout="0.21.0\n")
            return _ok()

        rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 0
        assert "BLOCKED" not in capsys.readouterr().out

    def test_invokes_with_no_globs_flag(self, push_command, tmp_path):
        """--no-globs is required so markdownlint lints only the changed
        files, not the repo's default **/*.md set. Pre-mortem mitigation:
        unrelated pre-existing violations would otherwise block valid pushes.
        """
        captured_args: list[list[str]] = []

        def lint(args):
            captured_args.append(list(args))
            if "--version" in args:
                return _ok(stdout="0.21.0\n")
            return _ok()

        _run("docs/a.md\n", lint, tmp_path)

        # Find the lint invocation (not --version) and assert --no-globs
        lint_calls = [a for a in captured_args if "--version" not in a]
        assert lint_calls, "Expected at least one markdownlint-cli2 invocation"
        for call_args in lint_calls:
            assert "--no-globs" in call_args, (
                f"--no-globs missing from invocation: {call_args}"
            )
            config_index = call_args.index("--config")
            assert call_args[config_index + 1] == str(guard.CONFIG_PATH)
            assert call_args[-1] == "-"
            assert "docs/a.md" not in call_args

    def test_lints_content_outside_consumer_config_scope(
        self, push_command, tmp_path
    ):
        markdown = tmp_path / "docs" / "a.md"
        markdown.parent.mkdir()
        markdown.write_text("# Trusted input\n", encoding="utf-8")
        lint_call: dict[str, object] = {}

        def dispatch(args, **kwargs):
            if args and args[0] == "git":
                return _ok("docs/a.md\n")
            if "--version" in args:
                return _ok(stdout="0.21.0\n")
            lint_call["args"] = args
            lint_call["input"] = kwargs.get("input")
            lint_call["cwd"] = kwargs.get("cwd")
            return _ok()

        with patch("push_guard_base.subprocess.run", side_effect=dispatch), \
             patch("push_guard_base._validate_strict_push_configuration"), \
             patch("push_guard_base.get_project_directory", return_value=str(tmp_path)), \
             patch.object(guard.shutil, "which", return_value="/usr/bin/markdownlint-cli2"), \
             patch("invoke_markdownlint_guard.get_project_directory", return_value=str(tmp_path)):
            rc = guard.main()

        assert rc == 0
        assert lint_call["input"] == "# Trusted input\n"
        assert lint_call["cwd"] == guard.CONFIG_PATH.parent
        assert lint_call["args"][-1] == "-"


class TestViolations:
    def test_violation_blocks_with_structured_output(self, push_command, tmp_path, capsys):
        violation_text = (
            "docs/a.md:5 MD040/fenced-code-language Fenced code blocks "
            "should have a language specified\n"
            "docs/a.md:12 MD013/line-length Line length\n"
        )

        def lint(args):
            if "--version" in args:
                return _ok(stdout="0.21.0")
            return _fail(1, stdout=violation_text)

        rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 2
        out = capsys.readouterr()
        assert "## BLOCKED [E_MARKDOWN_LINT]" in out.out
        assert "MD040/fenced-code-language" in out.out
        assert "MD013/line-length" in out.out
        assert "Fix and re-push." in out.out

    def test_nonzero_without_diagnostics_blocks(
        self, push_command, tmp_path, capsys
    ):
        def lint(args):
            if "--version" in args:
                return _ok(stdout="0.21.0")
            return _fail(2)

        rc = _run("docs/a.md\n", lint, tmp_path)

        assert rc == 2
        assert "exited 2 without diagnostics" in capsys.readouterr().out


class TestBinaryAbsent:
    def test_binary_missing_blocks(self, push_command, tmp_path, capsys):
        def lint(args):
            raise AssertionError("subprocess should not run when tool is absent")

        rc = _run("docs/a.md\n", lint, tmp_path, which_value=None)
        assert rc == 2
        err = capsys.readouterr().err
        assert "trusted markdownlint-cli2 not found outside the repository" in err
        assert "blocking push" in err

    def test_repository_local_binary_blocks(
        self, push_command, tmp_path, capsys
    ):
        local_binary = tmp_path / "node_modules" / ".bin" / guard.BINARY

        def lint(args):
            raise AssertionError("repository-controlled binary must not run")

        rc = _run(
            "docs/a.md\n",
            lint,
            tmp_path,
            which_value=str(local_binary),
        )

        assert rc == 2
        assert "trusted markdownlint-cli2 not found" in capsys.readouterr().err

    def test_repository_local_symlink_blocks(
        self, push_command, tmp_path, capsys
    ):
        local_binary = tmp_path / "node_modules" / ".bin" / guard.BINARY
        local_binary.parent.mkdir(parents=True)
        local_binary.symlink_to("/bin/true")

        def lint(args):
            raise AssertionError("repository-controlled symlink must not run")

        rc = _run(
            "docs/a.md\n",
            lint,
            tmp_path,
            which_value=str(local_binary),
        )

        assert rc == 2
        assert "trusted markdownlint-cli2 not found" in capsys.readouterr().err

    def test_missing_plugin_config_blocks(
        self, push_command, tmp_path, capsys
    ):
        missing_config = tmp_path / "missing-markdownlint.yaml"

        def lint(args):
            raise AssertionError("markdownlint must not run without fixed config")

        dispatcher = _make_dispatcher("docs/a.md\n", lint)
        with patch("push_guard_base.subprocess.run", side_effect=dispatcher), \
             patch("push_guard_base._validate_strict_push_configuration"), \
             patch("push_guard_base.get_project_directory", return_value=str(tmp_path)), \
             patch.object(guard.shutil, "which", return_value="/usr/bin/markdownlint-cli2"), \
             patch.object(guard, "CONFIG_PATH", missing_config), \
             patch("invoke_markdownlint_guard.get_project_directory", return_value=str(tmp_path)):
            rc = guard.main()

        assert rc == 2
        assert "plugin markdownlint config missing" in capsys.readouterr().err


class TestStrictHookInput:
    def test_empty_stdin_blocks_before_subprocess(
        self,
        monkeypatch,
        capsys,
    ):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("push_guard_base.subprocess.run") as run:
            with patch("push_guard_base._validate_strict_push_configuration"):
                rc = guard.main()

        assert rc == 2
        assert "stdin empty" in capsys.readouterr().out
        run.assert_not_called()


class TestTimeout:
    def test_timeout_blocks(self, push_command, tmp_path, capsys):
        def lint(args):
            if "--version" in args:
                return _ok(stdout="0.21.0")
            raise subprocess.TimeoutExpired(cmd=args, timeout=60)

        rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 2
        err = capsys.readouterr().err
        assert "TIMEOUT" in err
        assert "blocking push" in err


class TestOSError:
    def test_oserror_blocks(self, push_command, tmp_path, capsys):
        def lint(args):
            if "--version" in args:
                return _ok(stdout="0.21.0")
            raise OSError("Exec format error")

        rc = _run("docs/a.md\n", lint, tmp_path)
        assert rc == 2
        err = capsys.readouterr().err
        assert "OSError" in err
        assert "blocking push" in err


class TestGuardWiring:
    def test_consumer_repo_still_runs_customer_guard(
        self, push_command, tmp_path
    ):
        def lint(args):
            if "--version" in args:
                return _ok(stdout="0.21.0")
            return _fail(1, stdout="docs/a.md:1 MD018 missing space\n")

        with patch("push_guard_base.skip_if_consumer_repo", return_value=True):
            rc = _run("docs/a.md\n", lint, tmp_path)

        assert rc == 2

    def test_git_diff_failure_blocks_before_lint(
        self, push_command, tmp_path, capsys
    ):
        def dispatch(args, **_kwargs):
            if args and args[0] in {"git", "gh"}:
                return _fail(128, stderr="fatal: unavailable")
            raise AssertionError("markdownlint must not run without a changeset")

        with patch(
            "push_guard_base.subprocess.run", side_effect=dispatch
        ), patch(
            "push_guard_base._validate_strict_push_configuration"
        ), patch(
            "push_guard_base.get_project_directory", return_value=str(tmp_path)
        ), patch(
            "push_guard_base._gh_base_ref", return_value=None
        ):
            rc = guard.main()

        assert rc == 2
        assert "could not determine changed files" in capsys.readouterr().out


class TestEmptyChangeset:
    def test_no_md_files_skips_validator(self, push_command, tmp_path):
        invoked = {"lint": False}

        def lint(args):
            invoked["lint"] = True
            return _ok()

        rc = _run("src/foo.py\nsrc/bar.py\n", lint, tmp_path)
        assert rc == 0
        assert invoked["lint"] is False


class TestHooksJsonRegistration:
    _ROOT = Path(__file__).resolve().parents[2]

    def _push_commands(self, manifest_path: Path) -> list[str]:
        """Effective commands for the git-push block, dispatch-groups aware.

        Registrations route through invoke_dispatch_claude.py groups
        (#3075); a dispatcher command counts as one command per member
        shim so this contract stays pinned at the source layer.
        """
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        block = next(
            b
            for b in data["hooks"]["PreToolUse"]
            if b.get("matcher") == "Bash(git push*)"
        )
        groups = json.loads(
            (self._ROOT / ".claude" / "hooks" / "dispatch_groups.json").read_text(
                encoding="utf-8"
            )
        )["groups"]
        commands: list[str] = []
        for hook in block["hooks"]:
            command = hook.get("command", "") or ""
            if "invoke_dispatch_claude.py" in command:
                group_id = command.rsplit("--group", 1)[1].strip().split(";")[0].strip()
                commands.extend(shim["file"] for shim in groups[group_id]["shims"])
            else:
                commands.append(command)
        return commands

    def test_hooks_json_includes_markdownlint_guard(self):
        commands = self._push_commands(
            self._ROOT / ".claude" / "hooks" / "hooks.json"
        )
        assert any("invoke_markdownlint_guard.py" in cmd for cmd in commands)

    def test_settings_json_excludes_markdownlint_guard(self):
        settings = json.loads(
            (self._ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        assert "invoke_markdownlint_guard.py" not in json.dumps(settings)

    def test_generated_copilot_manifest_includes_markdownlint_guard(self):
        manifest = json.loads(
            (
                self._ROOT
                / "src"
                / "copilot-cli"
                / "hooks"
                / "PreToolUse"
                / "_manifest.json"
            ).read_text(encoding="utf-8")
        )
        assert any(
            shim.startswith("invoke_markdownlint_guard__")
            for shim in manifest["shims"]
        )
