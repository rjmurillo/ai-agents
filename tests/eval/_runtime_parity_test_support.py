"""Shared loader for runtime parity evaluator tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
SCRIPT = EVAL_DIR / "eval_runtime_parity.py"
FIXTURES = EVAL_DIR / "examples" / "runtime-parity-fixtures.json"

spec = importlib.util.spec_from_file_location("eval_runtime_parity", SCRIPT)
assert spec and spec.loader
parity = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = parity
path_added = str(EVAL_DIR) not in sys.path
if path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    spec.loader.exec_module(parity)
finally:
    if path_added:
        sys.path.remove(str(EVAL_DIR))

runtime_parity = sys.modules["_runtime_parity"]
runtime_harness = sys.modules["_runtime_harness"]
runtime_grader = sys.modules["_runtime_grader"]


def _workspace_root(cwd: Path) -> Path:
    """Find the git root above `cwd`, the way a real CLI discovers it.

    `_verify_copilot_instruction_listing` (SPEC-4880 T7) runs the listing
    command from a fixture's `cwd`, which may nest below the workspace root
    (for example `.github/workflows`), not always at the root itself.
    """
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _path_local_listing(root: Path, cwd: Path) -> list[dict[str, str]]:
    """Report `path_local` `AGENTS.md`/`CLAUDE.md` files from root down to cwd.

    Mirrors `copilot instruction list --json` (CLI 1.0.89) probed 2026-09-27
    in a scratch repo: the root and every ancestor directory between the git
    root and the working directory contributes its own `AGENTS.md`/
    `CLAUDE.md`, and `.github/copilot-instructions.md` is always listed when
    present, regardless of `cwd`.
    """
    relative_cwd = cwd.resolve().relative_to(root.resolve())
    directory = root.resolve()
    directories = [directory]
    for part in relative_cwd.parts:
        directory = directory / part
        directories.append(directory)
    found: list[dict[str, str]] = []
    for candidate_dir in directories:
        for name in ("AGENTS.md", "CLAUDE.md"):
            candidate = candidate_dir / name
            if candidate.is_file():
                found.append({"sourcePath": candidate.relative_to(root).as_posix()})
    copilot_instructions = root / ".github" / "copilot-instructions.md"
    if copilot_instructions.is_file():
        found.append({"sourcePath": ".github/copilot-instructions.md"})
    return found


def _copilot_instruction_listing(cwd: Path) -> list[dict[str, str]]:
    """Fake `copilot instruction list --json`: report every installed source.

    A real Copilot CLI lists whatever it loaded; this fake instead reports
    exactly what `prepare_workspace` wrote under `.github/instructions/` and
    at every `path_local` path in `cwd`'s ancestor chain (SPEC-4880 T7), so
    the listing preflight in `_verify_copilot_instruction_listing` sees a
    matching set without a real CLI call. `cwd` may be the workspace root
    (every fixture before `path_local` existed) or a nested directory.
    """
    root = _workspace_root(cwd)
    instructions_dir = root / ".github" / "instructions"
    entries = [
        {"sourcePath": path.relative_to(root).as_posix()}
        for path in (
            sorted(instructions_dir.glob("*.instructions.md")) if instructions_dir.is_dir() else []
        )
    ]
    entries.extend(_path_local_listing(root, cwd))
    return entries


class FixedResponseRunner:
    """A CLI runner that answers every fixture with one fixed response."""

    def __init__(self, response: str, *, model: str = parity.DEFAULT_MODEL) -> None:
        self.response = response
        self.model = model
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        args = [str(value) for value in argv]
        self.calls.append(args)
        executable = Path(args[0]).name.lower()
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, f"{executable} test-version\n", "")
        if args[1:4] == ["instruction", "list", "--json"]:
            return subprocess.CompletedProcess(
                args, 0, json.dumps(_copilot_instruction_listing(Path(kwargs["cwd"]))), ""
            )
        if executable.startswith("claude"):
            output = [
                {"type": "system", "subtype": "init", "model": self.model},
                {"type": "result", "subtype": "success", "result": self.response},
            ]
        else:
            output = [
                {
                    "type": "assistant.message",
                    "data": {"content": self.response, "model": self.model},
                }
            ]
        return subprocess.CompletedProcess(
            args, 0, "\n".join(json.dumps(event) for event in output) + "\n", ""
        )


def corpus_with_instructions(
    tmp_path: Path,
    *,
    instructions: list[str] | None = None,
    default_instructions: bool = True,
    semantic: bool = False,
    path_local: list[str] | None = None,
    cwd: str | None = None,
) -> Path:
    source = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixture = dict(source["fixtures"][0])  # "resume-phase-3"
    if instructions is None and default_instructions:
        instructions = [".claude/rules/voice.md"]
    if instructions is not None:
        fixture["instructions"] = list(instructions)
    if path_local is not None:
        fixture["path_local"] = list(path_local)
    if cwd is not None:
        fixture["cwd"] = cwd
    if semantic:
        fixture["assertions"] = [
            *fixture["assertions"],
            {"kind": "semantic", "rubric": "FAIL on any continuation offer; PASS otherwise."},
        ]
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps({"schema_version": 1, "fixtures": [fixture]}), encoding="utf-8")
    return path
