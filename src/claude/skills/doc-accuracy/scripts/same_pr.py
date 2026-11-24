# taste-lint: ignore file-size -- one module because the Hermes delivery pack is at its file cap
"""Same-PR doc accuracy: catch prose that drifts from code changed in the same diff.

Activated by `doc_accuracy.py --same-pr --diff-base REF`. It reads the changed
hunks of every text file in the diff, not only documentation globs, and sorts
each changed line into prose (Markdown and `.tmpl` lines, Python docstrings and
comments, JSON and YAML string values) or code (with its enclosing symbol).

Deterministic rules emit findings: R1 exit-code sets, R2 enumeration subsets,
R3 JSON key contents, and R4 literal collection counts. Every other changed prose
line that looks like a verifiable claim goes to the checklist with the code
locations it was paired with, for the Phase 4 reviewer. Nothing that looks
checkable is dropped silently.

Artifacts: `same-pr-findings.json` and
`same-pr-checklist.json`.

Exit codes belong to `doc_accuracy.py`: 0 no finding at or above the threshold,
10 a finding at or above it, 2 `--same-pr` without `--diff-base`, 3 git failed.

Layout: line classification and the code index, then rules R1 to R3, then the
scan driver. One module on purpose: the Hermes `project-toolkit-delivery` pack
is capped at 400 files (`templates/platforms/hermes.yaml`), so a second and
third sibling module would not fit.
"""

from __future__ import annotations

import ast
import io
import json
import re
import tokenize
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

# ===== line classification and code index =====


PROSE_SUFFIXES = {".md", ".tmpl", ".mdx"}
DATA_SUFFIXES = {".json", ".yaml", ".yml"}
CODE_SUFFIXES = {".py", ".cs", ".ts", ".tsx", ".js", ".ps1", ".sh"}
MODULE_SYMBOL = "<module>"
_FENCE = re.compile(r"^\s*(```|~~~)")
_JSON_VALUE = re.compile(r'^\s*"[^"]+"\s*:\s*(".*")\s*,?\s*$')
_YAML_VALUE = re.compile(r"^\s*(?:-\s+)?[\w.-]+:\s+[\"']?(.+?)[\"']?\s*$")
_MIN_DATA_WORDS = 4


@dataclass(frozen=True)
class ProseLine:
    file: str
    line: int
    text: str


@dataclass(frozen=True)
class CodeRegion:
    """The changed lines of one symbol: ``line`` is the first changed line."""

    file: str
    line: int
    symbol: str


def changed_line_numbers(ranges: list[list[int]] | None, total: int) -> set[int]:
    """Expand inclusive ``[start, end]`` ranges; ``None`` means every line changed."""
    if ranges is None:
        return set(range(1, total + 1))
    return {n for start, end in ranges for n in range(start, min(end, total) + 1)}


def _markdown_prose(rel: str, lines: list[str], changed: set[int]) -> list[ProseLine]:
    found: list[ProseLine] = []
    fenced = False
    for number, line in enumerate(lines, start=1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if number in changed and not fenced and line.strip():
            found.append(ProseLine(rel, number, line.strip()))
    return found


def _data_prose(rel: str, lines: list[str], changed: set[int]) -> list[ProseLine]:
    pattern = _JSON_VALUE if rel.endswith(".json") else _YAML_VALUE
    found: list[ProseLine] = []
    for number in sorted(changed):
        match = pattern.match(lines[number - 1])
        if not match:
            continue
        value = match.group(1)
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        if isinstance(value, str) and len(value.split()) >= _MIN_DATA_WORDS:
            found.append(ProseLine(rel, number, value))
    return found


def _docstring_spans(tree: ast.AST) -> list[tuple[int, int]]:
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str) and first.end_lineno:
                spans.append((first.lineno, first.end_lineno))
    return spans


def _comment_lines(source: str) -> dict[int, str]:
    comments: dict[int, str] = {}
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                comments[token.start[0]] = token.string.lstrip("#").strip()
    except (tokenize.TokenError, IndentationError):
        return comments
    return comments


def _symbol_spans(tree: ast.AST) -> list[tuple[int, int, str]]:
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            spans.append((node.lineno, node.end_lineno or node.lineno, node.name))
    return spans


def _innermost(spans: list[tuple[int, int, str]], line: int) -> str:
    inside = [s for s in spans if s[0] <= line <= s[1]]
    return min(inside, key=lambda s: s[1] - s[0])[2] if inside else MODULE_SYMBOL


