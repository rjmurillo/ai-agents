"""Contract test between `pr-autofix.md`'s jq reads and its producer scripts.

Refs #5094. The `/pr-autofix` command body pipes producer scripts through `jq`
and branches on the result. When a read names a path the producer never emits,
`jq` yields `null`, the `//` default fires, and the gate silently evaluates as
if it had evidence. Nothing fails; the gate just stops gating.

That defect shipped twice in this file, one script apart. First `TIER` read
`.Data.tier` from `check_pr_live_state.py`, which emits no tier field at all.
The repair then pointed at the right script but kept the envelope, reading
`.Data.Tier` from `test_pr_merge_ready.py`, which has no `--output-format` flag
and prints its result dict directly. Both instances left `TIER` pinned at
`UNKNOWN`, silently disabling the round-cap circuit breaker's T3/T4 check and
the auto-merge disarm gate's non-T1 check.

This test closes the class rather than the instance. It extracts every jq read
in the command body, binds each to the producer whose stdout it consumes,
derives that producer's real output shape with `ast`, and fails on any mismatch
of envelope level or field name.

Two producer styles exist and the distinction is the whole point. Scripts routed
through `github_core.output.write_skill_output` wrap their payload in a `Data`
envelope, so reads must be `.Data.<field>`. Scripts that
`print(json.dumps(result))` directly emit a flat object, so reads must be
`.<field>`. A flat producer may still carry its own top-level `Success` key
(`test_pr_merge_ready.py` does), so envelope detection keys off the emitter
call, never off the presence of a `Success` field.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / ".claude" / "commands" / "pr-autofix.md"
MIRROR_PATH = (
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "pr-autofix" / "SKILL.md"
)
PRODUCER_DIR = REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr"

# `github_core.output` helpers that wrap their payload in a `Data` envelope.
DATA_ENVELOPE_EMITTERS = frozenset({"write_skill_output", "write_skill_error"})

_INVOKE = re.compile(r"\$SCRIPTS_DIR/([A-Za-z0-9_]+)\.py")
_BIND = re.compile(r"^\s*(?:if\s+)?([A-Za-z_][A-Za-z0-9_]*)=\$\(")
_JQ_PATH = re.compile(r"jq\s[^|>]*?'(\.[A-Za-z_][A-Za-z0-9_.]*)")
_VAR_REF = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")


# Producer side: derive each script's real output shape from its source.


@dataclass(frozen=True)
class ProducerSchema:
    """What a producer script actually writes to stdout.

    Attributes:
        script: Producer module name, without the `.py` suffix.
        wraps_in_data: True when stdout carries a `Data` envelope.
        top_level_keys: Keys of the emitted object, or None when the shape is
            not statically derivable (every `Data`-wrapped producer builds its
            payload across call boundaries, so only flat producers resolve).
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

    Collects both dict-literal assignments (`name = {...}`) and per-key
    assignments (`name["k"] = ...`) anywhere in the module. Returns None when
    the name is never bound to a dict, which marks the shape as underivable
    rather than empty.
    """
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
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


def derive_producer_schema(script: str) -> ProducerSchema:
    """Statically derive `script`'s stdout shape from its source."""
    tree = ast.parse((PRODUCER_DIR / f"{script}.py").read_text(encoding="utf-8"))
    if _calls_data_emitter(tree):
        return ProducerSchema(script=script, wraps_in_data=True, top_level_keys=None)
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
        paths = _JQ_PATH.findall(line)
        capture = _BIND.search(line)
        if scripts and capture and not paths:
            bindings[capture.group(1)] = scripts[0]
            continue
        if not paths:
            continue
        source = scripts[0] if scripts else _bound_source(line, bindings)
        reads.extend(FieldRead(line=lineno, script=source, path=path) for path in paths)
    return reads


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
    """Report a read naming a field the flat producer never emits."""
    if schema.wraps_in_data or schema.top_level_keys is None:
        return None
    field = read.path.lstrip(".").split(".")[0]
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


@pytest.fixture(scope="module")
def command_body() -> str:
    return COMMAND_PATH.read_text(encoding="utf-8")


# Positive: the shipped command and its mirror honor every producer contract.


def test_source_command_has_no_contract_violations(command_body: str) -> None:
    violations = contract_violations(command_body)

    assert violations == [], (
        "pr-autofix.md reads fields its producers never emit:\n"
        + "\n".join(violations)
    )


def test_copilot_mirror_has_no_contract_violations() -> None:
    violations = contract_violations(MIRROR_PATH.read_text(encoding="utf-8"))

    assert violations == [], (
        "The shipped Copilot mirror drifted from producer contracts:\n"
        + "\n".join(violations)
    )


def test_mirror_reads_match_source_reads(command_body: str) -> None:
    """The mirror is generated, so its reads must equal the source's reads."""
    source = [(r.script, r.path) for r in extract_field_reads(command_body)]
    mirror = [
        (r.script, r.path)
        for r in extract_field_reads(MIRROR_PATH.read_text(encoding="utf-8"))
    ]

    assert source == mirror, (
        "src/copilot-cli/skills/pr-autofix/SKILL.md is stale. Re-run "
        "`uv run python build/scripts/generate_commands.py`."
    )


