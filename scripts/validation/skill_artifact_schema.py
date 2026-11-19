"""The declaration schema for `metadata.inputs` and `metadata.outputs` (ADR-123).

`check_skill_artifact_flow.py` owns the graph checks. This module owns what
one declaration may look like, and the check that skillforge's stdlib parser
can read a template at all. skillforge's `lint_skill_frontmatter.py` carries a
copy of the grammars below for consumers; `test_lint_skill_frontmatter_mirror.py`
fails when the two differ.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

_SCRIPT_DIR = Path(__file__).resolve().parent

ARTIFACT_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
# Relative to the artifact root. Each segment starts with a lowercase letter or
# digit, so `..`, `.git`, a leading `/`, `\`, `~`, `$`, `:` and control
# characters cannot match. Applied with `fullmatch`, so a trailing newline fails.
PATH_RE = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*/?")

SOURCES: tuple[str, ...] = ("skill", "user", "repo")
INPUT_KEYS: frozenset[str] = frozenset({"source", "required"})
OUTPUT_KEYS: frozenset[str] = frozenset({"path"})

# skillforge ships a stdlib-only frontmatter parser that consumers run without
# PyYAML. PyYAML accepts shapes it refuses (flow mappings, mappings inside a
# sequence, quoted keys), so a template a PyYAML gate passes can still make
# conformance report NOT_EVALUATED on every MUST rule. It is imported from this
# checkout, not from the repository under test, so fixture trees need no copy.
_SUBSET_PARSER_DIR = _SCRIPT_DIR.parents[1] / "src" / "claude" / "skills" / "skillforge" / "scripts"


@dataclass(frozen=True)
class Input:
    """One declared input."""

    artifact: str
    source: str
    required: bool


@dataclass(frozen=True)
class Output:
    """One declared output."""

    artifact: str
    path: str | None


class SubsetParserUnavailableError(RuntimeError):
    """Skillforge's stdlib frontmatter parser is missing or fails to import."""


