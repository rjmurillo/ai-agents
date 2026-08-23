"""Tests for the canonical bootstrap helper at .claude/lib/bootstrap.py.

Covers:
- ``resolve_plugin_lib_dir`` env-var path
- ``resolve_plugin_lib_dir`` manifest walk-up success
- ``resolve_plugin_lib_dir`` walk-up exhausted (returns None)
- ``resolve_plugin_lib_dir`` with ``hook_file=None`` (stack-inspection path)
- ``setup_hook_lib_path`` adds lib to ``sys.path``
- ``setup_hook_lib_path`` exits with ``fail_exit_code`` when lib missing
- ``setup_hook_lib_path`` is idempotent (second call does not double-insert)
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.ci import verify_code_env as verify

# The canonical bootstrap module lives outside any importable package, so we
# load it directly via importlib.util to avoid coupling these tests to the
# sys.path manipulation that production hooks perform.
REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = REPO_ROOT / ".claude" / "lib" / "bootstrap.py"


VM_BOOTSTRAP_PATH = REPO_ROOT / "scripts" / "bootstrap-vm.sh"
SETUP_ACTION_PATH = REPO_ROOT / ".github" / "actions" / "setup-code-env" / "action.yml"


WORKTRUNK_CONFIG_PATH = REPO_ROOT / ".config" / "wt.toml"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap_under_test", BOOTSTRAP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bootstrap_module():
    return _load_bootstrap()


@pytest.fixture
def fake_plugin_tree(tmp_path: Path) -> Path:
    """Create a minimal plugin layout: <root>/.claude-plugin/plugin.json + lib/."""
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "fake_hook.py").write_text("# fake", encoding="utf-8")
    return tmp_path


def test_resolve_uses_claude_plugin_root_env_var(
    bootstrap_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))

    result = bootstrap_module.resolve_plugin_lib_dir(hook_file=str(tmp_path / "x.py"))

    assert result == str(plugin_root.resolve() / "lib")


def test_resolve_walks_up_to_plugin_marker(
    bootstrap_module, fake_plugin_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    hook_file = fake_plugin_tree / "hooks" / "fake_hook.py"

    result = bootstrap_module.resolve_plugin_lib_dir(hook_file=str(hook_file))

    assert result == str(fake_plugin_tree / "lib")


def test_resolve_returns_none_when_walk_up_exhausted(
    bootstrap_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    # tmp_path has no .claude-plugin/plugin.json anywhere up the tree, so the
    # walk should reach the filesystem root and return None.
    isolated = tmp_path / "no_marker_here"
    isolated.mkdir()
    hook_file = isolated / "hook.py"
    hook_file.write_text("# fake", encoding="utf-8")

    # Walk up will eventually hit /, which obviously has no plugin marker.
    # We cannot guarantee the entire ancestor chain is marker-free on a real
    # checkout, so this test is only safe if no ancestor has the marker.
    cur = isolated
    while cur.parent != cur:
        if (cur / ".claude-plugin" / "plugin.json").is_file():
            pytest.skip(
                "ancestor of pytest tmp_path has a plugin marker; "
                "cannot test walk-up exhaustion in this environment"
            )
        cur = cur.parent

    result = bootstrap_module.resolve_plugin_lib_dir(hook_file=str(hook_file))

    assert result is None


def test_resolve_uses_caller_file_when_hook_file_none(
    bootstrap_module, fake_plugin_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When hook_file is None the resolver falls back to inspect.currentframe."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

    # Write a tiny script that imports the bootstrap module and calls
    # resolve_plugin_lib_dir() with no arguments, then prints the result.
    # Running it as a subprocess gives the inspect.currentframe() path a real
    # __file__ to walk up from.
    hook_dir = fake_plugin_tree / "hooks"
    runner = hook_dir / "runner.py"
    runner.write_text(
        f"""import sys, importlib.util