def test_tier_read_targets_the_authoritative_flat_producer(command_body: str) -> None:
    """Pin the specific regression from issue #5094 and its repeat."""
    tier_reads = [
        r for r in extract_field_reads(command_body) if r.path.endswith("Tier")
    ]

    assert tier_reads, "The TIER read vanished; the round-cap gate lost its input."
    for read in tier_reads:
        assert read.script == "test_pr_merge_ready", (
            f"line {read.line}: tier must come from test_pr_merge_ready.py, the "
            f"authoritative tier source, not {read.script}.py."
        )
        assert read.path == ".Tier", (
            f"line {read.line}: expected `.Tier`, got `{read.path}`. "
            "test_pr_merge_ready.py emits no Data envelope."
        )


# Coverage: the extractor must not go blind and silently pass.


def test_every_read_binds_to_a_producer(command_body: str) -> None:
    """An unbound read is unchecked, so treat it as a failure, not a skip."""
    unbound = [r for r in extract_field_reads(command_body) if r.script is None]

    assert unbound == [], "Reads that bind to no producer are unchecked:\n" + "\n".join(
        f"line {r.line}: `{r.path}`" for r in unbound
    )


def test_extractor_finds_reads_for_every_producer_style(command_body: str) -> None:
    """Both envelope styles must be represented, or the check proves little."""
    scripts = {r.script for r in extract_field_reads(command_body)}
    schemas = [derive_producer_schema(s) for s in scripts if s]

    assert any(s.wraps_in_data for s in schemas), "No Data-wrapped producer covered."
    assert any(not s.wraps_in_data for s in schemas), "No flat producer covered."


@pytest.mark.parametrize(
    ("script", "expected_wrap"),
    [
        ("test_pr_merge_ready", False),
        ("test_pr_merged", False),
        ("check_pr_live_state", True),
        ("check_pr_round_cap", True),
        ("get_pr_context", True),
        ("pr_autofix_lease", True),
    ],
)
def test_producer_envelope_classification(script: str, expected_wrap: bool) -> None:
    assert derive_producer_schema(script).wraps_in_data is expected_wrap


def test_flat_producer_keys_include_the_fields_the_command_reads() -> None:
    schema = derive_producer_schema("test_pr_merge_ready")

    assert schema.top_level_keys is not None
    assert "Tier" in schema.top_level_keys, "Tier is set via `result['Tier'] = ...`."
    assert "CanMerge" in schema.top_level_keys


# Negative controls: the check must actually fail on each known defect shape.


def _piped_read(script: str, jq_path: str) -> str:
    """A one-line command body piping `script` straight into a `jq` read."""
    return (
        f'VALUE=$(python3 "$SCRIPTS_DIR/{script}.py" --pull-request "$PR" '
        f"| jq -r '{jq_path}')\n"
    )


def test_detects_data_prefix_on_flat_producer() -> None:
    """The exact regression this PR fixes must be caught."""
    body = _piped_read("test_pr_merge_ready", '.Data.Tier // "UNKNOWN"')

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "flat object with no Data envelope" in violations[0]


def test_detects_unknown_field_on_flat_producer() -> None:
    """The originally reported shape: a field no producer emits."""
    body = _piped_read("test_pr_merge_ready", '.tier // "UNKNOWN"')

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "emits no `tier` field" in violations[0]


def test_detects_missing_data_prefix_on_wrapped_producer() -> None:
    """The mirror-image defect: dropping the envelope a producer does emit."""
    body = _piped_read("check_pr_live_state", ".action")

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "wraps its payload in a Data envelope" in violations[0]


def test_detects_violation_through_a_captured_variable() -> None:
    """Binding via a shell variable must be checked, not just direct pipes."""
    body = (
        'LIVE=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" --pull-request "$PR")\n'
        "ACTION=$(echo \"$LIVE\" | jq -r '.action')\n"
    )

    violations = contract_violations(body)

    assert len(violations) == 1
    assert "check_pr_live_state.py" in violations[0]


def test_correct_reads_produce_no_violations() -> None:
    """Guard against a check that fails everything and looks strict."""
    body = (
        'LIVE=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" --pull-request "$PR")\n'
        "ACTION=$(echo \"$LIVE\" | jq -r '.Data.action')\n"
        'TIER=$(python3 "$SCRIPTS_DIR/test_pr_merge_ready.py" --pull-request "$PR" '
        "| jq -r '.Tier // \"UNKNOWN\"')\n"
    )

    assert contract_violations(body) == []


# Edge cases in the extraction helpers.


def test_logical_lines_joins_backslash_continuations() -> None:
    joined = logical_lines(
        'CTX=$(python3 "$SCRIPTS_DIR/get_pr_context.py" \\\n'
        "    --output-format json)\n"
    )

    assert len(joined) == 1
    assert joined[0][0] == 1
    assert "get_pr_context.py" in joined[0][1]
    assert "--output-format" in joined[0][1]


def test_logical_lines_reports_the_first_physical_line() -> None:
    joined = logical_lines("alpha\nbeta \\\n    gamma\ndelta\n")

    assert [lineno for lineno, _ in joined] == [1, 2, 4]


def test_commented_reads_are_ignored() -> None:
    """Prose in comments explains defects; it must not be read as code."""
    body = "# Reading .Data.Tier here would pin TIER at UNKNOWN | jq -r '.Data.Tier'\n"

    assert extract_field_reads(body) == []


def test_a_read_with_no_producer_in_scope_is_reported_unbound() -> None:
    assert extract_field_reads("VALUE=$(echo \"$OTHER\" | jq -r '.Data.action')\n") == [
        FieldRead(line=1, script=None, path=".Data.action")
    ]
