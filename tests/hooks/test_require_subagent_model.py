"""Tests for invoke_require_subagent_model (issue #4874).

Covers: allow on explicit model, allow on definition file in every search
root (Claude user/project/plugin, Copilot user/project/plugin), allow on
the CLAUDE_CODE_SUBAGENT_MODEL escape hatch, deny with remediation message
when neither exists, both payload spellings (Claude snake_case, Copilot
camelCase with dict and JSON-string args), fail-open on malformed input at
the process boundary, and the three registration surfaces.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = REPO_ROOT / ".claude" / "hooks" / "PreToolUse"
HOOK_PATH = HOOK_DIR / "invoke_require_subagent_model.py"
sys.path.insert(0, str(HOOK_DIR))

import invoke_require_subagent_model as guard


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    for variable in (
        "CLAUDE_CODE_SUBAGENT_MODEL",
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_PLUGIN_ROOT",
        "CLAUDE_PROJECT_DIR",
        "COPILOT_CLI",
        "COPILOT_HOME",
        "COPILOT_PLUGIN_ROOT",
    ):
        monkeypatch.delenv(variable, raising=False)
    return home


@pytest.fixture
def project(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    return project_dir


def _run(monkeypatch, payload: object) -> int:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    return guard.main()


def _claude_payload(project: Path, **tool_input: object) -> dict:
    return {"tool_name": "Agent", "cwd": str(project), "tool_input": tool_input}


def _large_model_less_payload(project: Path, size: int) -> dict[str, object]:
    return _claude_payload(
        project,
        subagent_type="general-purpose",
        prompt="x" * size,
    )


class TestAllowPaths:
    def test_unrelated_tool_allows(self, monkeypatch, project):
        payload = {"tool_name": "Bash", "cwd": str(project), "tool_input": {"command": "ls"}}
        assert _run(monkeypatch, payload) == 0
    def test_explicit_model_allows(self, monkeypatch, project):
        payload = _claude_payload(project, subagent_type="general-purpose", model="sonnet")
        assert _run(monkeypatch, payload) == 0

    def test_escape_hatch_env_allows(self, monkeypatch, project):
        monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "sonnet")
        payload = _claude_payload(project, subagent_type="general-purpose")
        assert _run(monkeypatch, payload) == 0
    def test_missing_agent_type_allows(self, monkeypatch, project):
        payload = _claude_payload(project, prompt="do a thing")
        assert _run(monkeypatch, payload) == 0

    def test_non_dict_tool_input_allows(self, monkeypatch, project):
        payload = {"tool_name": "Agent", "cwd": str(project), "tool_input": [1, 2]}
        assert _run(monkeypatch, payload) == 0
class TestDefinitionSearch:
    def test_project_claude_agent_allows(self, monkeypatch, project):
        agent = project / ".claude" / "agents" / "orchestrator.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: sonnet\n---\n", encoding="utf-8")
        payload = _claude_payload(project, subagent_type="orchestrator")
        assert _run(monkeypatch, payload) == 0

    def test_claude_project_dir_precedes_payload_subdirectory(
        self, monkeypatch, project
    ):
        agent = project / ".claude" / "agents" / "orchestrator.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: sonnet\n---\n", encoding="utf-8")
        subdirectory = project / "packages" / "app"
        subdirectory.mkdir(parents=True)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))

        payload = _claude_payload(subdirectory, subagent_type="orchestrator")

        assert _run(monkeypatch, payload) == 0
    def test_user_claude_agent_allows(self, monkeypatch, project, _isolated_environment):
        custom_root = _isolated_environment / "custom-claude"
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(custom_root))
        agent = custom_root / "agents" / "me.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: sonnet\n---\nbody\n", encoding="utf-8")
        payload = _claude_payload(project, subagent_type="me")
        assert _run(monkeypatch, payload) == 0
    def test_plugin_scoped_agent_allows(self, monkeypatch, project, _isolated_environment):
        agent = (
            _isolated_environment
            / ".claude"
            / "plugins"
            / "cache"
            / "market"
            / "pack"
            / "1.0"
            / "agents"
            / "reviewer.md"
        )
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: sonnet\n---\nbody\n", encoding="utf-8")
        payload = _claude_payload(project, subagent_type="pack:reviewer")
        assert _run(monkeypatch, payload) == 0

    def test_active_claude_plugin_root_allows_namespaced_agent(
        self, monkeypatch, project, tmp_path
    ):
        plugin_root = tmp_path / "active-claude-plugin"
        manifest = plugin_root / ".claude-plugin" / "plugin.json"
        agent = plugin_root / "agents" / "reviewer.md"
        manifest.parent.mkdir(parents=True)
        agent.parent.mkdir(parents=True)
        manifest.write_text('{"name": "pack"}', encoding="utf-8")
        agent.write_text("---\nmodel: sonnet\n---\n", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))

        payload = _claude_payload(project, subagent_type="pack:reviewer")

        assert _run(monkeypatch, payload) == 0

    def test_active_plugin_root_with_wrong_namespace_denies(
        self, monkeypatch, project, tmp_path
    ):
        plugin_root = tmp_path / "active-claude-plugin"
        manifest = plugin_root / ".claude-plugin" / "plugin.json"
        agent = plugin_root / "agents" / "reviewer.md"
        manifest.parent.mkdir(parents=True)
        agent.parent.mkdir(parents=True)
        manifest.write_text('{"name": "other-pack"}', encoding="utf-8")
        agent.write_text("---\nmodel: sonnet\n---\n", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))

        payload = _claude_payload(project, subagent_type="pack:reviewer")

        assert _run(monkeypatch, payload) == 2

    def test_copilot_plugin_scoped_agent_allows(
        self, monkeypatch, project, _isolated_environment
    ):
        agent = (
            _isolated_environment
            / ".copilot"
            / "installed-plugins"
            / "market"
            / "pack"
            / "agents"
            / "reviewer.agent.md"
        )
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: claude-sonnet-4.6\n---\nbody\n", encoding="utf-8")
        payload = {
            "toolName": "task",
            "cwd": str(project),
            "toolArgs": {"agent_type": "pack:reviewer"},
        }
        assert _run(monkeypatch, payload) == 0

    def test_active_copilot_plugin_root_allows_namespaced_agent(
        self, monkeypatch, project, tmp_path
    ):
        plugin_root = tmp_path / "active-copilot-plugin"
        manifest = plugin_root / ".claude-plugin" / "plugin.json"
        agent = plugin_root / "agents" / "reviewer.agent.md"
        manifest.parent.mkdir(parents=True)
        agent.parent.mkdir(parents=True)
        manifest.write_text('{"name": "pack"}', encoding="utf-8")
        agent.write_text("---\nmodel: claude-sonnet-4.6\n---\n", encoding="utf-8")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(plugin_root))

        payload = {
            "toolName": "task",
            "cwd": str(project),
            "toolArgs": {"agent_type": "pack:reviewer"},
        }

        assert _run(monkeypatch, payload) == 0

    def test_copilot_user_agent_allows(self, monkeypatch, project, _isolated_environment):
        custom_root = _isolated_environment / "custom-copilot"
        monkeypatch.setenv("COPILOT_HOME", str(custom_root))
        agent = custom_root / "agents" / "me.agent.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: claude-sonnet-4.6\n---\nbody\n", encoding="utf-8")
        payload = {
            "toolName": "task",
            "cwd": str(project),
            "toolArgs": json.dumps({"agent_type": "me", "prompt": "x"}),
        }
        assert _run(monkeypatch, payload) == 0

    def test_copilot_project_github_agent_allows(self, monkeypatch, project):
        agent = project / ".github" / "agents" / "fix-ci.agent.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: claude-sonnet-4.6\n---\nbody\n", encoding="utf-8")
        # Copilot detection uses payload schema (toolName vs tool_name).
        # Process cwd must point to the project root for Copilot payloads.
        monkeypatch.chdir(project)
        payload = {
            "toolName": "task",
            "cwd": str(project),
            "toolArgs": {"agent_type": "fix-ci"},
        }
        assert _run(monkeypatch, payload) == 0

    def test_project_pinned_definition_overrides_unpinned_user(
        self, monkeypatch, project, _isolated_environment
    ):
        project_agent = project / ".claude" / "agents" / "reviewer.md"
        user_agent = _isolated_environment / ".claude" / "agents" / "reviewer.md"
        project_agent.parent.mkdir(parents=True)
        user_agent.parent.mkdir(parents=True)
        project_agent.write_text("---\nmodel: sonnet\n---\n", encoding="utf-8")
        user_agent.write_text("---\n---\n", encoding="utf-8")
        assert _run(monkeypatch, _claude_payload(project, subagent_type="reviewer")) == 0


class TestDenyPaths:
    @pytest.mark.parametrize("model", [None, "", "   ", "null", "none", "~", '""', "''"])
    def test_empty_model_argument_denies(self, monkeypatch, project, model):
        payload = _claude_payload(project, subagent_type="general-purpose", model=model)
        assert _run(monkeypatch, payload) == 2

    @pytest.mark.parametrize(
        "definition",
        [
            "body\n", "---\nmodel:\n---\n", "---\nmodel: null\n---\n",
            "---\nmodel: sonnet\n", "---\nmodel: []\n---\n",
            "---\nmodel: [sonnet]\n---\n", "---\nmodel: {name: sonnet}\n---\n",
            "---\nmodel: true\n---\n", "---\nmodel: 42\n---\n",
            "---\nmodel: \"   \"\n---\n", "---\nmodel: 0x10\n---\n",
            "---\nmodel: 0o10\n---\n", "---\nmodel: 0b10\n---\n",
            "---\nmodel: .inf\n---\n", "---\nmodel: 2026-08-13\n---\n",
        ],
    )
    def test_definition_without_nonempty_model_denies(
        self, monkeypatch, project, _isolated_environment, definition
    ):
        agent = _isolated_environment / ".claude" / "agents" / "unpinned.md"
        agent.parent.mkdir(parents=True)
        agent.write_text(definition, encoding="utf-8")
        payload = _claude_payload(project, subagent_type="unpinned")
        assert _run(monkeypatch, payload) == 2

    def test_unpinned_project_definition_overrides_pinned_user(
        self, monkeypatch, project, _isolated_environment
    ):
        project_agent = project / ".claude" / "agents" / "reviewer.md"
        user_agent = _isolated_environment / ".claude" / "agents" / "reviewer.md"
        project_agent.parent.mkdir(parents=True)
        user_agent.parent.mkdir(parents=True)
        project_agent.write_text("---\n---\n", encoding="utf-8")
        user_agent.write_text("---\nmodel: sonnet\n---\n", encoding="utf-8")
        assert _run(monkeypatch, _claude_payload(project, subagent_type="reviewer")) == 2

    def test_definition_from_other_harness_does_not_allow(self, monkeypatch, project):
        agent = project / ".github" / "agents" / "copilot-only.agent.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: claude-sonnet-4.6\n---\n", encoding="utf-8")
        payload = _claude_payload(project, subagent_type="copilot-only")
        assert _run(monkeypatch, payload) == 2

    def test_other_plugin_definition_does_not_allow(
        self, monkeypatch, project, _isolated_environment
    ):
        agent = (
            _isolated_environment
            / ".claude"
            / "plugins"
            / "cache"
            / "market"
            / "pack-b"
            / "1.0"
            / "agents"
            / "reviewer.md"
        )
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: sonnet\n---\n", encoding="utf-8")
        payload = _claude_payload(project, subagent_type="pack-a:reviewer")
        assert _run(monkeypatch, payload) == 2

    def test_plugin_definition_does_not_allow_bare_agent(
        self, monkeypatch, project, _isolated_environment
    ):
        agent = (
            _isolated_environment
            / ".claude"
            / "plugins"
            / "cache"
            / "market"
            / "pack"
            / "1.0"
            / "agents"
            / "reviewer.md"
        )
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: sonnet\n---\n", encoding="utf-8")
        payload = _claude_payload(project, subagent_type="reviewer")
        assert _run(monkeypatch, payload) == 2

    def test_other_copilot_plugin_definition_does_not_allow(
        self, monkeypatch, project, _isolated_environment
    ):
        agent = (
            _isolated_environment
            / ".copilot"
            / "installed-plugins"
            / "market"
            / "pack-b"
            / "agents"
            / "reviewer.agent.md"
        )
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmodel: claude-sonnet-4.6\n---\n", encoding="utf-8")
        payload = {
            "toolName": "task",
            "cwd": str(project),
            "toolArgs": {"agent_type": "pack-a:reviewer"},
        }
        assert _run(monkeypatch, payload) == 2

    def test_conflicting_plugin_versions_deny(
        self, monkeypatch, project, _isolated_environment
    ):
        root = _isolated_environment / ".claude" / "plugins" / "cache" / "market" / "pack"
        for version, model in (("1.0", "sonnet"), ("2.0", None)):
            agent = root / version / "agents" / "reviewer.md"
            agent.parent.mkdir(parents=True)
            value = f"model: {model}\n" if model else ""
            agent.write_text(f"---\n{value}---\n", encoding="utf-8")
        payload = _claude_payload(project, subagent_type="pack:reviewer")
        assert _run(monkeypatch, payload) == 2

    def test_claude_builtin_without_model_denies(self, monkeypatch, project, capsys):
        payload = _claude_payload(project, subagent_type="general-purpose", prompt="x")
        assert _run(monkeypatch, payload) == 2
        err = capsys.readouterr().err
        assert "general-purpose" in err
        assert "CLAUDE_CODE_SUBAGENT_MODEL" in err

    def test_copilot_camelcase_without_model_denies(self, monkeypatch, project, capsys):
        payload = {
            "toolName": "task",
            "cwd": str(project),
            "toolArgs": {"agent_type": "general-purpose", "prompt": "x"},
        }
        assert _run(monkeypatch, payload) == 2
        assert "general-purpose" in capsys.readouterr().err

    def test_null_tool_input_falls_back_to_tool_args(self, monkeypatch, project, capsys):
        payload = {
            "toolName": "task",
            "cwd": str(project),
            "tool_input": None,
            "toolArgs": {"agent_type": "general-purpose", "prompt": "x"},
        }
        assert _run(monkeypatch, payload) == 2
        assert "general-purpose" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "spoof",
        ["*", "**", "?", "[a]", "../me", "..\\me", "..:me"],
    )
    def test_unsafe_names_cannot_spoof_the_search(
        self, monkeypatch, project, _isolated_environment, spoof
    ):
        # Unsafe subagent types must not escape or expand the definition
        # search (CWE-22/CWE-400 shape).
        agent = _isolated_environment / ".claude" / "agents" / "me.md"
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_text("---\nmodel: sonnet\n---\n", encoding="utf-8")
        payload = _claude_payload(project, subagent_type=spoof)
        assert _run(monkeypatch, payload) == 2

    def test_legacy_task_tool_name_denies(self, monkeypatch, project):
        payload = {
            "tool_name": "Task",
            "cwd": str(project),
            "tool_input": {"subagent_type": "Explore"},
        }
        assert _run(monkeypatch, payload) == 2


class TestProcessBoundary:
    """The __main__ contract: deny is exit 2, malformed input fails open (#4672)."""

    def _spawn(self, stdin_text: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({"HOME": str(cwd), "USERPROFILE": str(cwd)})
        return subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=cwd,
            env=env,
        )

    def test_garbage_stdin_fails_open(self, tmp_path):
        result = self._spawn("not json at all", tmp_path)
        assert result.returncode == 0
        assert "fail-open" in result.stderr
        assert "[hook-error]" in result.stderr

    def test_empty_stdin_fails_open(self, tmp_path):
        assert self._spawn("", tmp_path).returncode == 0

    def test_deny_exits_two_with_message(self, tmp_path):
        payload = json.dumps(
            {
                "tool_name": "Agent",
                "cwd": str(tmp_path),
                "tool_input": {"subagent_type": "no-such-agent"},
            }
        )
        result = self._spawn(payload, tmp_path)
        assert result.returncode == 2
        assert "no-such-agent" in result.stderr

    def test_model_less_payload_over_128_kib_denies(self, tmp_path):
        payload = json.dumps(_large_model_less_payload(tmp_path, 129 * 1024))

        result = self._spawn(payload, tmp_path)

        assert result.returncode == 2
        assert "general-purpose" in result.stderr

    def test_payload_over_two_mib_denies_instead_of_failing_open(self, tmp_path):
        payload = json.dumps(_large_model_less_payload(tmp_path, 2 * 1024 * 1024))

        result = self._spawn(payload, tmp_path)

        assert result.returncode == 2
        assert "exceeds" in result.stderr


class TestRegistrations:
    @staticmethod
    def _github_hook_entry() -> dict[str, object]:
        config = json.loads(
            (REPO_ROOT / ".github/hooks/require-subagent-model.json").read_text(
                encoding="utf-8"
            )
        )
        return config["hooks"]["preToolUse"][0]
    @staticmethod
    def _run_registered_command(
        entry: dict[str, object], payload: dict[str, object], home: Path
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({"HOME": str(home), "USERPROFILE": str(home)})
        command = (
            ["pwsh", "-NoProfile", "-Command", str(entry["powershell"])]
            if os.name == "nt"
            else ["bash", "-c", str(entry["bash"])]
        )
        return subprocess.run(
            command, input=json.dumps(payload), capture_output=True, text=True,
            check=False, cwd=REPO_ROOT, env=env, timeout=30,
        )
    def test_dispatch_group_registered(self):
        manifest = json.loads(
            (REPO_ROOT / ".claude/hooks/dispatch_groups.json").read_text(encoding="utf-8")
        )
        group = manifest["groups"]["plugin-pretooluse-10-require_subagent_model"]
        assert group["event"] == "PreToolUse"
        assert group["mode"] == "gate"
        assert group["matcher"] == "^(Agent|Task)$"
        assert group["surface"] == "plugin"
        assert group["shims"][0]["file"] == "PreToolUse/invoke_require_subagent_model.py"
        assert group["shims"][0]["copilotMatcher"] == "^(Agent|Task)$"
    def test_no_settings_json_pretooluse_twin(self):
        """ADR-085 forbids a settings.json twin for plugin gates."""
        settings = json.loads(
            (REPO_ROOT / ".claude/settings.json").read_text(encoding="utf-8")
        )
        assert "PreToolUse" not in settings.get("hooks", {}), (
            "settings.json must not register a PreToolUse twin; "
            "the plugin dispatcher handles this gate (ADR-085)"
        )

    def test_plugin_hooks_json_registered(self):
        plugin_hooks = json.loads(
            (REPO_ROOT / ".claude/hooks/hooks.json").read_text(encoding="utf-8")
        )
        matching = [
            entry for entry in plugin_hooks["hooks"]["PreToolUse"]
            if entry.get("matcher") == "^(Agent|Task)$"
            and any(
                "plugin-pretooluse-10-require_subagent_model" in hook["command"]
                for hook in entry["hooks"]
            )
        ]
        assert len(matching) == 1
    def test_github_hooks_registered(self):
        config = json.loads(
            (REPO_ROOT / ".github/hooks/require-subagent-model.json").read_text(
                encoding="utf-8"
            )
        )
        assert config["version"] == 1
        entry = self._github_hook_entry()
        assert entry["matcher"] == "task"
        assert "invoke_require_subagent_model.py" in entry["bash"]
        assert "invoke_require_subagent_model.py" in entry["powershell"]
    def test_github_hook_command_executes_and_broken_path_fails(self, tmp_path):
        entry = self._github_hook_entry()
        payload = {
            "toolName": "task", "cwd": str(tmp_path),
            "toolArgs": {"agent_type": "general-purpose"},
        }
        assert self._run_registered_command(entry, payload, tmp_path).returncode == 2
        broken = {
            key: (
                value.replace(
                    "invoke_require_subagent_model.py",
                    "missing_require_subagent_model.py",
                )
                if key in {"bash", "powershell"} else value
            )
            for key, value in entry.items()
        }
        assert self._run_registered_command(broken, payload, tmp_path).returncode != 0
    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({"tool_name": "Agent", "tool_input": {"subagent_type": "general-purpose"}}, 2),
            ({"toolName": "task", "toolArgs": {"agent_type": "general-purpose"}}, 0),
            ({"toolName": "Read", "toolArgs": {"filePath": "README.md"}}, 0),
        ],
    )
    def test_generated_copilot_shim_executes_from_foreign_cwd(
        self, tmp_path, payload, expected
    ):
        shims = list(
            (REPO_ROOT / "src/copilot-cli/hooks/PreToolUse").glob(
                "invoke_require_subagent_model__*.py"
            )
        )
        assert len(shims) == 1
        env = os.environ.copy()
        env.update({
            "HOME": str(tmp_path), "USERPROFILE": str(tmp_path),
            "COPILOT_PLUGIN_ROOT": str(REPO_ROOT / "src/copilot-cli"),
        })
        result = subprocess.run(
            [sys.executable, str(shims[0])],
            input=json.dumps({**payload, "cwd": str(tmp_path)}),
            capture_output=True, text=True, check=False, cwd=tmp_path,
            env=env, timeout=30,
        )
        assert result.returncode == expected, result.stderr
    def test_generated_copilot_shim_malformed_input_fails_open(self, tmp_path):
        shims = list(
            (REPO_ROOT / "src/copilot-cli/hooks/PreToolUse").glob(
                "invoke_require_subagent_model__*.py"
            )
        )
        assert len(shims) == 1
        env = os.environ.copy()
        env.update({
            "HOME": str(tmp_path), "USERPROFILE": str(tmp_path),
            "COPILOT_PLUGIN_ROOT": str(REPO_ROOT / "src/copilot-cli"),
        })
        result = subprocess.run(
            [sys.executable, str(shims[0])], input="not json",
            capture_output=True, text=True, check=False, cwd=tmp_path,
            env=env, timeout=30,
        )
        assert result.returncode == 0
        assert "malformed JSON" in result.stderr

    def test_generated_copilot_shim_model_less_payload_over_128_kib_denies(
        self, tmp_path
    ):
        shims = list(
            (REPO_ROOT / "src/copilot-cli/hooks/PreToolUse").glob(
                "invoke_require_subagent_model__*.py"
            )
        )
        assert len(shims) == 1
        env = os.environ.copy()
        env.update({
            "HOME": str(tmp_path), "USERPROFILE": str(tmp_path),
            "COPILOT_PLUGIN_ROOT": str(REPO_ROOT / "src/copilot-cli"),
        })
        payload = _large_model_less_payload(tmp_path, 129 * 1024)

        result = subprocess.run(
            [sys.executable, str(shims[0])],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
            env=env,
            timeout=30,
        )

        assert result.returncode == 2
        assert "general-purpose" in result.stderr
