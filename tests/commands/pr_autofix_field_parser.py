"""Static schema parser behind `test_pr_autofix_field_contract.py`.

Refs #5094. Extracts every `jq` read in the `/pr-autofix` command body, binds
each to the producer whose stdout it consumes, and derives that producer's real
output shape with `ast`, so a test can fail on any envelope-level or field-name
mismatch.

Split from the test module so each file stays under the 500-line taste rule,
following the `step0_parser.py` precedent in this directory. This module holds
no assertions; it is the parser the tests drive.

Two producer styles exist and the distinction is the whole point. Scripts routed
through `github_core.output.write_skill_output` wrap their payload in a `Data`
envelope, so reads must be `.Data.<field>` and field names compare against the
keys inside that envelope. Scripts that `print(json.dumps(result))` directly
emit a flat object, so reads must be `.<field>`.

A flat producer may still carry its own top-level `Success` key
(`test_pr_merge_ready.py` does), so envelope detection keys off the emitter
call, never off the presence of a `Success` field.

Public symbols:

- `ProducerSchema`, `derive_producer_schema(script)`: a producer's real shape
- `FieldRead`, `extract_field_reads(text)`: reads found in a command body
- `contract_violations(text)`: every mismatch, one finding per read
- `logical_lines(text)`: backslash-continuation joining, exposed for tests
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / ".claude" / "commands" / "pr-autofix.md"
MIRROR_PATH = REPO_ROOT / "src" / "copilot-cli" / "skills" / "pr-autofix" / "SKILL.md"
PRODUCER_DIR = REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr"

# `github_core.output` helpers that wrap their payload in a `Data` envelope.
DATA_ENVELOPE_EMITTERS = frozenset({"write_skill_output", "write_skill_error"})

_INVOKE = re.compile(r"\$SCRIPTS_DIR/([A-Za-z0-9_]+)\.py")
_BIND = re.compile(r"^\s*(?:if\s+)?([A-Za-z_][A-Za-z0-9_]*)=\$\(")
# A jq invocation and its single-quoted program. The program is matched whole so
# every path inside it is seen, not just the first: `.Data.a // .Data.b` is two
# reads, and checking only the leading one leaves the fallback unverified.
_JQ_PROGRAM = re.compile(r"jq\s[^|>']*'([^']*)'")
# A path reference inside a jq program. Anchored on a leading dot preceded by a
# non-path character so `.b` in `.Data.a // .Data.b` starts a new match while
# the `.a` inside `.Data.a` does not.
_JQ_PATH = re.compile(r"(?:^|[^A-Za-z0-9_.])(\.[A-Za-z_][A-Za-z0-9_.]*)")
# Bare `jq` as a command word. Independent of _JQ_PROGRAM on purpose; see
# jq_invocation_lines for why the guard must not share the extractor's regex.
_JQ_TOKEN = re.compile(r"(?:^|[|\s(])jq\s")
_VAR_REF = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")


# Producer side: derive each script's real output shape from its source.


@dataclass(frozen=True)
class ProducerSchema:
    """What a producer script actually writes to stdout.

    Attributes:
        script: Producer module name, without the `.py` suffix.
        wraps_in_data: True when stdout carries a `Data` envelope.
        top_level_keys: Keys a read may name, or None when the shape is not
            statically derivable. For a wrapped producer these are the keys
            inside the envelope, so they compare against the segment after
            `.Data.`; for a flat producer they compare against the first
            segment. None means "cannot tell", not "no fields", so the field
            check stands down rather than inventing a violation.
    """

    script: str
    wraps_in_data: bool
    top_level_keys: frozenset[str] | None


def _callee_name(func: ast.expr) -> str | None:
    """Return the bare name of a call target, ignoring any module prefix."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _calls_data_emitter(tree: ast.Module) -> bool:
    """True when the module routes stdout through a `Data`-wrapping emitter."""
    return any(
        isinstance(node, ast.Call) and _callee_name(node.func) in DATA_ENVELOPE_EMITTERS
        for node in ast.walk(tree)
    )