def _python_split(
    rel: str, source: str, changed: set[int]
) -> tuple[list[ProseLine], list[CodeRegion], int]:
    lines = source.split("\n")
    doc_spans: list[tuple[int, int]] = []
    spans: list[tuple[int, int, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        pass  # Unparseable source: every changed line stays code with no symbol.
    else:
        doc_spans, spans = _docstring_spans(tree), _symbol_spans(tree)
    comments = _comment_lines(source)
    prose: list[ProseLine] = []
    first_line: dict[str, int] = {}
    code_lines = 0
    for number in sorted(changed):
        text = lines[number - 1].strip()
        if any(start <= number <= end for start, end in doc_spans):
            if text.strip("\"'"):
                prose.append(ProseLine(rel, number, text))
            continue
        if number in comments and comments[number]:
            prose.append(ProseLine(rel, number, comments[number]))
        if text and not text.startswith("#"):
            code_lines += 1
            first_line.setdefault(_innermost(spans, number), number)
    regions = [CodeRegion(rel, line, name) for name, line in first_line.items()]
    return prose, sorted(regions, key=lambda r: r.line), code_lines


def classify_file(
    rel: str, source: str, ranges: list[list[int]] | None
) -> tuple[list[ProseLine], list[CodeRegion], int]:
    """Split one file's changed lines into prose, code regions, and a code-line count."""
    lines = source.split("\n")
    changed = changed_line_numbers(ranges, len(lines))
    suffix = "." + rel.rsplit(".", 1)[-1] if "." in rel else ""
    if suffix in PROSE_SUFFIXES:
        return _markdown_prose(rel, lines, changed), [], 0
    if suffix in DATA_SUFFIXES:
        return _data_prose(rel, lines, changed), [], 0
    if suffix == ".py":
        return _python_split(rel, source, changed)
    if suffix in CODE_SUFFIXES:
        body = [n for n in sorted(changed) if lines[n - 1].strip()]
        regions = [CodeRegion(rel, body[0], MODULE_SYMBOL)] if body else []
        return [], regions, len(body)
    return [], [], 0


# -- code index ---------------------------------------------------------------


def _identifiers(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _function_returns(node: ast.AST) -> list[ast.Return]:
    """Returns in this function. Nested functions, classes, and lambdas are skipped."""
    found: list[ast.Return] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef):
            continue
        if isinstance(child, ast.Return):
            found.append(child)
            continue
        found.extend(_function_returns(child))
    return found


def _is_exit_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "exit"
    return isinstance(func, ast.Attribute) and func.attr == "exit"


class CodeIndex:
    """Lazy AST facts about the changed Python files, keyed by repo-relative path."""

    _MAIN_NAMES = {"main", "_main", "cli", "run_cli"}

    def __init__(self, sources: dict[str, str]) -> None:
        self.sources = {k: v for k, v in sources.items() if k.endswith(".py")}
        self._trees: dict[str, ast.AST | None] = {}
        self.memo: dict[str, Any] = {}

    def tree(self, rel: str) -> ast.AST | None:
        if rel not in self._trees:
            try:
                self._trees[rel] = ast.parse(self.sources[rel])
            except SyntaxError:
                self._trees[rel] = None
        return self._trees[rel]

    def exit_literals(self, rel: str) -> dict[int, int]:
        """Map each literal exit integer to its first line.

        Counts ``sys.exit(N)``, ``exit(N)``, and ``return N`` inside ``main``-like
        functions only. A ``return`` in a nested function is not a process exit.
        """
        tree = self.tree(rel)
        found: dict[int, int] = {}
        if tree is None:
            return found
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_exit_call(node) and node.args:
                self._take(found, node.args[0], node.lineno)
            if isinstance(node, ast.FunctionDef) and node.name in self._MAIN_NAMES:
                for ret in _function_returns(node):
                    if ret.value is not None:
                        self._take(found, ret.value, ret.lineno)
        return found

    @staticmethod
    def _take(found: dict[int, int], value: ast.AST, line: int) -> None:
        if isinstance(value, ast.Constant) and type(value.value) is int:
            found.setdefault(value.value, line)

    def _all_assignments(self) -> dict[str, list[tuple[str, int, set[str]]]]:
        cached = self.memo.get("assignments_by_key")
        if cached is not None:
            return cast(dict[str, list[tuple[str, int, set[str]]]], cached)
        by_key: dict[str, list[tuple[str, int, set[str]]]] = {}
        for rel in self.sources:
            tree = self.tree(rel)
            if tree is None:
                continue
            for node in ast.walk(tree):
                line = getattr(node, "lineno", 1)
                for key, value in _all_writes(node):
                    by_key.setdefault(key, []).append((rel, line, _identifiers(value)))
        self.memo["assignments_by_key"] = by_key
        return by_key

    def assignments(self, key: str) -> list[tuple[str, int, set[str]]]:
        """Return (file, line, identifiers on the right) for each write to ``key``."""
        return list(self._all_assignments().get(key, ()))


def _target_key(target: ast.AST) -> str | None:
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Subscript):
        return const_str(target.slice)
    return None


def _all_writes(node: ast.AST) -> list[tuple[str, ast.AST]]:
    """Return (key, value) pairs that ``node`` assigns to an attribute, item, or keyword."""
    if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        keys = dict.fromkeys(k for t in targets if (k := _target_key(t)) is not None)
        return [(key, node.value) for key in keys]
    if isinstance(node, ast.Call):
        return [(kw.arg, kw.value) for kw in node.keywords if kw.arg is not None]
    if isinstance(node, ast.Dict):
        return [
            (key, v)
            for k, v in zip(node.keys, node.values, strict=True)
            if (key := const_str(k)) is not None
        ]
    return []


def const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


# ===== rules R1 to R3 =====


_EXIT_HEADING = re.compile(r"^#{1,6}\s+.*exit\s+codes?", re.IGNORECASE)
_TABLE_ROW = re.compile(r"^\s*\|\s*(\d+)\s*\|")
_DOC_BLOCK = re.compile(r"^\s*Exit\s+Codes?:\s*$", re.IGNORECASE)
_DOC_ITEM = re.compile(r"^\s+(\d+)\s*[:=-]")
_SCRIPT_MENTION = re.compile(r"[\w./-]+\.py\b")


def make_finding(
    rule: str,
    severity: str,
    prose: ProseLine,
    code: tuple[str, int, str],
    evidence: Mapping[str, object],
    message: str,
) -> dict[str, object]:
    return {
        "rule": rule,
        "severity": severity,
        "prose": {"file": prose.file, "line": prose.line, "text": prose.text},
        "code": {"file": code[0], "line": code[1], "symbol": code[2]},
        "evidence": evidence,
        "message": message,
    }


# -- R1 -----------------------------------------------------------------------

Block = tuple[set[int], set[int]]  # documented codes, line numbers the block spans


def _markdown_blocks(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    for start, line in enumerate(lines):
        if not _EXIT_HEADING.match(line):
            continue
        end = start + 1
        while end < len(lines) and not lines[end].lstrip().startswith(("|", "#")):
            end += 1
        codes: set[int] = set()
        spanned: set[int] = set()
        while end < len(lines) and lines[end].lstrip().startswith("|"):
            spanned.add(end + 1)
            row = _TABLE_ROW.match(lines[end])
            if row:
                codes.add(int(row.group(1)))
            end += 1
        if codes:
            blocks.append((codes, spanned))
    return blocks


def _docstring_blocks(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    for start, line in enumerate(lines):
        if not _DOC_BLOCK.match(line):
            continue
        codes: set[int] = set()
        spanned = {start + 1}
        end = start + 1
        while end < len(lines) and lines[end].strip():
            spanned.add(end + 1)
            item = _DOC_ITEM.match(lines[end])
            if item:
                codes.add(int(item.group(1)))
            end += 1
        if codes:
            blocks.append((codes, spanned))
    return blocks


def _identify_script(text: str, changed_py: Iterable[str], index: CodeIndex) -> str | None:
    """Return a changed script that the doc names by path and that exits with literals."""
    for mention in _SCRIPT_MENTION.findall(text):
        wanted = mention.lstrip("./")
        for path in changed_py:
            if (path == wanted or path.endswith("/" + wanted)) and index.exit_literals(path):
                return path
    return None


def check_exit_codes(
    rel: str, text: str, changed_prose: set[int], index: CodeIndex
) -> list[dict[str, object]]:
    """R1: a touched Exit Codes block whose code set differs from the script's literals."""
    lines = text.split("\n")
    is_py = rel.endswith(".py")
    blocks = _docstring_blocks(lines) if is_py else _markdown_blocks(lines)
    found = []
    for codes, spanned in blocks:
        touched = spanned & changed_prose
        script = rel if is_py else _identify_script(text, index.sources, index)
        literals = index.exit_literals(script) if script in index.sources else {}
        if not touched or not literals:
            continue
        doc_only, code_only = sorted(codes - set(literals)), sorted(set(literals) - codes)
        # Dynamic return expressions can supply documented exits. Absence from
        # this literal index does not prove those exits impossible.
        if not code_only:
            continue
        line = min(touched)
        evidence = {"documented": sorted(codes), "doc_only": doc_only, "code_only": code_only}
        where = literals[code_only[0]] if code_only else min(literals.values())
        found.append(
            make_finding(
                "R1",
                "high" if code_only else "medium",
                ProseLine(rel, line, lines[line - 1].strip()),
                (str(script), where, "exit codes"),
                evidence,
                f"Documented exit codes {sorted(codes)} differ from literal exits "
                f"{sorted(literals)} in {script}",
            )
        )
    return found


# -- R2 -----------------------------------------------------------------------

_ENUM_KEYWORDS = ("language_name", "error")
_STOP = {"the", "and", "for", "with", "that", "this", "from", "are", "not", "its", "has", "can"}
Site = tuple[str, int, set[str]]  # function name, raise line, stems of its message


def _stems(text: str) -> set[str]:
    return {w.lower()[:4] for w in re.findall(r"[A-Za-z]{3,}", text)} - _STOP


def _enum_sets(tree: ast.AST) -> list[set[str]]:
    """Closed sets: values passed for the same record keyword across the file."""
    sets: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            member = kw.value.id if isinstance(kw.value, ast.Name) else const_str(kw.value)
            if kw.arg in _ENUM_KEYWORDS and member:
                sets.setdefault(kw.arg, set()).add(member)
    return [members for members in sets.values() if len(members) >= 2]


def _shared_sites(tree: ast.AST) -> list[Site]:
    """Raises inside a function parameterized by the record, as ``raise record.error(...)``."""
    sites: list[Site] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        params = {a.arg for a in [*fn.args.args, *fn.args.kwonlyargs]}
        for node in ast.walk(fn):
            if not isinstance(node, ast.Raise):
                continue
            call = node.exc
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                continue
            owner = call.func.value
            if not (isinstance(owner, ast.Name) and owner.id in params):
                continue
            if call.func.attr not in _ENUM_KEYWORDS:
                continue
            words = " ".join(_string_parts(call))
            if _stems(words):
                sites.append((fn.name, node.lineno, _stems(words)))
    return sites


def _string_parts(call: ast.Call) -> list[str]:
    return [
        c.value for c in ast.walk(call) if isinstance(c, ast.Constant) and isinstance(c.value, str)
    ]


def _member_runs(text: str, members: set[str]) -> list[tuple[int, int, list[str]]]:
    alt = "|".join(re.escape(m) for m in sorted(members, key=len, reverse=True))
    name = rf"(?<![\w#])(?:{alt})(?![\w#])"
    joiner = r"(?:,\s*(?:or|and)\s+|,\s+|\s+(?:or|and)\s+)"
    run = re.compile(rf"{name}(?:{joiner}{name})*")
    return [(m.start(), m.end(), re.findall(name, m.group(0))) for m in run.finditer(text)]


def _clause_for(text: str, runs: list[tuple[int, int, list[str]]], target: int) -> str:
    """The comma-delimited clause around run ``target``, with every run masked."""
    masked = text
    for i in range(len(runs) - 1, -1, -1):
        start, end, _ = runs[i]
        masked = masked[:start] + f"\x00{i}\x00" + masked[end:]
    for segment in re.split(r"[,;()]", masked):
        if f"\x00{target}\x00" in segment:
            return re.sub(r"\x00\d+\x00", " ", segment).strip()
    return ""


def _enum_facts(index: CodeIndex, path: str) -> tuple[list[set[str]], list[Site]]:
    """Closed sets and shared raise sites of one file, computed once per index."""
    if path not in index.memo:
        tree = index.tree(path)
        sites = _shared_sites(tree) if tree else []
        sets = _enum_sets(tree) if tree and sites else []
        index.memo[path] = (sets, sites)
    facts: tuple[list[set[str]], list[Site]] = index.memo[path]
    return facts


def check_enumeration_subset(
    prose: ProseLine, index: CodeIndex, code_order: list[str]
) -> list[dict[str, object]]:
    """R2: a clause names two or more, but not all, members of a closed set."""
    text = prose.text.replace("`", "")
    found: list[dict[str, object]] = []
    for path in code_order:
        sets, sites = _enum_facts(index, path)
        for members in sets:
            runs = _member_runs(text, members)
            for i, (_, _, named) in enumerate(runs):
                found += _subset_finding(
                    prose, path, members, named, _clause_for(text, runs, i), sites
                )
        if found:
            break
    return found


def _subset_finding(
    prose: ProseLine,
    path: str,
    members: set[str],
    named: list[str],
    clause: str,
    sites: list[Site],
) -> list[dict[str, object]]:
    named_members = set(named)
    if len(named_members) < 2 or named_members >= members:
        return []
    scored = sorted(((len(_stems(clause) & site[2]), site) for site in sites), key=lambda s: -s[0])
    best = scored[0] if scored else (0, ("", 0, set()))
    if best[0] < 2 or (len(scored) > 1 and scored[1][0] == best[0]):
        return []
    function, line, _ = best[1]
    missing = sorted(members - named_members)
    evidence = {"named": named, "missing": missing, "clause": clause, "raise_in": function}
    return [
        make_finding(
            "R2",
            "high",
            prose,
            (path, line, function),
            evidence,
            f"Clause names {named} but {function} raises this cause for every member; "
            f"{missing} also applies",
        )
    ]


def literal_collections(index: CodeIndex) -> list[tuple[str, int, str, list[ast.expr]]]:
    """Return named, literal collections without evaluating target code."""
    if "literal_collections" in index.memo:
        return cast(list[tuple[str, int, str, list[ast.expr]]], index.memo["literal_collections"])
    collections: list[tuple[str, int, str, list[ast.expr]]] = []
    for path in index.sources:
        tree = index.tree(path)
        for node in ast.walk(tree) if tree else []:
            if not isinstance(node, ast.Assign | ast.AnnAssign):
                continue
            if not isinstance(node.value, ast.Tuple | ast.List | ast.Set):
                continue
            if any(isinstance(e, ast.Starred) for e in node.value.elts):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for name in targets:
                if isinstance(name, ast.Name):
                    collections.append((path, node.lineno, name.id, node.value.elts))
    index.memo["literal_collections"] = collections
    return collections


def _same_script(path: str, mention: str) -> bool:
    """True when ``mention`` names ``path`` by its full path or a trailing part."""
    mention = mention.removeprefix("./")
    return path == mention or path.endswith("/" + mention)


_EXAMPLE_WORD = re.compile(r"\b(?:example|including|such as|e\.g\.)\b", re.I)
_BACKTICK_SPAN = re.compile(r"`([^`]+)`")
_SCOPE_WORD = re.compile(r"scope|root|prefix", re.I)
_COUNT_WORD_VALUES = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _literal_subset_index(
    index: CodeIndex,
) -> tuple[list[tuple[str, int, str, frozenset[str]]], dict[str, list[int]]]:
    cached = index.memo.get("literal_subset_index")
    if cached is not None:
        return cast(
            tuple[list[tuple[str, int, str, frozenset[str]]], dict[str, list[int]]],
            cached,
        )
    entries: list[tuple[str, int, str, frozenset[str]]] = []
    by_member: dict[str, list[int]] = {}
    for path, line, symbol, values in literal_collections(index):
        strings = [const_str(v) for v in values]
        if None in strings or len(strings) < 2:
            continue
        members = frozenset(s.rstrip("/") for s in strings if s is not None)
        entry_id = len(entries)
        entries.append((path, line, symbol, members))
        for member in members:
            by_member.setdefault(member, []).append(entry_id)
    result = (entries, by_member)
    index.memo["literal_subset_index"] = result
    return result


def _literal_count_index(index: CodeIndex) -> dict[str, list[tuple[int, str, int, str, int]]]:
    cached = index.memo.get("literal_count_index")
    if cached is not None:
        return cast(dict[str, list[tuple[int, str, int, str, int]]], cached)
    by_symbol: dict[str, list[tuple[int, str, int, str, int]]] = {}
    for pos, (path, line, symbol, values) in enumerate(literal_collections(index)):
        by_symbol.setdefault(symbol.lower(), []).append((pos, path, line, symbol, len(values)))
    index.memo["literal_count_index"] = by_symbol
    return by_symbol


def check_literal_subset(prose: ProseLine, index: CodeIndex) -> list[dict[str, object]]:
    """R2: a closed path enumeration omits a literal collection member."""
    if "`" not in prose.text or _EXAMPLE_WORD.search(prose.text):
        return []
    named = {s.rstrip("/") for s in _BACKTICK_SPAN.findall(prose.text)}
    if not named:
        return []
    entries, by_member = _literal_subset_index(index)
    candidate_ids = sorted({i for token in named for i in by_member.get(token, ())})
    if not candidate_ids:
        return []
    scripts = _SCRIPT_MENTION.findall(prose.text)
    scoped = bool(_SCOPE_WORD.search(prose.text))
    found = []
    for entry_id in candidate_ids:
        path, line, symbol, members = entries[entry_id]
        overlap = named & members
        # The line must name the collection, by symbol or by its file, or sit
        # in that file. Two shared paths and a scope word alone matched
        # unrelated table rows (issue #7484), because any changed or
        # mentioned script joins the index for every prose line.
        paths = len(overlap) >= 2 and all(f"`{s}/`" in prose.text for s in overlap)
        own_file = prose.file == path or any(_same_script(path, m) for m in scripts)
        explicit = symbol in named and (symbol.isupper() or own_file)
        if not (explicit or paths and own_file and scoped):
            continue
        if overlap and overlap < members:
            found.append(
                make_finding(
                    "R2",
                    "high",
                    prose,
                    (path, line, symbol),
                    {"named": sorted(overlap), "missing": sorted(members - overlap)},
                    f"Enumeration omits {sorted(members - overlap)} from `{symbol}`",
                )
            )
    return found


def _count_beside_symbol(text: str, symbol: str, words: dict[str, int]) -> int | None:
    """Return the count token placed immediately before a backticked symbol."""
    needle = "`" + symbol.lower() + "`"
    folded = text.lower()
    start = 0
    while start < len(folded):
        index = folded.find(needle, start)
        if index < 0:
            return None
        if index == 0 or not text[index - 1].isspace():
            start = index + 1
            continue
        prefix_tokens = text[:index].split()
        if not prefix_tokens:
            start = index + 1
            continue
        token = prefix_tokens[-1].lower()
        if token.isdigit():
            return int(token)
        counted = words.get(token)
        if counted is not None:
            return counted
        start = index + 1
    return None


def check_literal_count(prose: ProseLine, index: CodeIndex) -> list[dict[str, object]]:
    """R4: a count immediately beside a named collection differs from its length."""
    if "`" not in prose.text:
        return []
    by_symbol = _literal_count_index(index)
    matches = [
        entry
        for token in {m.lower() for m in _BACKTICK_SPAN.findall(prose.text)}
        for entry in by_symbol.get(token, ())
    ]
    if not matches:
        return []
    matches.sort(key=lambda item: item[0])
    scripts = _SCRIPT_MENTION.findall(prose.text)
    found = []
    for _pos, path, line, symbol, length in matches:
        if not symbol.isupper() and not (
            length and (path == prose.file or any(_same_script(path, script) for script in scripts))
        ):
            continue
        count = _count_beside_symbol(prose.text, symbol, _COUNT_WORD_VALUES)
        if count is None or count == length:
            continue
        found.append(
            make_finding(
                "R4",
                "high",
                prose,
                (path, line, symbol),
                {"stated": count, "actual": length},
                f"Count {count} differs from {length} entries in `{symbol}`",
            )
        )
    return found


# -- R3 -----------------------------------------------------------------------

_NOUN_UNDER_KEY = re.compile(r"(?P<noun>[A-Za-z][\w-]*)\s+under\s+`(?P<key>[A-Za-z_]\w*)`")
_KEY_HOLDS_NOUN = re.compile(
    r"`(?P<key>[A-Za-z_]\w*)`\s+(?:holds|keeps|records|stores|contains|retains)\s+"
    r"(?:the\s+|a\s+|an\s+)?(?P<noun>[A-Za-z][\w-]*)"
)
# Placeholder names that docs use to describe the pattern itself, not a real JSON key.
_PLACEHOLDER_KEYS = {"key", "field", "name", "value", "k", "x"}
_PRONOUNS = {"it", "them", "this", "that", "these", "those", "all", "everything", "both"}
_NON_NOUNS = {"recorded", "listed", "stored", "written", "retained", "reported"} | {
    "at",
    "are",
    "is",
    "its",
    "only",
}
_JSON_MENTION = re.compile(r"\bjson\b", re.IGNORECASE)


def _stem5(word: str) -> str:
    return word.lower().rstrip("s")[:5]


def _ident_stems(idents: Iterable[str]) -> set[str]:
    tokens = (t for ident in idents for t in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", ident))
    return {_stem5(t) for t in tokens}


def check_json_key(prose: ProseLine, index: CodeIndex) -> tuple[list[dict[str, object]], list[str]]:
    """R3: findings, plus notes for keys the changed code never assigns.

    Stricter than a name match: the noun has to share a five-letter stem with an
    identifier on the assigned right-hand side. An assignment whose right side is
    a bare literal has no identifier and is not judged.
    """
    found: list[dict[str, object]] = []
    notes: list[str] = []
    if not _JSON_MENTION.search(prose.text):
        return found, notes
    scripts = _SCRIPT_MENTION.findall(prose.text)
    pairs = [
        m.groupdict() for p in (_NOUN_UNDER_KEY, _KEY_HOLDS_NOUN) for m in p.finditer(prose.text)
    ]
    for pair in pairs:
        noun, key = pair["noun"], pair["key"]
        if noun.lower() in _PRONOUNS | _NON_NOUNS or key in _PLACEHOLDER_KEYS:
            continue
        writes = [w for w in index.assignments(key) if w[2]]
        bound_writes = [
            write
            for write in writes
            if write[0] == prose.file or any(_same_script(write[0], script) for script in scripts)
        ]
        if bound_writes:
            writes = bound_writes
        elif scripts or len({path for path, _, _ in writes}) > 1:
            notes.append(f"R3: no unique source for `{key}` in changed code")
            continue
        if not writes:
            notes.append(f"R3: no assignment to `{key}` with identifiers in changed code")
            continue
        if any(_stem5(noun) in _ident_stems(idents) for _, _, idents in writes):
            continue
        path, line, idents = writes[0]
        evidence = {"key": key, "noun": noun, "assigned_from": sorted(idents)}
        found.append(
            make_finding(
                "R3",
                "high",
                prose,
                (path, line, key),
                evidence,
                f"`{key}` is assigned from {sorted(idents)}, none of which names {noun!r}",
            )
        )
    return found, notes


# ===== scan driver =====


MAX_PAIRS = 6
MAX_FILE_BYTES = 1_000_000
SCANNED_SUFFIXES = PROSE_SUFFIXES | DATA_SUFFIXES | CODE_SUFFIXES
LIMITS = [
    "Changed prose and touched exit tables are checked; unchanged symbol references are listed.",
    "Explicit script paths can resolve unchanged literals. Other unchanged behavior needs review.",
    "Prose in a changed file that no rule matches is listed, not judged.",
]

_COUNT_WORDS = (
    r"one|two|three|four|five|six|seven|eight|nine|ten|twice|"
    r"second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
)
_NUMBER_WORD = re.compile(rf"\b(?:{_COUNT_WORDS})\b", re.IGNORECASE)
_DIGITS = re.compile(r"(?<![\w#./:-])\d+(?![\w./-])")
_LEADING_COUNTER = re.compile(r"^\s*(?:\|\s*\d+\s*\||\d+[.)]\s|#+\s+\d+[.)]?\s)")
_QUANTIFIER = re.compile(
    r"\b(only|identical|every|never|always|exactly|none|same)\b", re.IGNORECASE
)
_BACKTICKED = re.compile(r"`([^`\s]{2,})`")
_VOCABULARY = {
    "exit": re.compile(r"\bexit(?:\s+codes?)?\b", re.IGNORECASE),
    "json": re.compile(r"\bjson\b", re.IGNORECASE),
    "raises": re.compile(r"\braises?\b", re.IGNORECASE),
    "returns": re.compile(r"\breturns?\b", re.IGNORECASE),
}
_TOKEN = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def claim_reasons(text: str) -> list[str]:
    """Why a prose line looks like a verifiable claim; empty when it does not."""
    body = _LEADING_COUNTER.sub("", text)
    reasons: list[str] = []
    if _NUMBER_WORD.search(body) or _DIGITS.search(body):
        reasons.append("number")
    reasons += [m.lower() for m in dict.fromkeys(_QUANTIFIER.findall(body))]
    reasons += [f"symbol:`{s}`" for s in dict.fromkeys(_BACKTICKED.findall(body))]
    reasons += [name for name, pattern in _VOCABULARY.items() if pattern.search(body)]
    return list(dict.fromkeys(reasons))


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text) if len(t) >= 3}


def _shared_prefix(a: str, b: str) -> int:
    count = 0
    for left, right in zip(a.split("/")[:-1], b.split("/")[:-1], strict=False):
        if left != right:
            break
        count += 1
    return count


def _shared_parts(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    count = 0
    for a, b in zip(left, right, strict=False):
        if a != b:
            break
        count += 1
    return count


class _PreparedRegions:
    """Precomputed region metadata and token index for fast checklist pairing."""

    def __init__(self, regions: dict[str, list[CodeRegion]]) -> None:
        self.items: list[tuple[str, str, tuple[str, ...], CodeRegion, frozenset[str]]] = []
        self.by_token: dict[str, list[int]] = {}
        self.by_basename: dict[str, list[int]] = {}
        self._base_top: dict[str, list[int]] = {}
        for path, found in regions.items():
            basename = Path(path).name
            parts = tuple(path.split("/")[:-1])
            for region in found:
                idx = len(self.items)
                toks = frozenset(_tokens(region.symbol))
                self.items.append((path, basename, parts, region, toks))
                self.by_basename.setdefault(basename, []).append(idx)
                for tok in toks:
                    self.by_token.setdefault(tok, []).append(idx)
        self._basenames = tuple(self.by_basename)

    def _top_zero_overlap(self, prose_file: str) -> list[int]:
        cached = self._base_top.get(prose_file)
        if cached is not None:
            return cached
        prose_parts = tuple(prose_file.split("/")[:-1])
        scored = [
            ((path != prose_file, 0, -_shared_parts(prose_parts, parts), path, region.line), idx)
            for idx, (path, _base, parts, region, _toks) in enumerate(self.items)
        ]
        scored.sort(key=lambda item: item[0])
        top = [idx for _, idx in scored[:MAX_PAIRS]]
        self._base_top[prose_file] = top
        return top

    def pair(self, prose: ProseLine) -> list[dict[str, Any]]:
        if not self.items:
            return []
        words = _tokens(prose.text)
        prose_parts = tuple(prose.file.split("/")[:-1])
        candidates = set(self._top_zero_overlap(prose.file))
        for tok in words:
            candidates.update(self.by_token.get(tok, ()))
        for basename in self._basenames:
            if basename in prose.text:
                candidates.update(self.by_basename[basename])
        ranked = []
        for idx in candidates:
            path, basename, parts, region, toks = self.items[idx]
            overlap = len(words & toks)
            if basename in prose.text:
                overlap += 5
            close = _shared_parts(prose_parts, parts)
            ranked.append(((path != prose.file, -overlap, -close, path, region.line), region))
        ranked.sort(key=lambda item: item[0])
        return [{"file": r.file, "line": r.line, "symbol": r.symbol} for _, r in ranked[:MAX_PAIRS]]


def pair_code(prose: ProseLine, regions: dict[str, list[CodeRegion]]) -> list[dict[str, Any]]:
    """Code symbols changed in this diff: same file first, then by overlap and path closeness."""
    return _PreparedRegions(regions).pair(prose)


def _read_scannable(target: Path, rel: str, is_unsafe: Callable[[Path], bool]) -> str | None:
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        return None
    path = target / rel
    if Path(rel).suffix not in SCANNED_SUFFIXES or is_unsafe(path):
        return None
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _proximity(prose_file: str, paths: list[str]) -> list[str]:
    return sorted(paths, key=lambda p: (-_shared_prefix(prose_file, p), p))


def _file_findings(
    rel: str,
    text: str,
    prose: list[ProseLine],
    index: CodeIndex,
    literal_index: CodeIndex | None = None,
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], list[str]]]:
    """Findings for one file's prose, plus extra checklist reasons keyed by prose line."""
    findings = check_exit_codes(rel, text, {p.line for p in prose}, index)
    notes: dict[tuple[str, int], list[str]] = {}
    order = _proximity(rel, list(index.sources))
    for line in prose:
        found = check_enumeration_subset(line, index, order)
        r3, r3_notes = check_json_key(line, index)
        literals = literal_index or index
        findings += (
            found + r3 + check_literal_subset(line, literals) + check_literal_count(line, literals)
        )
        if r3_notes:
            notes[(rel, line.line)] = r3_notes
    return findings, notes


def _expand_exit_table(rel: str, text: str, prose: list[ProseLine]) -> list[ProseLine]:
    """Treat each touched exit table as one claim unit."""
    if Path(rel).suffix not in PROSE_SUFFIXES:
        return prose
    lines = text.split("\n")
    touched = {p.line for p in prose}
    for _codes, span in _markdown_blocks(lines):
        if touched & span:
            prose += [
                ProseLine(rel, n, lines[n - 1].strip())
                for n in sorted(span - touched)
                if _TABLE_ROW.match(lines[n - 1])
            ]
    return prose


def run_same_pr(
    target: Path,
    changed_files: set[str],
    ranges: dict[str, list[list[int]]],
    *,
    normalize: Callable[[str], str],
    is_unsafe: Callable[[Path], bool],
    tracked_files: list[str] | None = None,
    removed_symbols: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Scan the changed hunks; return the findings and checklist documents."""
    texts: dict[str, str] = {}
    for rel in sorted(changed_files):
        text = _read_scannable(target, rel, is_unsafe)
        if text is not None:
            texts[rel] = text
    prose_by_file: dict[str, list[ProseLine]] = {}
    regions: dict[str, list[CodeRegion]] = {}
    code_lines = 0
    for rel, text in texts.items():
        prose, found, count = classify_file(rel, text, ranges.get(normalize(rel)))
        prose = _expand_exit_table(rel, text, prose)
        prose_by_file[rel], code_lines = prose, code_lines + count
        if found:
            regions[rel] = found
    index = CodeIndex(texts)
    # Explicit paths can pair a changed claim with an unchanged literal.
    references = {}
    for prose in prose_by_file.values():
        for claim in prose:
            for mention in _SCRIPT_MENTION.findall(claim.text):
                text = _read_scannable(target, mention, is_unsafe)
                if text is not None:
                    references[mention] = text
    literal_index = CodeIndex({**references, **texts})
    findings: list[dict[str, Any]] = []
    notes: dict[tuple[str, int], list[str]] = {}
    for rel, prose in prose_by_file.items():
        file_findings, file_notes = _file_findings(rel, texts[rel], prose, index, literal_index)
        findings += file_findings
        notes.update(file_notes)
    findings = _unique(findings)
    for number, finding in enumerate(findings, start=1):
        finding["id"] = f"same-pr-{number:04d}"
    flagged = {(f["prose"]["file"], f["prose"]["line"]) for f in findings}
    checklist_regions = {path: list(items) for path, items in regions.items()}
    for path, line, symbol, _values in literal_collections(literal_index):
        if path not in regions:
            checklist_regions.setdefault(path, []).append(CodeRegion(path, line, symbol))
    entries = _checklist(prose_by_file, checklist_regions, notes, flagged)
    entries += unchanged_references(
        target,
        tracked_files or [],
        ranges,
        regions,
        removed_symbols or {},
        is_unsafe,
        changed_files=changed_files,
        normalize=normalize,
    )
    examined = {
        "changed_files": len(changed_files),
        "scanned_files": len(texts),
        "skipped_files": len(changed_files) - len(texts),
        "prose_lines": sum(len(p) for p in prose_by_file.values()),
        "code_lines": code_lines,
    }
    return {
        "findings": {"status": "OK", "examined": examined, "findings": findings},
        "checklist": {"examined": examined, "limits": LIMITS, "entries": entries},
    }


_WORD_RUN = re.compile(r"\w+")
_PURE_WORD = re.compile(r"^\w+$")


def _match_aliases(
    text: str,
    word_aliases: set[str],
    flags_by_word: dict[str, list[str]],
    nonword_always: list[str],
    tree_nonword: list[str],
) -> set[str]:
    line_words = set(_WORD_RUN.findall(text))
    word_hits = line_words & word_aliases
    extras: set[str] = set()
    if "--" in text:
        for word in line_words:
            for flag in flags_by_word.get(word, ()):
                if flag in text:
                    extras.add(flag)
    for item in nonword_always:
        if item in text:
            extras.add(item)
    for item in tree_nonword:
        if item in text:
            extras.add(item)
    if not extras:
        return word_hits
    candidates = sorted(word_hits | extras, key=len, reverse=True)
    regex = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(n) for n in candidates) + r")(?![\w])")
    return set(regex.findall(text))


def _partition_aliases(
    aliases: dict[str, list[dict[str, Any]]],
    removed: dict[str, list[dict[str, Any]]],
) -> tuple[set[str], dict[str, list[str]], list[str], dict[str, list[str]], dict[str, set[str]]]:
    word_aliases: set[str] = set()
    flags_by_word: dict[str, list[str]] = {}
    nonword_always: list[str] = []
    tree_nonword: dict[str, list[str]] = {}
    removed_trees: dict[str, set[str]] = {
        sym: {_reference_tree(p["file"]) for p in pairs} for sym, pairs in removed.items()
    }
    for name in aliases:
        if _PURE_WORD.match(name):
            word_aliases.add(name)
        elif name.startswith("--") and (first := _WORD_RUN.search(name)):
            flags_by_word.setdefault(first.group(0), []).append(name)
        elif name in removed_trees:
            for tree in removed_trees[name]:
                tree_nonword.setdefault(tree, []).append(name)
        else:
            nonword_always.append(name)
    return word_aliases, flags_by_word, nonword_always, tree_nonword, removed_trees


def unchanged_references(
    target: Path,
    tracked: list[str],
    ranges: dict[str, list[list[int]]],
    regions: dict[str, list[CodeRegion]],
    removed: dict[str, list[dict[str, Any]]],
    is_unsafe: Callable[[Path], bool],
    *,
    changed_files: set[str],
    normalize: Callable[[str], str],
) -> list[dict[str, Any]]:
    """List unchanged prose naming changed symbols, flags, or deleted headings.

    A path in ``changed_files`` with no parsed hunk (binary, mode-only) is
    changed in full, as ``doc_accuracy._get_changed_diff`` documents, so none of
    its lines count as unchanged. A tracked path outside ``changed_files`` has
    no changed line.
    """
    changed_keys = {normalize(path) for path in changed_files}
    aliases: dict[str, list[dict[str, Any]]] = {}
    for path, changes in regions.items():
        for region in changes:
            if region.symbol == MODULE_SYMBOL or len(region.symbol.strip("_")) < 5:
                continue
            pair = {"file": path, "line": region.line, "symbol": region.symbol}
            for name in (region.symbol, "--" + region.symbol.strip("_").replace("_", "-")):
                aliases.setdefault(name, []).append(pair)
    for symbol, pairs in removed.items():
        aliases.setdefault(symbol, []).extend(pairs)
    if not aliases:
        return []
    word_aliases, flags_by_word, nonword_always, tree_nonword, removed_trees = _partition_aliases(
        aliases, removed
    )
    entries = []
    for rel in tracked:
        if Path(rel).suffix not in PROSE_SUFFIXES:
            continue
        text = _read_scannable(target, rel, is_unsafe)
        if text is None:
            continue
        lines = text.splitlines()
        key = normalize(rel)
        file_ranges = ranges.get(key) or ([] if key not in changed_keys else None)
        changed = changed_line_numbers(file_ranges, len(lines))
        rel_tree = _reference_tree(rel)
        local_nonword = tree_nonword.get(rel_tree, [])
        for line in _markdown_prose(rel, lines, set(range(1, len(lines) + 1)) - changed):
            names = _match_aliases(
                line.text, word_aliases, flags_by_word, nonword_always, local_nonword
            )
            # A heading's references belong to its skill tree or document directory.
            names = {n for n in names if n not in removed_trees or rel_tree in removed_trees[n]}
            if names:
                pairs = [p for name in sorted(names) for p in aliases[name]]
                entries.append(
                    {
                        "prose_file": rel,
                        "prose_line": line.line,
                        "text": line.text,
                        "reasons": [f"unchanged reference:`{n}`" for n in sorted(names)],
                        "pairs": pairs,
                    }
                )
    return entries


def _reference_tree(path: str) -> str:
    skill = re.search(r"(?:skills/)([^/.]+)", path)
    if skill:
        return skill.group(1).removesuffix(".SKILL")
    template = re.search(r"templates/skills/(.+)\.SKILL\.md\.tmpl", path)
    return template.group(1) if template else str(Path(path).parent)


def removed_references(diff: str) -> dict[str, list[dict[str, Any]]]:
    """Index deleted definitions, headings, and option strings from a Git diff."""
    found: dict[str, list[dict[str, Any]]] = {}
    path = ""
    old_line = 1
    for line in diff.splitlines():
        if line.startswith("--- a/"):
            path = line[6:]
        hunk = re.match(r"@@ -(\d+)", line)
        if hunk:
            old_line = int(hunk.group(1))
            continue
        if line.startswith(" "):
            old_line += 1
        if not line.startswith("-") or line.startswith("---"):
            continue
        text = line[1:]
        heading = re.match(r"#{1,6}\s+(.+)", text)
        definition = re.match(r"\s*(?:async\s+)?def\s+(\w+)\(", text)
        names = [heading.group(1).strip()] if heading else []
        names += [definition.group(1)] if definition else []
        names += re.findall(r"(?<!\w)--[a-z][a-z-]+", text)
        for name in names:
            found.setdefault(name, []).append(
                {"file": path, "line": old_line, "symbol": name, "side": "base"}
            )
        old_line += 1
    return found


def _unique(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    kept = []
    for finding in findings:
        key = json.dumps([finding["rule"], finding["prose"], finding["code"], finding["evidence"]])
        if key not in seen:
            seen.add(key)
            kept.append(finding)
    return kept


def _checklist(
    prose_by_file: dict[str, list[ProseLine]],
    regions: dict[str, list[CodeRegion]],
    notes: dict[tuple[str, int], list[str]],
    flagged: set[tuple[str, int]],
) -> list[dict[str, Any]]:
    prepared = _PreparedRegions(regions)
    entries = []
    for rel, prose in prose_by_file.items():
        for line in prose:
            reasons = [*claim_reasons(line.text), *notes.get((rel, line.line), [])]
            if reasons and (rel, line.line) not in flagged:
                entries.append(
                    {
                        "prose_file": rel,
                        "prose_line": line.line,
                        "text": line.text,
                        "reasons": reasons,
                        "pairs": prepared.pair(line),
                    }
                )
    return entries


def write_artifacts(output_dir: Path, result: dict[str, Any]) -> None:
    for name, key in (
        ("same-pr-findings.json", "findings"),
        ("same-pr-checklist.json", "checklist"),
    ):
        (output_dir / name).write_text(json.dumps(result[key], indent=2), encoding="utf-8")


def add_cardinality(
    result: dict[str, Any],
    target: Path,
    files: set[str],
    ranges: dict[str, list[list[int]]],
    detector: Any,
    is_unsafe: Callable[[Path], bool],
) -> None:
    """Reuse repository cardinality rules on changed prose and structured strings."""
    findings = result["findings"]["findings"]
    for rel in sorted(files):
        text = _read_scannable(target, rel, is_unsafe)
        if text is None:
            continue
        changed = changed_line_numbers(ranges.get(rel), len(text.splitlines()))
        suffix = Path(rel).suffix
        if suffix in PROSE_SUFFIXES:
            claims = detector.explicit_count_claims(text)
            rule = "nl-cardinality"
        elif suffix in DATA_SUFFIXES:
            claims = detector.structured_count_claims(text, "json" if suffix == ".json" else "yaml")
            rule = "structured-cardinality"
        else:
            continue
        for claim in claims:
            if claim.line not in changed:
                continue
            findings.append(
                make_finding(
                    rule,
                    "high",
                    ProseLine(rel, claim.line, text.splitlines()[claim.line - 1]),
                    (rel, claim.line, getattr(claim, "array_key", "enumeration")),
                    {"stated": claim.stated, "actual": claim.actual},
                    f"Count {claim.stated} differs from {claim.actual} enumerated entries",
                )
            )
    for number, finding in enumerate(findings, start=1):
        finding["id"] = f"same-pr-{number:04d}"


def fold_into_gate(
    gate: dict[str, Any],
    findings: list[dict[str, Any]],
    threshold: str,
    severity_order: dict[str, int],
) -> dict[str, Any]:
    """Add same-PR findings to a gate result; any at or above threshold makes it FAIL."""
    by_severity = dict(gate["by_severity"])
    blocking = gate["blocking_findings"]
    for finding in findings:
        sev = finding["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1
        if severity_order.get(sev, 3) <= severity_order.get(threshold, 1):
            blocking += 1
    verdict = "FAIL" if blocking else gate["verdict"]
    return {
        **gate,
        "verdict": verdict,
        "blocking_findings": blocking,
        "total_findings": sum(by_severity.values()),
        "by_severity": by_severity,
        "same_pr_findings": len(findings),
    }


def summary_lines(result: dict[str, Any]) -> list[str]:
    findings = result["findings"]["findings"]
    by_rule: dict[str, int] = {}
    for finding in findings:
        by_rule[finding["rule"]] = by_rule.get(finding["rule"], 0) + 1
    rules = ", ".join(f"{rule}: {n}" for rule, n in sorted(by_rule.items())) or "none"
    seen = result["findings"]["examined"]
    return [
        f"Same-PR findings: {len(findings)} ({rules})",
        f"Same-PR checklist: {len(result['checklist']['entries'])} entries",
        f"Same-PR examined: {seen['scanned_files']} of {seen['changed_files']} changed files, "
        f"{seen['prose_lines']} prose lines, {seen['code_lines']} code lines",
    ]
