"""Static checks for the scripts and evals rules, and judgment checking, for conformance.

These read the skill's scripts, evals, and text files. They never run them, and
they call no model.
"""

from __future__ import annotations

import ast
import json
import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _conformance_checks import (
    _FENCE_RE,
    NotApplicableError,
    NotEvaluatedError,
    body_or_skip,
)
from _conformance_parse import SkillDoc, contained, file_id, inside_skill

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
        # An empty neighbor is a text boundary; `"" in "_.-"` is True, so test it first.
        before_ok = not before or not (before.isalnum() or before in "_.-")
        after_ok = not after or not (after.isalnum() or after in "_-")
        if before_ok and after_ok:
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


# Judging the guideline rules --------------------------------------------------
# conformance.py prints the rules no check decides, an agent judges them, and
# these functions accept a verdict only when its quotes appear in the skill.

VERDICT_STATUS = {"pass": "JUDGED_PASS", "fail": "JUDGED_FAIL", "unknown": "JUDGED_UNKNOWN"}
MIN_QUOTE_CHARS = 12
# Every script type the static checks recognize, plus prose and data files.
TEXT_SUFFIXES = frozenset(_SCRIPT_SUFFIXES | {".md", ".json", ".yaml", ".yml", ".txt"})
JUDGE_INSTRUCTIONS = (
    "Judge each rule from the files listed, and nothing else. Run in a fresh "
    "context with only this packet and the skill directory, not the session "
    "that wrote the skill. For each rule write verdict pass, fail, or unknown, "
    "and a one-sentence reason. A pass or fail cites at least one quote copied "
    f"verbatim from a listed file, at least {MIN_QUOTE_CHARS} characters long "
    "after whitespace runs collapse to one space. Answer unknown when the files "
    "cannot show it, such as how the skill was tested; unknown is never a pass. "
    "Write the judgments file outside the skill directory."
)


@dataclass(frozen=True)
class JudgingScope:
    """What a judgments file may name: the skill's files, its open rules, and waivers."""

    directory: Path
    root: Path
    allowed: frozenset[str]
    open_ids: frozenset[str]
    waived: frozenset[str]
    excluded: tuple[int, int] | None = None


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _read_inside(path: Path, scope: JudgingScope) -> str | None:
    """Read a file only if the file opened is the one inside the skill and root.

    Open first, then check: the path must resolve inside both boundaries now,
    and reach the same file (device and inode) as the open descriptor. A swap
    before or after the open fails one of the two checks. None means reject.
    """
    with open(path, "rb") as handle:
        opened = os.fstat(handle.fileno())
        identity = (opened.st_dev, opened.st_ino)
        if identity == scope.excluded or file_id(path) != identity:
            return None
        if not inside_skill(path, scope.directory, scope.root):
            return None
        return handle.read().decode("utf-8", errors="replace")


def _evidence_item_error(at: str, item: object, scope: JudgingScope) -> str | None:
    """Return why one evidence item fails, or None when its quote is in the named file."""
    if not isinstance(item, dict):
        return f"{at}: must be an object"
    file, quote = item.get("file"), item.get("quote")
    if not isinstance(file, str) or not isinstance(quote, str):
        return f"{at}: file and quote must both be strings"
    if len(_collapse(quote)) < MIN_QUOTE_CHARS:
        return f"{at}: quote needs at least {MIN_QUOTE_CHARS} characters"
    if file not in scope.allowed:
        return f"{at}: {file} is not a text file in the skill"
    try:
        text = _read_inside(scope.directory / file, scope)
    except OSError as exc:
        return f"{at}: cannot read {file}: {exc}"
    if text is None:
        return f"{at}: {file} is not a text file in the skill"
    if _collapse(quote) not in _collapse(text):
        return f"{at}: quote not found verbatim in {file}"
    return None


def _evidence_errors(where: str, evidence: object, scope: JudgingScope) -> list[str]:
    if not isinstance(evidence, list):
        return [f"{where}: evidence must be a list"]
    errors = (
        _evidence_item_error(f"{where}.evidence[{index}]", item, scope)
        for index, item in enumerate(evidence)
    )
    return [error for error in errors if error is not None]


def _judgment_errors(item: object, index: int, scope: JudgingScope) -> list[str]:
    where = f"judgments[{index}]"
    if not isinstance(item, dict):
        return [f"{where}: must be an object"]
    rule_id, verdict = item.get("id"), item.get("verdict")
    if not isinstance(rule_id, str) or rule_id not in scope.open_ids:
        return [f"{where}: {rule_id!r} is not an unjudged guideline rule for this skill"]
    if not isinstance(verdict, str) or verdict not in VERDICT_STATUS:
        return [f"{where}: verdict must be pass, fail, or unknown"]
    errors = []
    if not isinstance(item.get("reason"), str) or not item["reason"].strip():
        errors.append(f"{where}: reason must be a non-empty string")
    evidence = item.get("evidence", [])
    if verdict != "unknown" and not evidence:
        errors.append(f"{where}: a {verdict} verdict needs at least one quote")
    return errors + _evidence_errors(where, evidence, scope)


def _read_judgments(raw: bytes) -> list[object] | str:
    """Return the judgments list from the file's bytes, or why it cannot be parsed."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return f"the judgments file is not valid UTF-8 JSON: {exc}"
    items = data.get("judgments") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return "the file needs a top-level 'judgments' list"
    return items


def apply_judgments(results: list[Any], raw: bytes, scope: JudgingScope) -> list[str]:
    """Apply a judgments file's bytes to the MANUAL results, or return why it was rejected.

    Every verdict is checked before any result changes, so a rejected file
    leaves the report as it was.
    """
    items = _read_judgments(raw)
    if isinstance(items, str):
        return [items]
    ids = [item.get("id") for item in items if isinstance(item, dict)]
    string_ids = [i for i in ids if isinstance(i, str)]
    errors = [
        f"{i!r} is judged more than once"
        for i in sorted(set(string_ids))
        if string_ids.count(i) > 1
    ]
    for index, item in enumerate(items):
        errors.extend(_judgment_errors(item, index, scope))
    if errors:
        return errors
    verdicts = {item["id"]: item for item in items if isinstance(item, dict)}
    for result in results:
        item = verdicts.get(result.rule.id)
        if item is None:
            continue
        result.status = VERDICT_STATUS[item["verdict"]]
        result.reason = item["reason"].strip()
        result.problems = [
            f'"{_collapse(e["quote"])}" ({e["file"]})' for e in item.get("evidence", [])
        ]
        if result.status == "JUDGED_FAIL" and result.rule.id in scope.waived:
            result.status = "WAIVED"
            result.reason = f"waived with --waive; judged fail: {result.reason}"
    return []
