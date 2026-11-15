"""Static checks for the scripts and evals rules in the conformance catalog.

These read the skill's scripts and evals files. They never run them.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from _conformance_checks import _FENCE_RE, NotApplicableError, body_or_skip
from _conformance_parse import SkillDoc

_RUNNER_RE = re.compile(
    r"(?:^|[\s;&|(])(uvx|npx|bunx|pipx\s+run|deno\s+run|go\s+run)\s+([^\n;&|]*)"
)
_SCRIPT_SUFFIXES = {".py", ".sh", ".bash", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".ps1"}


# Scripts guide --------------------------------------------------------------


def _has_main_guard(path: Path) -> bool:
    """True when a Python file has a top-level `if __name__ == "__main__":` block."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return True
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            names = [node.test.left, *node.test.comparators]
            if any(isinstance(n, ast.Name) and n.id == "__name__" for n in names):
                return True
    return False


def entry_scripts(doc: SkillDoc) -> list[Path]:
    """Return the entry scripts directly in the skill's scripts directory.

    A Python file is an entry script only when it has a `__main__` guard; a
    module that other scripts import is not. Names starting with `_`, `.`, or
    `test_` are skipped.
    """
    root = doc.directory / "scripts"
    if not root.is_dir():
        raise NotApplicableError("no scripts directory")
    found = [
        path
        for path in sorted(root.iterdir())
        if path.is_file()
        and path.suffix.lower() in _SCRIPT_SUFFIXES
        and not path.name.startswith(("_", ".", "test_"))
        and (path.suffix != ".py" or _has_main_guard(path))
    ]
    if not found:
        raise NotApplicableError("no entry scripts")
    return found


def scripts_listed(doc: SkillDoc) -> list[str]:
    scripts = entry_scripts(doc)
    body = body_or_skip(doc)
    return [
        f"{path.name} (scripts directory) is not named in SKILL.md"
        for path in scripts
        if path.name not in body
    ]


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _python_prompt_lines(source: str) -> list[int] | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if name in ("input", "getpass"):
                lines.append(node.lineno)
    return lines


def scripts_no_prompts(doc: SkillDoc) -> list[str]:
    problems = []
    for path in entry_scripts(doc):
        source = _read(path)
        if source is None:
            problems.append(f"{path.name}: cannot read as UTF-8")
            continue
        if path.suffix == ".py":
            lines = _python_prompt_lines(source)
            if lines is None:
                problems.append(f"{path.name}: does not parse as Python")
                continue
        else:
            pattern = re.compile(
                r"\bread\s+(?:-\w+\s+)*-p\b|</dev/tty|\breadline\.question\(|\bprompt\("
            )
            lines = [n for n, line in enumerate(source.splitlines(), 1) if pattern.search(line)]
        problems.extend(f"{path.name}:{n} reads interactive input" for n in lines)
    return problems


def scripts_help(doc: SkillDoc) -> list[str]:
    problems = []
    for path in entry_scripts(doc):
        source = _read(path) or ""
        handled = (
            "--help" in source or "argparse" in source or re.search(r"@click\.|typer\.", source)
        )
        if path.suffix != ".py":
            handled = handled or re.search(r"(?:^|\s)-h[)|]", source)
        if not handled:
            problems.append(f"{path.name}: no --help handling found")
    return problems


def _code_blocks(markdown: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    fence = ""
    for line in markdown.split("\n"):
        match = _FENCE_RE.match(line)
        if current is None and match:
            fence = match.group(2)
            current = []
        elif (
            current is not None
            and match
            and match.group(2).startswith(fence)
            and not match.group(3).strip()
        ):
            blocks.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(line)
    return blocks


def _pinned(runner: str, args: str) -> bool:
    tokens = args.split()
    if runner == "uvx" and "--from" in tokens:
        index = tokens.index("--from")
        spec = tokens[index + 1] if index + 1 < len(tokens) else ""
        return "==" in spec or "@" in spec
    package = next((token for token in tokens if not token.startswith("-")), "")
    return "@" in package[1:] or "==" in package


def scripts_pinned_one_off(doc: SkillDoc) -> list[str]:
    problems = []
    for block in _code_blocks(body_or_skip(doc)):
        for match in _RUNNER_RE.finditer(block):
            runner = " ".join(match.group(1).split())
            if not _pinned(runner, match.group(2)):
                problems.append(f"unpinned one-off command: {runner} {match.group(2).strip()}")
    return problems


# Evaluating skills guide ----------------------------------------------------


def _eval_case_problems(directory: Path, where: str, case: object) -> list[str]:
    """Return the shape problems in one evals[] entry."""
    if not isinstance(case, dict):
        return [f"{where} must be an object"]
    problems = [] if "id" in case else [f"{where} has no id"]
    for key in ("prompt", "expected_output"):
        if not isinstance(case.get(key), str) or not case[key].strip():
            problems.append(f"{where}.{key} must be a non-empty string")
    files = case.get("files", [])
    if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
        problems.append(f"{where}.files must be a list of paths")
    else:
        missing = [item for item in files if not (directory / item).exists()]
        problems.extend(f"{where}.files: {item} does not exist" for item in missing)
    assertions = case.get("assertions", [])
    if not isinstance(assertions, list) or not all(
        isinstance(a, str) and a.strip() for a in assertions
    ):
        problems.append(f"{where}.assertions must be a list of non-empty strings")
    return problems


def _load_evals(doc: SkillDoc) -> dict[str, object]:
    path = doc.directory / "evals" / "evals.json"
    if not path.is_file():
        raise NotApplicableError("no evals/evals.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise _EvalsFileError(f"evals/evals.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise _EvalsFileError("evals/evals.json must be a JSON object")
    return data


class _EvalsFileError(Exception):
    pass


def evals_file_shape(doc: SkillDoc) -> list[str]:
    try:
        data = _load_evals(doc)
    except _EvalsFileError as exc:
        return [str(exc)]
    problems = []
    name = (doc.fields or {}).get("name")
    skill_name = data.get("skill_name")
    if not isinstance(skill_name, str):
        problems.append("skill_name must be a string")
    elif isinstance(name, str) and skill_name != str(name):
        problems.append(f"skill_name {skill_name!r} does not match name {str(name)!r}")
    cases = data.get("evals")
    if not isinstance(cases, list) or not cases:
        return [*problems, "evals must be a non-empty list"]
    for index, case in enumerate(cases):
        problems.extend(_eval_case_problems(doc.directory, f"evals[{index}]", case))
    return problems
