"""Static checks for the scripts and evals rules in the conformance catalog.

These read the skill's scripts and evals files. They never run them.
"""

from __future__ import annotations

import ast
import json
import posixpath
import re
from pathlib import Path

from _conformance_checks import (
    _FENCE_RE,
    NotApplicableError,
    NotEvaluatedError,
    body_or_skip,
)
from _conformance_parse import SkillDoc, contained

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
    return any(_is_main_test(node.test) for node in tree.body if isinstance(node, ast.If))


def _is_main_test(test: ast.expr) -> bool:
    """True only for `__name__ == "__main__"`, in either order."""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    sides = [test.left, test.comparators[0]]
    has_name = any(isinstance(n, ast.Name) and n.id == "__name__" for n in sides)
    has_main = any(isinstance(n, ast.Constant) and n.value == "__main__" for n in sides)
    return has_name and has_main


def entry_scripts(doc: SkillDoc) -> list[Path]:
    """Return the entry scripts directly in the skill's scripts directory.

    A Python file is an entry script only when it has a `__main__` guard; a
    module that other scripts import is not. Names starting with `_`, `.`, or
    `test_` are skipped.
    """
    scripts_dir = doc.directory / "scripts"
    if not scripts_dir.is_dir():
        raise NotApplicableError("no scripts directory")
    if not contained(doc, scripts_dir):
        raise NotEvaluatedError("the scripts directory resolves outside the root; not read")
    candidates = [
        path
        for path in sorted(scripts_dir.iterdir())
        if path.is_file()
        and path.suffix.lower() in _SCRIPT_SUFFIXES
        and not path.name.startswith(("_", ".", "test_"))
    ]
    for path in candidates:
        note = f"skipped {path.name}: it resolves outside the root"
        if not contained(doc, path) and note not in doc.notes:
            doc.notes.append(note)
    found = [
        path
        for path in candidates
        if contained(doc, path) and (path.suffix != ".py" or _has_main_guard(path))
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
        if not _names_file(body, path.name)
    ]


def _names_file(text: str, name: str) -> bool:
    """True when name appears as a whole file name, not inside a longer one.

    `run.py` matches `scripts/run.py` and `run.py.` but not `overrun.py` or
    `run.pyc`.
    """
    start = text.find(name)
    while start != -1:
        before = text[start - 1] if start else ""
        end = start + len(name)
        after = text[end] if end < len(text) else ""
        if not (before.isalnum() or before in "_.-") and not (after.isalnum() or after in "_-"):
            return True
        start = text.find(name, start + 1)
    return False


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


_EXIT_DOC_RE = re.compile(r"exit[ _-]?codes?\b", re.IGNORECASE)


def scripts_exit_codes_documented(doc: SkillDoc) -> list[str]:
    """Each entry script names its exit codes, where --help or its header shows them."""
    problems = []
    for path in entry_scripts(doc):
        source = _read(path) or ""
        if not _EXIT_DOC_RE.search(source):
            problems.append(f"{path.name}: no exit code documentation found")
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


def _spec_pinned(spec: str) -> bool:
    """True when a package spec names a version: name@1, @scope/name@1, name==1."""
    spec = re.sub(r"^(npm|jsr):", "", spec)
    name = spec[1:] if spec.startswith("@") else spec
    return "@" in name or "==" in name


def _pinned(runner: str, args: str) -> bool:
    """True when the command pins its package, or runs a local file instead of one."""
    tokens = args.split()
    for index, token in enumerate(tokens):
        for flag in ("--from", "--spec"):
            if token == flag:
                return _spec_pinned(tokens[index + 1] if index + 1 < len(tokens) else "")
            if token.startswith(flag + "="):
                return _spec_pinned(token.split("=", 1)[1])
    package = next((token for token in tokens if not token.startswith("-")), "")
    if not package or package.startswith((".", "/", "~", "$")):
        return True
    if runner == "deno run" and not package.startswith(("npm:", "jsr:")):
        return True
    return _spec_pinned(package)


def scripts_pinned_one_off(doc: SkillDoc) -> list[str]:
    problems = []
    for block in _code_blocks(body_or_skip(doc)):
        for match in _RUNNER_RE.finditer(block):
            runner = " ".join(match.group(1).split())
            if not _pinned(runner, match.group(2)):
                problems.append(f"unpinned one-off command: {runner} {match.group(2).strip()}")
    return problems


# Evaluating skills guide ----------------------------------------------------


def _eval_case_problems(doc: SkillDoc, where: str, case: object) -> list[str]:
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
        for item in files:
            normalized = posixpath.normpath(item)
            if posixpath.isabs(item) or normalized == ".." or normalized.startswith("../"):
                problems.append(f"{where}.files: {item} leaves the skill directory")
            elif not contained(doc, doc.directory / normalized):
                problems.append(f"{where}.files: {item} resolves outside the root")
            elif not (doc.directory / normalized).exists():
                problems.append(f"{where}.files: {item} does not exist")
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
    if not contained(doc, path):
        raise NotEvaluatedError("evals/evals.json resolves outside the root; not read")
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
        problems.extend(_eval_case_problems(doc, f"evals[{index}]", case))
    return problems
