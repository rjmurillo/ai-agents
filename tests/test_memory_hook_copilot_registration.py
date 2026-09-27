"""Memory recall reaches GitHub Copilot CLI through userPromptTransformed.

Issue #4727: Copilot CLI drops all output from config-file
``userPromptSubmitted`` hooks, so the ``.claude/settings.json`` recall
registration runs under Copilot and changes nothing. The documented
config-file channel is ``userPromptTransformed``, whose output field
``modifiedTransformedPrompt`` replaces the model-facing prompt.

These tests run the command string from ``.github/hooks/memory-recall.json``
as a subprocess from the repository root, which is where Copilot resolves
``"cwd": "."``. The registered ``python3`` is kept, not ``sys.executable``,
for the same reason ``test_memory_hook_registration.py`` gives.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / ".github" / "hooks" / "memory-recall.json"
INVOKER = ".claude/hooks/UserPromptSubmit/invoke_memory_recall.py"
FLAG = "--copilot-transformed"
PROMPT = "how does dispatch group registration work"
CLOUD_AGENT_VARS = ("COPILOT_AGENT_PROMPT", "GITHUB_COPILOT_API_TOKEN")

pytestmark = pytest.mark.skipif(
    shutil.which("python3") is None, reason="registered interpreter python3 not on PATH"
)


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _entries(event: str) -> list[dict]:
    return _manifest()["hooks"].get(event, [])


def _bash_command() -> str:
    (entry,) = _entries("userPromptTransformed")
    return entry["bash"]


def _copilot_env() -> dict[str, str]:
    """Environment a repository hook sees under Copilot CLI, minus the venv.

    Copilot sets ``CLAUDE_PROJECT_DIR`` for repository hooks (issue #4727
    probe), and activates no virtualenv, so the uv venv is dropped from PATH.
    """
    env = dict(os.environ)
    virtual_env = env.pop("VIRTUAL_ENV", "")
    if virtual_env:
        venv_bin = {str(Path(virtual_env) / "bin"), str(Path(virtual_env) / "Scripts")}
        entries = [e for e in env.get("PATH", "").split(os.pathsep) if e not in venv_bin]
        env["PATH"] = os.pathsep.join(entries)
    env["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT)
    for name in CLOUD_AGENT_VARS:
        env.pop(name, None)
    return env


def _run(
    command: str, payload: object, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", "-c", command],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        env={**_copilot_env(), **(extra_env or {})},
        timeout=60,
        check=False,
    )


class TestManifest:
    """The registration uses Copilot's native schema and the only live event."""

    @pytest.mark.unit
    def test_registers_one_user_prompt_transformed_entry(self):
        manifest = _manifest()

        assert manifest["version"] == 1
        assert list(manifest["hooks"]) == ["userPromptTransformed"]
        assert len(_entries("userPromptTransformed")) == 1

    @pytest.mark.unit
    def test_entry_runs_the_recall_invoker_from_repo_root(self):
        (entry,) = _entries("userPromptTransformed")

        assert entry["type"] == "command"
        assert entry["cwd"] == "."
        for shell in ("bash", "powershell"):
            argv = shlex.split(entry[shell])
            assert argv[-2:] == [INVOKER, FLAG]
        assert (REPO_ROOT / INVOKER).is_file()

    @pytest.mark.unit
    def test_timeout_matches_the_claude_registration(self):
        (entry,) = _entries("userPromptTransformed")

        assert entry["timeoutSec"] == 10

    @pytest.mark.unit
    @pytest.mark.parametrize("event", ["userPromptSubmitted", "UserPromptSubmit"])
    def test_no_registration_on_the_dropped_output_event(self, event):
        assert _entries(event) == []


class TestRegisteredCommand:
    """Run the exact registered command the way Copilot launches it."""

    @pytest.mark.unit
    def test_match_emits_one_modified_transformed_prompt_object(self):
        transformed = f"<current_datetime>x</current_datetime>\n\n{PROMPT}"

        result = _run(_bash_command(), {"prompt": PROMPT, "transformedPrompt": transformed})

        assert result.returncode == 0, result.stderr
        document = json.loads(result.stdout)
        assert list(document) == ["modifiedTransformedPrompt"]
        rewritten = document["modifiedTransformedPrompt"]
        assert rewritten.startswith(f"{transformed}\n\n<memory-context>")
        assert rewritten.rstrip().endswith("</memory-context>")
        assert "No module named" not in result.stderr

    @pytest.mark.unit
    def test_payload_without_transformed_prompt_writes_nothing(self):
        result = _run(_bash_command(), {"prompt": PROMPT})

        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    @pytest.mark.unit
    def test_cloud_agent_sandbox_writes_nothing(self):
        """Cloud agent runs unattended on a checked-out branch (ADR-068, #4727)."""
        payload = {"prompt": PROMPT, "transformedPrompt": PROMPT}

        result = _run(_bash_command(), payload, {"COPILOT_AGENT_PROMPT": PROMPT})

        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    @pytest.mark.unit
    def test_claude_invocation_without_flag_stays_plain_text(self):
        command = _bash_command().removesuffix(f" {FLAG}")

        result = _run(command, {"prompt": PROMPT, "transformedPrompt": PROMPT})

        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith("<memory-context>")

    @pytest.mark.unit
    def test_missing_scripts_tree_fails_open(self, tmp_path):
        """A consumer checkout without scripts/ gets no output and exit 0."""
        env = _copilot_env()
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        env["PYTHONPATH"] = ""

        result = subprocess.run(
            ["python3", "-u", str(REPO_ROOT / INVOKER), FLAG],
            input=json.dumps({"prompt": PROMPT, "transformedPrompt": PROMPT}),
            capture_output=True,
            encoding="utf-8",
            cwd=str(tmp_path),
            env=env,
            timeout=60,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
