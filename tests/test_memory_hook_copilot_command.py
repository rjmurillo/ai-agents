"""Run the registered Copilot recall command the way Copilot launches it.

Issue #4727. The command string comes from ``.github/hooks/memory-recall.json``
and runs as a subprocess from the repository root, which is where Copilot
resolves ``"cwd": "."``. The registered ``python3`` is kept, not
``sys.executable``, for the reason ``test_memory_hook_registration.py`` gives:
the uv venv would hide a missing dependency.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
(ENTRY,) = json.loads(
    (REPO_ROOT / ".github" / "hooks" / "memory-recall.json").read_text(encoding="utf-8")
)["hooks"]["userPromptTransformed"]
PROMPT = "how does dispatch group registration work"
CLOUD_VARS = ("COPILOT_AGENT_PROMPT", "GITHUB_COPILOT_API_TOKEN")

pytestmark = pytest.mark.skipif(
    shutil.which("python3") is None, reason="registered interpreter python3 not on PATH"
)


def _run(command, payload, cwd=REPO_ROOT, **env_overrides):
    """Run *command* under the Copilot hook environment, minus the uv venv.

    Copilot sets ``CLAUDE_PROJECT_DIR`` for repository hooks (issue #4727
    probe) and activates no virtualenv.
    """
    env = {k: v for k, v in os.environ.items() if k not in CLOUD_VARS}
    venv = env.pop("VIRTUAL_ENV", "")
    if venv:
        drop = {str(Path(venv) / "bin"), str(Path(venv) / "Scripts")}
        env["PATH"] = os.pathsep.join(
            e for e in env.get("PATH", "").split(os.pathsep) if e not in drop
        )
    env["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT)
    env.update(env_overrides)
    argv = ["sh", "-c", command] if isinstance(command, str) else command
    return subprocess.run(
        argv,
        input=json.dumps(payload),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
        env=env,
        timeout=60,
        check=False,
    )


@pytest.mark.unit
def test_match_emits_one_modified_transformed_prompt_object():
    transformed = f"<current_datetime>x</current_datetime>\n\n{PROMPT}"

    result = _run(ENTRY["bash"], {"prompt": PROMPT, "transformedPrompt": transformed})

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert list(document) == ["modifiedTransformedPrompt"]
    rewritten = document["modifiedTransformedPrompt"]
    assert rewritten.startswith(f"{transformed}\n\n<memory-context>")
    assert rewritten.rstrip().endswith("</memory-context>")
    assert "No module named" not in result.stderr


@pytest.mark.unit
@pytest.mark.parametrize(
    ("payload", "env"),
    [
        ({"prompt": PROMPT}, {}),
        ({"prompt": PROMPT, "transformedPrompt": PROMPT}, {"COPILOT_AGENT_PROMPT": PROMPT}),
    ],
    ids=["no-transformed-prompt", "cloud-agent"],
)
def test_command_writes_nothing(payload, env):
    result = _run(ENTRY["bash"], payload, **env)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@pytest.mark.unit
def test_claude_invocation_without_flag_stays_plain_text():
    command = ENTRY["bash"].removesuffix(" --copilot-transformed")

    result = _run(command, {"prompt": PROMPT, "transformedPrompt": PROMPT})

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("<memory-context>")


@pytest.mark.unit
def test_missing_scripts_tree_fails_open(tmp_path):
    """A consumer checkout without scripts/ gets no output and exit 0."""
    invoker = str(REPO_ROOT / ".claude" / "hooks" / "UserPromptSubmit" / "invoke_memory_recall.py")

    result = _run(
        ["python3", "-u", invoker, "--copilot-transformed"],
        {"prompt": PROMPT, "transformedPrompt": PROMPT},
        cwd=tmp_path,
        CLAUDE_PROJECT_DIR=str(tmp_path),
        PYTHONPATH="",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