def _load_subset_parser() -> ModuleType:
    """Import skillforge's parser without leaving its directory or siblings behind.

    The parser imports `_path_guard` from its own directory. Leaving that
    directory on sys.path, or `_path_guard` in sys.modules, would make a later
    import of another tree's skillforge scripts pick up this copy.

    Raises SubsetParserUnavailableError when the parser file is absent or its import
    fails, so a caller can map the failure to its own config exit.
    """
    parser_file = _SUBSET_PARSER_DIR / "_conformance_parse.py"
    if not parser_file.is_file():
        raise SubsetParserUnavailableError(f"skillforge parser not found: {parser_file}")
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    sys.path.insert(0, str(_SUBSET_PARSER_DIR))
    try:
        spec = importlib.util.spec_from_file_location("_artifact_flow_subset_parser", parser_file)
        if spec is None or spec.loader is None:
            raise SubsetParserUnavailableError(f"cannot load {parser_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(spec.name, None)
            raise SubsetParserUnavailableError(f"cannot import {parser_file}: {exc}") from exc
        return module
    finally:
        sys.path[:] = saved_path
        for added in set(sys.modules) - saved_modules:
            origin = getattr(sys.modules[added], "__file__", None)
            if origin and Path(origin).resolve().parent == _SUBSET_PARSER_DIR.resolve():
                del sys.modules[added]


_parser_cache: list[ModuleType] = []


def subset_parser() -> ModuleType:
    """Return skillforge's parser, loading it on first use."""
    if not _parser_cache:
        _parser_cache.append(_load_subset_parser())
    return _parser_cache[0]


def subset_defect(rel: str, text: str) -> str | None:
    """Return why skillforge's stdlib parser cannot read the frontmatter, or None."""
    parser = subset_parser()
    raw, _body, error = parser.split_frontmatter(text)
    if raw is None:
        return None if error is None else f"{rel}: {error}"
    try:
        parser.parse_frontmatter(raw)
    except (parser.UnsupportedError, parser.ParseError) as exc:
        return (
            f"{rel}: skillforge's stdlib frontmatter parser refuses this template ({exc}); "
            "use block mappings, and key lists by name instead of listing mappings"
        )
    return None


def _name_defect(rel: str, field: str, artifact: object) -> str | None:
    """Return why a key is not a usable artifact name, or None."""
    if isinstance(artifact, bool):
        return (
            f"{rel}: {field} key {artifact!r} is a YAML 1.1 boolean "
            "(yes, no, on, off); rename the artifact"
        )
    if not isinstance(artifact, str):
        return f"{rel}: {field} key {artifact!r} must be a string artifact name"
    if not ARTIFACT_RE.fullmatch(artifact):
        return f"{rel}: {field}.{artifact!r}: artifact name must be lowercase kebab case"
    return None


def _option_defects(where: str, field: str, entry: dict[object, object]) -> list[str]:
    """Return defects in one entry's options."""
    allowed = INPUT_KEYS if field == "inputs" else OUTPUT_KEYS
    unknown = [key for key in entry if key not in allowed]
    defects = [f"{where} has unknown key {key!r}" for key in sorted(unknown, key=repr)]
    if field == "outputs" and "path" in entry:
        path = entry["path"]
        if not isinstance(path, str):
            defects.append(f"{where}.path must be a string")
        elif not PATH_RE.fullmatch(path):
            defects.append(
                f"{where}.path {path!r} must be a lowercase path relative to the artifact root"
            )
    if field == "inputs":
        source = entry.get("source", "skill")
        if not isinstance(source, str) or source not in SOURCES:
            defects.append(f"{where}.source {source!r} must be one of {', '.join(SOURCES)}")
        if "required" in entry and not isinstance(entry["required"], bool):
            defects.append(f"{where}.required must be true or false")
    return defects


def entry_defects(rel: str, field: str, artifact: object, entry: object) -> list[str]:
    """Return shape defects for one `inputs` or `outputs` entry.

    An entry is `artifact-name:` with no value (all defaults) or with a
    mapping of the optional keys.
    """
    name_problem = _name_defect(rel, field, artifact)
    if name_problem and not isinstance(artifact, str):
        return [name_problem]
    defects = [name_problem] if name_problem else []
    where = f"{rel}: {field}.{artifact!r}"
    if entry is None:
        return defects
    if not isinstance(entry, dict):
        return [*defects, f"{where} must be empty or a mapping, not {type(entry).__name__}"]
    return defects + _option_defects(where, field, entry)


def _mapping_or_defect(rel: str, field: str, value: object) -> list[str]:
    """Return the defects of one `inputs` or `outputs` value, keyed by artifact."""
    if not isinstance(value, dict):
        return [
            f"{rel}: {field} must be a mapping keyed by artifact name, not {type(value).__name__}"
        ]
    defects: list[str] = []
    for artifact, entry in value.items():
        defects.extend(entry_defects(rel, field, artifact, entry))
    return defects


def parse_inputs(rel: str, value: object) -> tuple[tuple[Input, ...], list[str]]:
    """Return typed inputs, or no inputs and the defects that prevented them."""
    if value is None:
        return (), []
    defects = _mapping_or_defect(rel, "inputs", value)
    if defects or not isinstance(value, dict):
        return (), defects
    inputs = []
    for name, entry in value.items():
        options = entry or {}
        inputs.append(
            Input(
                artifact=str(name),
                source=str(options.get("source", "skill")),
                required=bool(options.get("required", True)),
            )
        )
    return tuple(inputs), []


def parse_outputs(rel: str, value: object) -> tuple[tuple[Output, ...], list[str]]:
    """Return typed outputs, or no outputs and the defects that prevented them."""
    if value is None:
        return (), []
    defects = _mapping_or_defect(rel, "outputs", value)
    if defects or not isinstance(value, dict):
        return (), defects
    outputs = []
    for name, entry in value.items():
        path = (entry or {}).get("path")
        outputs.append(Output(artifact=str(name), path=path if isinstance(path, str) else None))
    return tuple(outputs), []