spec = importlib.util.spec_from_file_location("bs", r"{BOOTSTRAP_PATH}")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(m.resolve_plugin_lib_dir())
""",
        encoding="utf-8",
    )

    import subprocess

    proc = subprocess.run(
        [sys.executable, str(runner)],
        check=True,
        capture_output=True,
        text=True, encoding="utf-8",
        env={k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"},
    )

    assert proc.stdout.strip() == str(fake_plugin_tree / "lib")


def test_setup_hook_lib_path_adds_lib_to_sys_path(
    bootstrap_module, fake_plugin_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    lib_dir = str(fake_plugin_tree / "lib")
    # Ensure we start clean in case a prior test added the path.
    while lib_dir in sys.path:
        sys.path.remove(lib_dir)

    hook_file = fake_plugin_tree / "hooks" / "fake_hook.py"
    result = bootstrap_module.setup_hook_lib_path(str(hook_file), fail_exit_code=2)

    assert result == lib_dir
    assert sys.path[0] == lib_dir

    # cleanup so we do not leak state to other tests
    while lib_dir in sys.path:
        sys.path.remove(lib_dir)


def test_setup_hook_lib_path_exits_when_lib_missing(
    bootstrap_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the resolver returns a path that does not exist, exit with the
    requested code rather than continuing into an ImportError."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "nonexistent_plugin"))

    hook_file = tmp_path / "fake_hook.py"
    hook_file.write_text("# fake", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module.setup_hook_lib_path(str(hook_file), fail_exit_code=2)

    assert excinfo.value.code == 2


def test_setup_hook_lib_path_is_idempotent(
    bootstrap_module, fake_plugin_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling setup_hook_lib_path twice must not duplicate the entry in sys.path."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    lib_dir = str(fake_plugin_tree / "lib")
    while lib_dir in sys.path:
        sys.path.remove(lib_dir)

    hook_file = fake_plugin_tree / "hooks" / "fake_hook.py"
    bootstrap_module.setup_hook_lib_path(str(hook_file), fail_exit_code=2)
    bootstrap_module.setup_hook_lib_path(str(hook_file), fail_exit_code=2)

    occurrences = sum(1 for entry in sys.path if entry == lib_dir)
    assert occurrences == 1

    while lib_dir in sys.path:
        sys.path.remove(lib_dir)


def test_vm_bootstrap_installs_lefthook_after_dependency_sync() -> None:
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")

    sync = text.index("uv sync --frozen --extra dev")
    install = text.index("uv run --frozen lefthook install --reset-hooks-path")
    assert sync < install
    assert "git config core.hooksPath" not in text


def test_vm_bootstrap_has_no_bare_apt_get_or_unguarded_dpkg_i() -> None:
    """Pin Issue #5169's fix: every apt-get/dpkg-i call site routes through
    the quiet wrappers, so a future edit cannot silently reintroduce a bare
    call that dumps unpack-log noise into every SessionStart session."""
    text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "apt-get" in stripped:
            assert stripped.startswith(("quiet_apt_get", "quiet_run sudo apt-get")), (
                f"apt-get call bypasses the quiet wrapper: {stripped!r}"
            )
        if "dpkg -i" in stripped:
            assert stripped.startswith("quiet_run sudo dpkg -i"), (
                f"dpkg -i call bypasses the quiet wrapper: {stripped!r}"
            )


class TestConfigureGithubCli:
    """Run the shipped ``configure_github_cli`` against a fake ``gh``.

    The prior version of these tests asserted that certain substrings appeared
    in the function body, which passes whether or not the credential flow
    works: it cannot tell login-before-unset from unset-before-login, cannot
    see which token reaches stdin, and cannot notice a dropped failure check.
    These extract the function verbatim (per .claude/rules/
    canonical-source-mirror.md) and execute it, so the assertions are about
    behavior.
    """

    @staticmethod
    def _extract() -> str:
        text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")
        start = text.index("configure_github_cli() {")
        end = text.index("\n}\n", start) + len("\n}\n")
        return text[start:end]

    @staticmethod
    def _fake_gh(tmp_path: Path, fail_on: str = "") -> Path:
        """A ``gh`` that logs each invocation, its stdin, and the token env."""
        log = tmp_path / "gh.log"
        script = tmp_path / "gh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            f'log="{log}"\n'
            'printf "argv:%s\\n" "$*" >>"$log"\n'
            'printf "env:GH_TOKEN=%s GITHUB_TOKEN=%s\\n" '
            '"${GH_TOKEN-<unset>}" "${GITHUB_TOKEN-<unset>}" >>"$log"\n'
            'if [[ "$1 $2" == "auth login" ]]; then\n'
            '  printf "stdin:%s\\n" "$(cat)" >>"$log"\n'
            "fi\n"
            f'if [[ -n "{fail_on}" && "$1 $2" == "{fail_on}" ]]; then exit 1; fi\n'
            "exit 0\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return log

    def _run(
        self, tmp_path: Path, env: dict[str, str], fail_on: str = ""
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        log = self._fake_gh(tmp_path, fail_on)
        script = f"set -uo pipefail\n{self._extract()}\nconfigure_github_cli\n"
        base = {
            k: v for k, v in os.environ.items() if k not in {"GH_TOKEN", "GITHUB_TOKEN"}
        }
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env={**base, "PATH": f"{tmp_path}:{os.environ['PATH']}", **env},
            check=False,
        )
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return result, lines

    def test_persists_the_token_and_wires_git_transport(self, tmp_path: Path) -> None:
        result, lines = self._run(tmp_path, {"GITHUB_TOKEN": "tok-github"})

        assert result.returncode == 0, result.stderr
        argv = [line.removeprefix("argv:") for line in lines if line.startswith("argv:")]
        assert argv == [
            "auth login --with-token",
            "auth status",
            "api user --jq .login",
            "auth setup-git",
        ]
        assert "stdin:tok-github" in lines
        assert "✓ GitHub CLI authenticated" in result.stdout

    def test_login_sees_no_environment_token(self, tmp_path: Path) -> None:
        """gh prefers an env token over stored credentials, so the unset must
        happen before login or the stored credential never gets written."""
        _result, lines = self._run(
            tmp_path, {"GH_TOKEN": "tok-gh", "GITHUB_TOKEN": "tok-github"}
        )

        assert lines[1] == "env:GH_TOKEN=<unset> GITHUB_TOKEN=<unset>"

    def test_explicit_gh_token_wins_over_the_actions_alias(
        self, tmp_path: Path
    ) -> None:
        _result, lines = self._run(
            tmp_path, {"GH_TOKEN": "tok-gh", "GITHUB_TOKEN": "tok-github"}
        )

        assert "stdin:tok-gh" in lines
        assert "stdin:tok-github" not in lines

    def test_missing_token_warns_and_skips_every_gh_call(
        self, tmp_path: Path
    ) -> None:
        result, lines = self._run(tmp_path, {})

        assert result.returncode == 0
        assert lines == []
        assert "set GITHUB_TOKEN in the Codex environment" in result.stderr

    @pytest.mark.parametrize(
        ("fail_on", "expected_calls"),
        [
            ("auth login", 1),
            ("auth status", 2),
            ("api user", 3),
            ("auth setup-git", 4),
        ],
    )
    def test_a_failed_step_stops_the_sequence(
        self, tmp_path: Path, fail_on: str, expected_calls: int
    ) -> None:
        """Each step is checked, so a failure aborts the rest. The function
        still returns 0: bootstrap continues without GitHub auth by design
        (a hard exit here left the whole VM unprovisioned)."""
        result, lines = self._run(tmp_path, {"GITHUB_TOKEN": "tok"}, fail_on=fail_on)

        assert result.returncode == 0, result.stderr
        assert sum(1 for line in lines if line.startswith("argv:")) == expected_calls
        assert "WARNING" in result.stderr
        assert "✓ GitHub CLI authenticated" not in result.stdout

    def test_setup_git_failure_does_not_blame_the_token(self, tmp_path: Path) -> None:
        """`auth status` and `api user` already passed, so reporting missing
        authentication would send operators to rotate a valid credential."""
        result, _lines = self._run(
            tmp_path, {"GITHUB_TOKEN": "tok"}, fail_on="auth setup-git"
        )

        assert "authentication succeeded" in result.stderr
        assert "the token itself is valid" in result.stderr


class TestRestoreOriginRemote:
    """Run the shipped ``restore_origin_remote`` against real repositories."""

    @staticmethod
    def _extract() -> str:
        text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")
        start = text.index("restore_origin_remote() {")
        end = text.index("\n}\n", start) + len("\n}\n")
        return text[start:end]

    def _run(self, repo: Path) -> subprocess.CompletedProcess[str]:
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        script = f"set -uo pipefail\n{self._extract()}\nrestore_origin_remote\n"
        return subprocess.run(
            ["bash", "-c", script],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    @staticmethod
    def _origin(repo: Path) -> str:
        return subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()

    def test_adds_the_canonical_remote_when_origin_is_absent(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "no-origin"
        result = self._run(repo)

        assert result.returncode == 0, result.stderr
        assert self._origin(repo) == "https://github.com/rjmurillo/ai-agents.git"

    def test_leaves_an_existing_fork_remote_alone(self, tmp_path: Path) -> None:
        """Bootstrapping a fork must not repoint later fetches and pushes at
        upstream."""
        repo = tmp_path / "fork"
        fork_url = "https://github.com/someone-else/ai-agents.git"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", fork_url], cwd=repo, check=True
        )

        script = f"set -uo pipefail\n{self._extract()}\nrestore_origin_remote\n"
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert self._origin(repo) == fork_url


class TestQuietAptGet:
    """Exercise the real quiet_run/quiet_apt_get bash functions (Issue #5169)
    against fake sudo/apt-get/dpkg executables. Extracts the function bodies
    verbatim from bootstrap-vm.sh rather than reimplementing them, so a
    behavioral regression in the shipped script fails these tests instead of
    a copy that has silently drifted from it (see .claude/rules/
    canonical-source-mirror.md on self-referential test mirrors).
    """

    @staticmethod
    def _extract_helpers() -> str:
        text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")
        markers = [
            (r'^APT_LOG="\$\(mktemp\)"$', r"^trap cleanup_tmp EXIT$"),
            (r"^quiet_run\(\) \{$", r"^\}$"),
            (r"^quiet_apt_get\(\) \{$", r"^\}$"),
        ]
        lines = text.splitlines()
        blocks: list[str] = []
        for start_pat, end_pat in markers:
            start_re = re.compile(start_pat)
            end_re = re.compile(end_pat)
            start_idx = next(i for i, line in enumerate(lines) if start_re.match(line))
            end_idx = next(
                i for i in range(start_idx, len(lines)) if end_re.match(lines[i])
            )
            block = "\n".join(lines[start_idx : end_idx + 1])
            assert block, f"empty extraction for {start_pat!r}"
            blocks.append(block)
        return "\n\n".join(blocks)

    @staticmethod
    def _fake_bin(tmp_path: Path, name: str, body: str) -> None:
        script = tmp_path / name
        script.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
        script.chmod(0o755)

    def _run(
        self, tmp_path: Path, apt_get_body: str, bash_call: str
    ) -> subprocess.CompletedProcess[str]:
        self._fake_bin(tmp_path, "sudo", 'exec "$@"')
        self._fake_bin(tmp_path, "apt-get", apt_get_body)
        helpers = self._extract_helpers()
        full_script = f"set -euo pipefail\n{helpers}\n{bash_call}\n"
        env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
        return subprocess.run(
            ["bash", "-c", full_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=env,
            check=False,
        )

    def test_quiet_on_success(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path,
            apt_get_body='echo "Unpacking somepkg (noise)"\nexit 0',
            bash_call='quiet_apt_get install -y -qq somepkg\necho MARKER_OK',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "MARKER_OK"
        assert result.stderr == ""

    def test_warnings_surface_even_on_zero_exit(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path,
            apt_get_body=(
                'echo "Hit:1 http://archive.ubuntu.com noble InRelease"\n'
                'echo "W: GPG error: https://example.test NO_PUBKEY ABC123"\n'
                "exit 0"
            ),
            bash_call='quiet_apt_get update -qq\necho MARKER_OK',
        )
        assert result.returncode == 0, result.stderr
        assert "MARKER_OK" in result.stdout
        assert "NO_PUBKEY ABC123" in result.stderr

    def test_failure_dumps_log_and_aborts(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path,
            apt_get_body=(
                'echo "Unpacking failpkg (noise)"\n'
                'echo "E: some apt error" >&2\n'
                "exit 100"
            ),
            bash_call='quiet_apt_get install -y -qq failpkg\necho SHOULD_NOT_PRINT',
        )
        assert result.returncode != 0
        assert "SHOULD_NOT_PRINT" not in result.stdout
        assert "E: some apt error" in result.stderr

    def test_apt_log_removed_on_exit(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path,
            apt_get_body="exit 0",
            bash_call='quiet_apt_get update -qq\necho "$APT_LOG"',
        )
        assert result.returncode == 0, result.stderr
        log_path = Path(result.stdout.strip())
        assert not log_path.exists(), "APT_LOG was not cleaned up by the EXIT trap"


def test_setup_action_preserves_input_and_installs_lefthook_after_dependencies() -> None:
    text = SETUP_ACTION_PATH.read_text(encoding="utf-8")

    validation = text.index("- name: Validate git hook inputs")
    dependencies = text.index("- name: Install Python dependencies")
    install = text.index("- name: Enable git hooks")
    assert "enable-git-hooks:" in text
    assert validation < dependencies < install
    assert "if: inputs.enable-git-hooks == 'true' && inputs.enable-python != 'true'" in text
    assert "enable-git-hooks=true requires enable-python=true" in text
    assert "exit 2" in text
    assert "if: inputs.enable-git-hooks == 'true' && inputs.enable-python == 'true'" in text
    assert "uv run --frozen --extra dev lefthook install --reset-hooks-path" in text
    assert "scripts/ci/verify_code_env.py" in text
    assert "git config core.hooksPath" not in text


def test_setup_action_verification_gates_lefthook_on_both_inputs(monkeypatch) -> None:
    """The lefthook check runs only when git hooks and Python are both enabled.

    This replaces three assertions against the PowerShell that used to live in
    the action's verify step (extracted under ADR-006, issue #3532). The
    contract is the same; it is now measured by running the code rather than by
    grepping the shell that used to implement it.
    """
    calls: list[int] = []

    def _verify_lefthook() -> int:
        calls.append(1)
        return 0

    monkeypatch.setattr(verify, "verify_lefthook", _verify_lefthook)
    monkeypatch.setattr(verify.shutil, "which", lambda _name: None)
    monkeypatch.setenv("ENABLE_PESTER", "false")
    for hooks, python, expected in [
        ("true", "true", 1),
        ("true", "false", 0),
        ("false", "true", 0),
    ]:
        calls.clear()
        monkeypatch.setenv("ENABLE_GIT_HOOKS", hooks)
        monkeypatch.setenv("ENABLE_PYTHON", python)
        verify.main([])
        assert len(calls) == expected, (hooks, python)


def test_setup_action_verification_propagates_lefthook_exit_code(monkeypatch) -> None:
    """A failed lefthook check fails the step with its own exit code."""
    monkeypatch.setattr(
        verify, "_run", lambda _argv: subprocess.CompletedProcess(args=[], returncode=5, stdout="")
    )
    monkeypatch.setattr(verify.shutil, "which", lambda _name: None)
    monkeypatch.setenv("ENABLE_GIT_HOOKS", "true")
    monkeypatch.setenv("ENABLE_PYTHON", "true")
    monkeypatch.setenv("ENABLE_PESTER", "false")

    assert verify.verify_lefthook() == 5
    assert verify.main([]) == 5, "main must propagate the failing exit code, not swallow it"


def test_workflows_choose_hook_installation_explicitly() -> None:
    missing_input: list[str] = []

    for workflow_path in sorted(WORKFLOW_DIR.glob("*.yml")):
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                if step.get("uses") != "./.github/actions/setup-code-env":
                    continue
                if "enable-git-hooks" not in step.get("with", {}):
                    missing_input.append(workflow_path.name)

    assert missing_input == []


def test_worktrunk_post_create_installs_lefthook() -> None:
    text = WORKTRUNK_CONFIG_PATH.read_text(encoding="utf-8")

    assert (
        'configure-hooks = "uv run --frozen --extra dev lefthook install '
        '--reset-hooks-path && uv run --frozen --extra dev lefthook check-install"' in text
    )
    assert "core.hooksPath" not in text
