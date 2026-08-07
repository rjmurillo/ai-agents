"""Shared loader and helpers for the split ``new_pr.py`` tests."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_mod = _import_script("new_pr")
main = _mod.main
build_parser = _mod.build_parser
validate_conventional_commit = _mod.validate_conventional_commit
get_repo_root = _mod.get_repo_root
run_validations = _mod.run_validations
write_audit_log = _mod.write_audit_log
_resolve_validation_base = _mod._resolve_validation_base


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(
        args=[],
        returncode=rc,
        stdout=stdout,
        stderr=stderr,
    )


def _prepared_body(repo_root: Path, content: str = "PR body content") -> str:
    relative_path = _mod.prepare_pr_body(repo_root)
    (repo_root / relative_path).write_text(content, encoding="utf-8")
    return relative_path.as_posix()