def _json_dumped_name(tree: ast.Module) -> str | None:
    """Name of the variable printed via `print(json.dumps(<name>))`, if any."""
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _callee_name(node.func) == "print"):
            continue
        if not node.args:
            continue
        dumped = node.args[0]
        if not (isinstance(dumped, ast.Call) and _callee_name(dumped.func) == "dumps"):
            continue
        if dumped.args and isinstance(dumped.args[0], ast.Name):
            return dumped.args[0].id
    return None


def _literal_dict_keys(node: ast.Dict) -> set[str]:
    """String keys of a dict literal; non-literal keys are skipped."""
    return {
        key.value
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def _subscript_key(target: ast.expr, name: str) -> str | None:
    """Return `k` for an assignment shaped `name["k"] = ...`, else None."""
    if not (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)):
        return None
    if target.value.id != name:
        return None
    if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
        return target.slice.value
    return None


def _keys_bound_to(tree: ast.Module, name: str) -> frozenset[str] | None:
    """Union of keys the module ever puts on a dict bound to `name`.

    Collects dict-literal assignments (`name = {...}`), the annotated form
    (`name: dict[str, object] = {...}`), and per-key assignments
    (`name["k"] = ...`) anywhere in the module. Returns None when the name is
    never bound to a dict, which marks the shape as underivable rather than
    empty, so a caller can tell "no such field" from "cannot tell".

    The annotated form is not an optional nicety. `get_pr_context.py` builds
    its payload that way, and an `ast.Assign`-only walk silently returned three
    keys instead of thirty, which would have failed the valid
    `.Data.auto_merge_method` read as a phantom field.
    """
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            targets: list[ast.expr] = [node.target]
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
        else:
            continue
        for target in targets:
            if (
                isinstance(target, ast.Name)
                and target.id == name
                and isinstance(node.value, ast.Dict)
            ):
                keys |= _literal_dict_keys(node.value)
            subscript = _subscript_key(target, name)
            if subscript is not None:
                keys.add(subscript)
    return frozenset(keys) if keys else None


