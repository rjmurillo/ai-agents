"""Shared setup for the completion-gate dynamic-load tests.

The gate is a script under `.claude/skills`, not an importable package, so the
tests load it by path once and share it.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import textwrap
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
GATE_PATH = (
    REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr" / "run_completion_gate.py"
)
NEW_PR = REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr" / "new_pr.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("run_completion_gate_dynamic", GATE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_completion_gate_dynamic"] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def loads(tmp_path: Path, body: str, name: str = "verify.py"):
    script = write(tmp_path, name, body)
    return gate._dynamic_loads(script.read_bytes(), script)


def closure(tmp_path: Path, *named: str) -> list[str]:
    return gate._expand_import_closure(list(named), tmp_path)


SHIPPED_CONFIG = REPO_ROOT / ".claude" / "skills" / "pr-review" / "pr-review-config.yaml"


def shipped_verifier_closure() -> tuple[list[str], list[str]]:
    """``(named, closure)`` for the shipped ``pr-review-config.yaml``.

    Built with the gate's own functions, so the files scanned are the files the
    gate byte-verifies: the same criteria (``completion_criteria`` plus every
    ``scripts.<harness>`` entry), the same argv classification, the same import
    and literal-dynamic-load closure. ``named`` is the work-tree-relative paths
    the commands name, which can include data files; ``closure`` adds what they
    import or load.
    """
    import yaml

    config = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    criteria = gate._extract_criteria(config) + gate._scripts_map_criteria(config)
    # The config's `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}` forms expand from
    # the environment. The pre-push hook exports CLAUDE_PLUGIN_ROOT=src/copilot-cli, which
    # would move the closure to the Copilot mirror. Pin the self-hosted `.claude` shape so
    # the scanned set does not depend on the caller.
    with mock.patch.dict(os.environ):
        for var in gate._PLUGIN_ROOT_ENV_VARS:
            os.environ.pop(var, None)
        named, _external, escaping = gate._collect_command_paths(criteria, 1, REPO_ROOT)
    assert escaping == [], f"config commands escape the work tree: {escaping}"
    return named, gate._expand_import_closure(named, REPO_ROOT)
