# taste-lint: ignore file-size -- one module because the Hermes delivery pack is at its file cap
"""Same-PR doc accuracy: catch prose that drifts from code changed in the same diff.

Activated by `doc_accuracy.py --same-pr --diff-base REF`. It reads the changed
hunks of every text file in the diff, not only documentation globs, and sorts
each changed line into prose (Markdown and `.tmpl` lines, Python docstrings and
comments, JSON and YAML string values) or code (with its enclosing symbol).

Three deterministic rules emit findings that can fail the gate: R1 exit-code
sets, R2 enumeration subsets, R3 JSON key contents. Every other changed prose
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
from typing import Any

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
        functions only: a ``return 1`` in a helper is rarely a process exit code.
        """
        tree = self.tree(rel)
        found: dict[int, int] = {}
        if tree is None:
            return found
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_exit_call(node) and node.args:
                self._take(found, node.args[0], node.lineno)
            if isinstance(node, ast.FunctionDef) and node.name in self._MAIN_NAMES:
                for ret in ast.walk(node):
                    if isinstance(ret, ast.Return) and ret.value is not None:
                        self._take(found, ret.value, ret.lineno)
        return found

    @staticmethod
    def _take(found: dict[int, int], value: ast.AST, line: int) -> None:
        if isinstance(value, ast.Constant) and type(value.value) is int:
            found.setdefault(value.value, line)

    def assignments(self, key: str) -> list[tuple[str, int, set[str]]]:
        """Return (file, line, identifiers on the right) for each write to ``key``."""
        found = []
        for rel in self.sources:
            tree = self.tree(rel)
            for node in ast.walk(tree) if tree else []:
                for value in _writes_to(node, key):
                    found.append((rel, getattr(node, "lineno", 1), _identifiers(value)))
        return found


def _writes_to(node: ast.AST, key: str) -> list[ast.AST]:
    """Return the value nodes that ``node`` assigns to attribute, item, or keyword ``key``."""
    if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(_names_key(t, key) for t in targets):
            return [node.value]
    if isinstance(node, ast.Call):
        return [kw.value for kw in node.keywords if kw.arg == key]
    if isinstance(node, ast.Dict):
        return [v for k, v in zip(node.keys, node.values, strict=True) if const_str(k) == key]
    return []


def const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _names_key(target: ast.AST, key: str) -> bool:
    if isinstance(target, ast.Attribute):
        return target.attr == key
    return isinstance(target, ast.Subscript) and const_str(target.slice) == key


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
        if not (doc_only or code_only):
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
    return found


def _subset_finding(
    prose: ProseLine,
    path: str,
    members: set[str],
    named: list[str],
    clause: str,
    sites: list[Site],
) -> list[dict[str, object]]:
    if len(set(named)) < 2 or set(named) >= members:
        return []
    scored = sorted(((len(_stems(clause) & site[2]), site) for site in sites), key=lambda s: -s[0])
    best = scored[0] if scored else (0, ("", 0, set()))
    if best[0] < 2 or (len(scored) > 1 and scored[1][0] == best[0]):
        return []
    function, line, _ = best[1]
    missing = sorted(members - set(named))
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


# -- R3 -----------------------------------------------------------------------

_NOUN_UNDER_KEY = re.compile(r"(?P<noun>[A-Za-z][\w-]*)\s+under\s+`(?P<key>[A-Za-z_]\w*)`")
_KEY_HOLDS_NOUN = re.compile(
    r"`(?P<key>[A-Za-z_]\w*)`\s+(?:holds|keeps|records|stores|contains|retains)\s+"
    r"(?:the\s+|a\s+|an\s+)?(?P<noun>[A-Za-z][\w-]*)"
)
# Placeholder names that docs use to describe the pattern itself, not a real JSON key.
_PLACEHOLDER_KEYS = {"key", "field", "name", "value", "k", "x"}
_PRONOUNS = {"it", "them", "this", "that", "these", "those", "all", "everything", "both"}


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
    pairs = [
        m.groupdict() for p in (_NOUN_UNDER_KEY, _KEY_HOLDS_NOUN) for m in p.finditer(prose.text)
    ]
    for pair in pairs:
        noun, key = pair["noun"], pair["key"]
        if noun.lower() in _PRONOUNS or key in _PLACEHOLDER_KEYS:
            continue
        writes = [w for w in index.assignments(key) if w[2]]
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
    "Only changed lines are read, and only code files changed in this diff are paired.",
    "A claim contradicted by an unchanged file, such as a rule in a sibling document, "
    "is not found here; the Phase 4 reviewer has to look for it.",
    "Prose in a changed file that no rule matches is listed, not judged.",
]

_COUNT_WORDS = (
    r"two|three|four|five|six|seven|eight|nine|ten|twice|"
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


def pair_code(prose: ProseLine, regions: dict[str, list[CodeRegion]]) -> list[dict[str, Any]]:
    """Code symbols changed in this diff: same file first, then by overlap and path closeness."""
    words = _tokens(prose.text)
    ranked = []
    for path, found in regions.items():
        close = _shared_prefix(prose.file, path)
        for region in found:
            overlap = len(words & _tokens(region.symbol))
            ranked.append(((path != prose.file, -overlap, -close, path, region.line), region))
    ranked.sort(key=lambda item: item[0])
    return [{"file": r.file, "line": r.line, "symbol": r.symbol} for _, r in ranked[:MAX_PAIRS]]


def _read_scannable(target: Path, rel: str, is_unsafe: Callable[[Path], bool]) -> str | None:
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
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], list[str]]]:
    """Findings for one file's prose, plus extra checklist reasons keyed by prose line."""
    findings = check_exit_codes(rel, text, {p.line for p in prose}, index)
    notes: dict[tuple[str, int], list[str]] = {}
    order = _proximity(rel, list(index.sources))
    for line in prose:
        found = check_enumeration_subset(line, index, order)
        r3, r3_notes = check_json_key(line, index)
        findings += found + r3
        if r3_notes:
            notes[(rel, line.line)] = r3_notes
    return findings, notes


def run_same_pr(
    target: Path,
    changed_files: set[str],
    ranges: dict[str, list[list[int]]],
    *,
    normalize: Callable[[str], str],
    is_unsafe: Callable[[Path], bool],
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
        prose_by_file[rel], code_lines = prose, code_lines + count
        if found:
            regions[rel] = found
    index = CodeIndex(texts)
    findings: list[dict[str, Any]] = []
    notes: dict[tuple[str, int], list[str]] = {}
    for rel, prose in prose_by_file.items():
        file_findings, file_notes = _file_findings(rel, texts[rel], prose, index)
        findings += file_findings
        notes.update(file_notes)
    findings = _unique(findings)
    for number, finding in enumerate(findings, start=1):
        finding["id"] = f"same-pr-{number:04d}"
    flagged = {(f["prose"]["file"], f["prose"]["line"]) for f in findings}
    entries = _checklist(prose_by_file, regions, notes, flagged)
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
                        "pairs": pair_code(line, regions),
                    }
                )
    return entries


def write_artifacts(output_dir: Path, result: dict[str, Any]) -> None:
    for name, key in (
        ("same-pr-findings.json", "findings"),
        ("same-pr-checklist.json", "checklist"),
    ):
        (output_dir / name).write_text(json.dumps(result[key], indent=2), encoding="utf-8")


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