def _emitter_payload_names(tree: ast.Module) -> set[str]:
    """Names of the dicts handed to a `Data`-wrapping emitter.

    The payload is the first positional argument to `write_skill_output`, or
    the `extra=` keyword on `write_skill_error`. A module may emit from several
    branches (`pr_autofix_lease.py` uses three), so every name is collected and
    the caller unions their keys: a field is legitimate if any emitted branch
    carries it.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _callee_name(node.func) in DATA_ENVELOPE_EMITTERS):
            continue
        if node.args and isinstance(node.args[0], ast.Name):
            names.add(node.args[0].id)
        for keyword in node.keywords:
            if keyword.arg == "extra" and isinstance(keyword.value, ast.Name):
                names.add(keyword.value.id)
    return names


def _union_keys(tree: ast.Module, names: set[str]) -> frozenset[str] | None:
    """Union of the keys bound to every name in `names`, or None if none resolve."""
    keys: set[str] = set()
    for name in names:
        bound = _keys_bound_to(tree, name)
        if bound:
            keys |= set(bound)
    return frozenset(keys) if keys else None


def derive_producer_schema(script: str) -> ProducerSchema:
    """Statically derive `script`'s stdout shape from its source.

    For a `Data`-wrapped producer the derived keys are those of the payload
    inside the envelope, so a caller compares them against the segment after
    `.Data.`.
    """
    tree = ast.parse((PRODUCER_DIR / f"{script}.py").read_text(encoding="utf-8"))
    if _calls_data_emitter(tree):
        keys = _union_keys(tree, _emitter_payload_names(tree))
        return ProducerSchema(script=script, wraps_in_data=True, top_level_keys=keys)
    dumped = _json_dumped_name(tree)
    keys = _keys_bound_to(tree, dumped) if dumped else None
    return ProducerSchema(script=script, wraps_in_data=False, top_level_keys=keys)


# Command side: extract every jq read and bind it to its producer.


@dataclass(frozen=True)
class FieldRead:
    """One `jq` read in the command body.

    Attributes:
        line: 1-indexed line where the read's logical line starts.
        script: Producer whose stdout the read consumes, or None when the read
            could not be bound to one.
        path: The jq path as written, for example `.Data.action`.
    """

    line: int
    script: str | None
    path: str


def logical_lines(text: str) -> list[tuple[int, str]]:
    """Join backslash-continued lines so a read and its producer stay together.

    Returns (start_line, joined_text) pairs. The line number is that of the
    first physical line, which is what a reader needs to find the read.
    """
    joined: list[tuple[int, str]] = []
    buffer = ""
    start = 1
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not buffer:
            start = lineno
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        joined.append((start, buffer + stripped))
        buffer = ""
    if buffer:
        joined.append((start, buffer))
    return joined


def extract_field_reads(text: str) -> list[FieldRead]:
    """Extract every jq read in `text`, bound to the producer it consumes.

    Handles the two shapes the command body uses: a producer piped straight
    into `jq`, and a producer captured into a shell variable that a later line
    pipes into `jq`.
    """
    bindings: dict[str, str] = {}
    reads: list[FieldRead] = []
    for lineno, line in logical_lines(text):
        if line.lstrip().startswith("#"):
            continue
        scripts = _INVOKE.findall(line)
        capture = _BIND.search(line)
        if scripts and capture and not jq_paths(line):
            bindings[capture.group(1)] = scripts[0]
            continue
        for source, program in _reads_by_invocation(line, bindings):
            reads.extend(
                FieldRead(line=lineno, script=source, path=path)
                for path in _JQ_PATH.findall(program)
            )
    return reads


def _reads_by_invocation(line: str, bindings: dict[str, str]) -> list[tuple[str | None, str]]:
    """Pair each jq program on `line` with the producer feeding *that* jq.

    Binding per line instead of per invocation was the fourth instance of this
    PR's recurring bug: a line with two producer pipelines assigned every path
    to the first producer, so the second read was checked against the wrong
    schema and a real mismatch could pass. The coverage guard deliberately
    permits several jq commands per line, so the two together made the hole
    reachable rather than theoretical.

    Each jq program sees only the text between the previous jq program and
    itself, which is what actually feeds it. Within that window the nearer of a
    direct producer invocation and a captured-variable reference wins, because
    `X=$(a.py); printf '%s' "$Y" | jq` feeds the jq from `$Y`, not from `a.py`.
    """
    pairs: list[tuple[str | None, str]] = []
    previous_end = 0
    for match in _JQ_PROGRAM.finditer(line):
        window = line[previous_end : match.start()]
        previous_end = match.end()
        pairs.append((_window_source(window, bindings), match.group(1)))
    return pairs


def _window_source(window: str, bindings: dict[str, str]) -> str | None:
    """Producer feeding a jq whose input is `window`, nearest reference wins."""
    invocations = list(_INVOKE.finditer(window))
    direct_at = invocations[-1].start() if invocations else -1

    bound_at = -1
    bound_source: str | None = None
    for reference in _VAR_REF.finditer(window):
        if reference.group(1) in bindings:
            bound_at = reference.start()
            bound_source = bindings[reference.group(1)]

    if direct_at < 0 and bound_at < 0:
        return None
    return invocations[-1].group(1) if direct_at > bound_at else bound_source


def jq_paths(line: str) -> list[str]:
    """Every path referenced by every jq program on `line`, in order.

    A jq program can name more than one path (`.Data.a // .Data.b`), and a line
    can carry more than one jq invocation, so both are enumerated. Literal
    defaults (`// "UNKNOWN"`, `// empty`) carry no leading dot and drop out.
    """
    return [path for program in _JQ_PROGRAM.findall(line) for path in _JQ_PATH.findall(program)]


def jq_invocation_count(line: str) -> int:
    """How many jq commands `line` runs, counted independently of the parser."""
    return len(_JQ_TOKEN.findall(line))


def jq_programs(line: str) -> list[str]:
    """The jq program text the parser could extract from `line`, in order."""
    return _JQ_PROGRAM.findall(line)


def unparsed_jq_invocations(line: str) -> int:
    """How many jq commands on `line` the parser never read a program for.

    Counting paths against invocations does not work, and the difference is the
    whole point of this helper. A program may name several paths, so one
    well-parsed invocation can supply enough paths to cover for a sibling the
    parser never read: `jq -r '.Data.a // .Data.b'` next to an unparseable
    `jq -r ".Data.$field"` yields 2 paths for 2 invocations and the arithmetic
    balances while half the line is unchecked. Comparing programs to invocations
    is per-invocation and cannot be masked that way.
    """
    return max(0, jq_invocation_count(line) - len(jq_programs(line)))


def pathless_jq_programs(line: str) -> list[str]:
    """Programs the parser read but got no path out of.

    A program the parser reads but cannot pull a path from is also unchecked,
    just one stage later than an unread one, so the guard needs both.
    """
    return [program for program in jq_programs(line) if not _JQ_PATH.findall(program)]


def jq_invocation_lines(text: str) -> list[tuple[int, str]]:
    """Logical lines that invoke jq, ignoring comments.

    Exists so a test can assert the extractor reached every one of them.
    `extract_field_reads` can only report a read it found; a read it never saw
    (an unusual quoting style, a path starting with `[` or `$`) is silently
    absent and leaves the suite green. Comparing against this list makes the
    extractor's reach falsifiable instead of assumed.

    Deliberately does NOT reuse `_JQ_PROGRAM`. A guard built on the same regex
    as the thing it guards goes blind in lockstep with it: break that pattern
    and both the extractor and the guard see zero invocations, so the guard
    passes vacuously and certifies the blindness it exists to catch. `_JQ_TOKEN`
    only has to spot the word `jq`, which is a far weaker claim than parsing its
    program, and that independence is the whole point.
    """
    return [
        (lineno, line)
        for lineno, line in logical_lines(text)
        if not line.lstrip().startswith("#") and _JQ_TOKEN.search(line)
    ]


def _bound_source(line: str, bindings: dict[str, str]) -> str | None:
    """Producer behind the first captured variable referenced on `line`."""
    for var in _VAR_REF.findall(line):
        if var in bindings:
            return bindings[var]
    return None


# The check itself.


def _envelope_violation(read: FieldRead, schema: ProducerSchema) -> str | None:
    """Report a read whose `Data.` prefix disagrees with the producer."""
    has_prefix = read.path.startswith(".Data.")
    if schema.wraps_in_data and not has_prefix:
        return (
            f"line {read.line}: reads `{read.path}` from {schema.script}.py, which "
            f"wraps its payload in a Data envelope. Use `.Data{read.path}`."
        )
    if not schema.wraps_in_data and has_prefix:
        return (
            f"line {read.line}: reads `{read.path}` from {schema.script}.py, which "
            f"prints a flat object with no Data envelope. Use "
            f"`{read.path.replace('.Data', '', 1)}`. The read yields null today, "
            f"so the `//` default fires and the gate never gates."
        )
    return None


def _field_violation(read: FieldRead, schema: ProducerSchema) -> str | None:
    """Report a read naming a field the producer never emits.

    Applies to both producer styles. For a `Data`-wrapped producer the compared
    segment is the one after `.Data.`, which is what makes the originally
    reported defect (`.Data.tier` from a script emitting no tier) fail here.
    """
    if schema.top_level_keys is None:
        return None
    path = read.path[len(".Data") :] if read.path.startswith(".Data.") else read.path
    field = path.lstrip(".").split(".")[0]
    if field in schema.top_level_keys:
        return None
    return (
        f"line {read.line}: reads `{read.path}` from {schema.script}.py, which "
        f"emits no `{field}` field. Known fields: "
        f"{', '.join(sorted(schema.top_level_keys))}."
    )


def contract_violations(text: str) -> list[str]:
    """Every envelope-level and field-name mismatch in a command body.

    One read yields at most one finding. A read at the wrong envelope level
    also names a field the producer lacks, but reporting both would describe
    a single defect twice: the field name cannot be judged until the envelope
    is right, so the envelope finding wins.
    """
    problems: list[str] = []
    for read in extract_field_reads(text):
        if read.script is None:
            continue
        schema = derive_producer_schema(read.script)
        finding = _envelope_violation(read, schema) or _field_violation(read, schema)
        if finding:
            problems.append(finding)
    return problems
