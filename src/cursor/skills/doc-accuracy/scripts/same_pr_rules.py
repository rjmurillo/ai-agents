"""Deterministic same-PR rules R1 to R3 for `same_pr.py`.

Each rule compares a changed prose line with code that changed in the same diff
and returns finding dicts. A rule stays quiet when it cannot judge: R1 needs an
identifiable script, R2 needs a shared raise site, R3 needs an assignment with a
non-literal right side.

R1  exit-code set: an Exit Codes table or docstring block against the literal
    exit integers in the paired script.
R2  enumeration subset: prose names part of a closed set for a cause that every
    member of the set shares in code.
R3  JSON key contents: "<noun> under `key`" against what the code assigns to key.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Mapping

from same_pr_source import CodeIndex, ProseLine, const_str

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


def check_enumeration_subset(
    prose: ProseLine, index: CodeIndex, code_order: list[str]
) -> list[dict[str, object]]:
    """R2: a clause names two or more, but not all, members of a closed set."""
    text = prose.text.replace("`", "")
    found: list[dict[str, object]] = []
    for path in code_order:
        tree = index.tree(path)
        sites = _shared_sites(tree) if tree else []
        for members in _enum_sets(tree) if tree and sites else []:
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
        if noun.lower() in _PRONOUNS:
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
