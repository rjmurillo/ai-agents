"""Runtime-contract guard for ``.github/hooks/*.json`` (ADR-109 B4, TASK-034).

Extends the PATTERN ``test_generate_hooks_runtime_contract.py`` established
for the plugin ``hooks.json`` contract (cwd set to the user's working
directory, the vendored script proven to resolve, a negative control
proving the harness has teeth) to the DIFFERENT contract Copilot CLI's
cloud agent uses for repository hook files, per
``.claude/skills/agent-harness-reference/references/official-hook-contracts.md``:

    Cloud agent:
    - loads only ``.github/hooks/*.json``;
    - runs in an ephemeral Linux sandbox;
    - honors only ``bash``, with ``command`` as fallback;
    - does not load user settings, repository settings, or installed
      plugins.

This is a NEW sibling file, not an addition to the existing 831-line
``test_generate_hooks_runtime_contract.py``, to respect the 500-line
taste-lint file-size ceiling TASK-034's Testing Requirements ask new test
files to hold to.

KNOWN GAP this test documents rather than fixes (TASK-034 is explicitly out
of scope for "what a plugin registers", ADR-097): today
``.claude/hooks/hooks.json`` and ``src/copilot-cli/hooks/hooks.json`` both
register zero hooks, so binplacing ``src/copilot-cli/hooks/`` into
``.github/hooks/`` verbatim is safe. But ``generate_hooks_emit._build_copilot_entry``
anchors every command it emits at ``$COPILOT_PLUGIN_ROOT`` (that module's
docstring: "Copilot CLI runs hooks with cwd set to the user's working
directory, NOT the plugin root... Anchoring at the plugin root makes the
invocation work regardless of where the user launched copilot from"). The
cloud agent's repository-hook contract "does not load... installed
plugins", so it never sets ``COPILOT_PLUGIN_ROOT``/``CLAUDE_PLUGIN_ROOT``: a
plugin-root-anchored command would silently fail to resolve there once any
entry stops being empty. This test proves the CORRECT shape for a
repository hook (cwd-relative, no plugin-root variable) resolves under the
cloud-agent contract, and that a bare relative command (missing the
``.github/hooks/`` anchor a cwd-relative command still needs) fails the
same harness, so the guard has teeth. It does not assert anything about
today's real (empty) ``.github/hooks/hooks.json``, because there is no
command in it yet to exercise.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.windows_path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Cloud agent honors bash only (module docstring). A minimal probe that a
# working bash actually runs commands, mirroring the sibling file's
# _require_bash without duplicating its Windows Git-Bash candidate list:
# the cloud agent itself only ever runs on Linux (module docstring, "runs
# in an ephemeral Linux sandbox"), so this guard does not need Windows
# bash discovery to stay faithful to the contract it tests.
_BASH = "bash"


def _bash_available() -> bool:
    try:
        proc = subprocess.run(
            [_BASH, "-c", "printf ok"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout == "ok"


requires_bash = pytest.mark.skipif(not _bash_available(), reason="no working bash on PATH")


def _cloud_agent_env() -> dict[str, str]:
    """Environment with no plugin-root variables, per the cloud-agent contract.

    "does not load... installed plugins" means COPILOT_PLUGIN_ROOT and
    CLAUDE_PLUGIN_ROOT are never set for a repository hook run this way.
    """
    import os

    env = os.environ.copy()
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    return env


def _materialize_repo_hook(tmp_path: Path) -> Path:
    """Build a repository working directory carrying a ``.github/hooks/*.json``.

    The command is cwd-relative (the correct shape for a repository hook,
    module docstring's KNOWN GAP paragraph), not anchored at any
    plugin-root variable: ``python3 -u .github/hooks/support/probe.py``.
    """
    repo = tmp_path / "userland"
    script = repo / ".github" / "hooks" / "support" / "probe.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("print('PROBE_RAN')\n", encoding="utf-8")

    doc = {
        "version": 1,
        "hooks": {
            "SessionStart": [
                {"bash": "python3 -u .github/hooks/support/probe.py"},
            ]
        },
    }
    hooks_json = repo / ".github" / "hooks" / "repo-hooks.json"
    hooks_json.write_text(json.dumps(doc), encoding="utf-8")
    return repo


def _emitted_bash_command(hooks_json: Path) -> str:
    doc = json.loads(hooks_json.read_text(encoding="utf-8"))
    entry = doc["hooks"]["SessionStart"][0]
    command = entry["bash"]
    assert isinstance(command, str)
    return command


@requires_bash
def test_cwd_relative_repository_hook_resolves_under_cloud_agent_contract(
    tmp_path: Path,
) -> None:
    """A cwd-relative .github/hooks/*.json command resolves with no plugin vars."""
    repo = _materialize_repo_hook(tmp_path)
    command = _emitted_bash_command(repo / ".github" / "hooks" / "repo-hooks.json")

    proc = subprocess.run(
        [_BASH, "-c", command],
        cwd=repo,
        env=_cloud_agent_env(),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "PROBE_RAN" in proc.stdout


@requires_bash
def test_plugin_root_anchored_command_fails_under_cloud_agent_contract(
    tmp_path: Path,
) -> None:
    """The plugin-hooks.json command shape (COPILOT_PLUGIN_ROOT-anchored) fails here.

    Documents the KNOWN GAP (module docstring): a command shaped the way
    ``generate_hooks_emit._build_copilot_entry`` emits it for the PLUGIN
    contract does not resolve under the cloud agent's repository-hook
    contract, because no plugin-root variable is set there.
    """
    repo = _materialize_repo_hook(tmp_path)
    plugin_style_command = (
        'cd "${COPILOT_PLUGIN_ROOT:-$CLAUDE_PLUGIN_ROOT}" && '
        "python3 -u hooks/support/probe.py"
    )

    proc = subprocess.run(
        [_BASH, "-c", plugin_style_command],
        cwd=repo,
        env=_cloud_agent_env(),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )

    assert proc.returncode != 0


# --- Gate over the COMMITTED artifact, not only a synthetic repo ----------


def _iter_command_strings(node: object) -> Iterator[str]:
    """Yield every string value nested anywhere in a parsed hooks.json document.

    Walks generically instead of assuming one entry shape (bare
    ``{"bash": ...}``, matcher-wrapped, or nested groups): whatever schema
    a future generator change produces, every command string it could ever
    write passes through a "bash", "powershell", or "command" key
    somewhere in the tree, and a generic walk catches all of them without
    tracking the schema by hand.
    """
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_command_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_command_strings(item)


def test_committed_github_hooks_json_has_no_plugin_root_anchored_commands() -> None:
    """The committed ``.github/hooks/hooks.json`` never anchors a command at a
    plugin-root variable.

    ``generate_hooks_emit._build_copilot_entry`` is the only entry-building
    function in this pipeline, and it unconditionally anchors every command
    at ``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}`` (module docstring's
    KNOWN GAP paragraph); there is no separate cloud-agent transform for the
    ``hooks-github`` binplace row, which copies ``src/copilot-cli/hooks/``
    (built by that same function) into ``.github/hooks/`` verbatim. The
    cloud agent never sets either plugin-root variable
    (``_cloud_agent_env``'s docstring), so a plugin-root-anchored command
    would silently fail to resolve there
    (``test_plugin_root_anchored_command_fails_under_cloud_agent_contract``
    proves the exact failure mode above).

    Both ``.claude/hooks/hooks.json`` and ``.github/hooks/hooks.json``
    register zero hooks today (ADR-097; confirmed by the ``doc.get("hooks")
    == {}`` assertion below), so this passes vacuously right now. It is the
    gate the module docstring's KNOWN GAP asks for: the moment a real
    registration reaches ``.github/hooks/hooks.json`` through the existing
    (plugin-root-anchored) generator path with no cloud-specific transform
    added first, this test fails loudly instead of shipping a hook that is
    silently dead in the cloud agent.
    """
    hooks_path = REPO_ROOT / ".github" / "hooks" / "hooks.json"
    doc = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert doc.get("hooks") == {}, (
        ".github/hooks/hooks.json now has real registrations; "
        "generate_hooks_emit._build_copilot_entry's plugin-root-anchored "
        "command shape is unsafe under the cloud-agent contract until a "
        "cloud-specific transform exists (see this file's module docstring "
        "KNOWN GAP paragraph)"
    )
    for command in _iter_command_strings(doc):
        assert "COPILOT_PLUGIN_ROOT" not in command
        assert "CLAUDE_PLUGIN_ROOT" not in command


@requires_bash
def test_negative_control_bare_relative_command_fails(tmp_path: Path) -> None:
    """A bare command missing the .github/hooks/ anchor fails the same harness.

    Proves the harness has teeth: if the positive test's command anchoring
    were wrong (e.g. missing the .github/hooks/ prefix), this negative
    control shows the failure mode it would produce.
    """
    repo = _materialize_repo_hook(tmp_path)
    bare_command = f"{sys.executable} -u support/probe.py"

    proc = subprocess.run(
        [_BASH, "-c", bare_command],
        cwd=repo,
        env=_cloud_agent_env(),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )

    assert proc.returncode != 0
