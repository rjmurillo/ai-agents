#!/usr/bin/env python3
"""The shipped recall closure imports with PyYAML and python-frontmatter blocked.

``plugin-self-containment.md`` MUST 4: a plugin-root script runs under bare
``python3``, and its closure includes the shipped lib. ``memory_enhancement``
is not in the ``shipped-lib-no-runtime-dependencies`` import-linter contract
(that contract keeps a shrink-only ignore baseline), so this test enforces the
guards at runtime: a subprocess installs a meta-path blocker for ``yaml`` and
``frontmatter``, puts ONLY the shipped ``lib/`` on ``sys.path``, imports the
recall closure, and runs ``recall_block`` against a repository.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_LIB = REPO_ROOT / "src" / "claude" / "lib"
TIMEOUT_SECONDS = 60

_BLOCKER = textwrap.dedent(
    """
    import sys

    class _Blocker:
        BLOCKED = {"yaml", "frontmatter"}

        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in self.BLOCKED:
                raise ImportError(f"blocked for test: {name}")
            return None

    sys.meta_path.insert(0, _Blocker())
    """
)


def _run(script: str, cwd: Path, env_extra: dict[str, str] | None = None):
    import os

    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-I", "-c", _BLOCKER + textwrap.dedent(script)],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_SECONDS,
    )


def test_the_blocker_actually_blocks_yaml_and_frontmatter(tmp_path: Path) -> None:
    """Negative control: without it the passing tests below prove nothing."""
    result = _run("import yaml", tmp_path)

    assert result.returncode != 0
    assert "blocked for test: yaml" in result.stderr


def test_the_closure_imports_and_recalls_without_yaml_or_frontmatter(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    memories = project / ".serena" / "memories"
    memories.mkdir(parents=True)
    (memories / "gateway-cutover.md").write_text(
        "---\ntitle: Gateway cutover\ntags: [x]\n---\n\nMove every service behind the gateway.\n",
        encoding="utf-8",
    )
    script = f"""
        import os, sys
        sys.path.insert(0, {str(SHIPPED_LIB)!r})
        from memory_enhancement.hooks import user_prompt_submit_memory as hook
        from memory_enhancement import search, serena_integration
        assert serena_integration.frontmatter_reader.frontmatter is None
        assert serena_integration.frontmatter_reader.yaml is None
        assert "yaml" not in sys.modules and "frontmatter" not in sys.modules
        assert os.path.commonpath([{str(SHIPPED_LIB)!r}, hook.__file__]) == {str(SHIPPED_LIB)!r}
        out = hook.recall_block("gateway cutover")
        assert "<memory-context>" in out, out
        print("closure-ok")
    """

    result = _run(script, tmp_path, {"CLAUDE_PROJECT_DIR": str(project)})

    assert result.returncode == 0, result.stderr
    assert "closure-ok" in result.stdout


@pytest.mark.parametrize(
    "module", ["interpreter", "search", "serena_integration", "frontmatter_reader", "verification"]
)
def test_each_module_the_shim_can_reach_imports_without_yaml_or_frontmatter(
    tmp_path: Path, module: str
) -> None:
    script = f"""
        import sys
        sys.path.insert(0, {str(SHIPPED_LIB)!r})
        import importlib
        importlib.import_module("memory_enhancement.{module}")
        print("ok")
    """

    result = _run(script, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
