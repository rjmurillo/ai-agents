#!/usr/bin/env python3
"""Copy ``src/claude/agents/`` into a host plugin tree with a frontmatter allow-list.

ADR-115 Decision 2. The Cursor plugin tree reads agents from ``agents/*.md``
with frontmatter ``name``, ``description``, ``model``, ``readonly`` and
``is_background`` (https://cursor.com/docs/context/subagents). The Claude agent
files carry more keys (``tools``, ``metadata``, ``argument-hint``, ``model``,
and others) that Cursor does not document, so this copy keeps only the keys the
platform stanza lists.

A platform opts in by setting ``artifacts.agents.frontmatterKeep``. The
Copilot-family generator (``build/generate_agents.py``) skips such a platform,
because it renders from ``templates/agents/`` and this module renders from the
already-compiled Claude plugin tree.

Stanza keys (all under ``artifacts.agents``):

``sourceDir``         plugin-tree agent directory to read (``src/claude/agents``)
``outputDir``         directory to write (``src/cursor/agents``)
``frontmatterKeep``   top-level frontmatter keys to keep, in output order
``deriveReadonly``    when true, emit ``readonly: true`` for an agent whose
                      ``tools`` (list or comma-separated string) names only
                      read-only tools, and do not ship an agent whose ``tools``
                      is restricted (including empty) but not all read-only
``excludeFilenames``  source file names to skip
``skipToolRestricted`` when true, do not ship an agent whose frontmatter declares
                      ``tools`` (list or comma string), and append a paragraph to
                      every shipped body naming the agents left out (Codex agent
                      files cannot restrict tools, ADR-115 Decision 7). Requires
                      ``frontmatterKeep``; excludes ``deriveReadonly: true``.
``noSubagentsNote``   when true, a ``markdown`` agent whose source sets
                      ``disallowedTools: Agent`` gets the same short ``Subagents``
                      section ``codex-toml`` always adds, because the host cannot
                      enforce that deny (Muse Code, ADR-115 Decision 8).
``outputFormat``      ``markdown`` (default) or ``codex-toml``. ``codex-toml`` writes
                      ``<stem>.toml`` with the keys ``name``, ``description`` and
                      ``developer_instructions`` (the body). ``frontmatterKeep`` must
                      be exactly ``[name, description]`` for it.
``bodyReplace``       map of agent file name to ``{from: to}`` literal edits to its body
                      (issue #7226). Cursor ships no ``security`` agent, so a
                      line that hands work to one is reworded for Cursor. Each
                      ``from`` must occur exactly once in its file, and each
                      ``file`` must exist, so a stale entry fails the build.

``readonly`` is derived, never guessed: an agent without a ``tools`` list gets
no ``readonly`` key (it is unrestricted in Claude too). Cursor documents no
tool allow-list for subagents, so ``readonly: true`` is the only tool
restriction it can carry. ADR-115 Decision 3: an agent whose ``tools`` list is
non-empty but not all read-only has a restriction ``readonly`` cannot express,
and copying it would hand it every tool, shell included. With
``deriveReadonly`` on, such an agent is not emitted, a skip line names it, and
the prune step removes a copy generated earlier (``--check`` reports it as
drift).

Different from ``generate_agents.py``: no handoff or memory-prefix rewrite and
no model pin. ``model`` is not in the keep list, so Cursor's default
(``inherit``) applies, and ADR-080's pin rules do not reach this tree.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))

from agent_toml import (  # noqa: E402
    FORMAT_CODEX_TOML,
    FORMAT_MARKDOWN,
    NO_SUBAGENTS,
    CodexOutputError,
    check_names_match_stems,
    forbids_subagents,
    not_installed_paragraph,
    read_output_options,
    render_codex_toml,
    unenforceable_disallowed,
)
from agent_tools import (  # noqa: E402
    AgentCopyError,
    declared_tools,
    derive_readonly,
    has_inexpressible_restriction,
)
from agent_tools import is_readonly_tool as is_readonly_tool  # noqa: E402  re-export
from atomic_write import publish_bytes_preserving_mode  # noqa: E402
from generate_agents_common import read_yaml_frontmatter  # noqa: E402
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import ConfigError, load_platform_config, validate_relative_path  # noqa: E402

T = TypeVar("T")
KEEP_KEY = "frontmatterKeep"
REPLACE_KEY = "bodyReplace"
_READONLY_KEY = "readonly"
_READONLY_SKIP_REASON = "tools list restricts it beyond what readonly can express"
_SOURCE_SUFFIX = ".md"
_DEFAULT_EXCLUDES = ("AGENTS.md", "CLAUDE.md")


@dataclass
class AgentCopyResult:
    """Outcome of one copy run."""

    inputs: int = 0
    written: int = 0
    drift: list[str] = field(default_factory=list)
    pruned: int = 0
    skipped: list[str] = field(default_factory=list)


def uses_agent_tree_copy(stanza: object) -> bool:
    """True when an ``artifacts.agents`` stanza opts in to this copy."""
    return isinstance(stanza, dict) and KEEP_KEY in stanza


def parse_agent(text: str, source: str) -> tuple[dict[str, object], str]:
    """Return ``(frontmatter mapping, body)`` for one agent file."""
    parsed = read_yaml_frontmatter(text)
    if parsed is None:
        raise AgentCopyError(f"{source}: no frontmatter block")
    try:
        loaded = yaml.safe_load(parsed["frontmatter_raw"])
    except yaml.YAMLError as exc:
        raise AgentCopyError(f"{source}: unparseable frontmatter: {exc}") from exc
    if not isinstance(loaded, dict):
        raise AgentCopyError(f"{source}: frontmatter is not a mapping")
    return loaded, parsed["body"]


@dataclass(frozen=True)
class RenderSpec:
    """How one platform renders every agent: the keys to keep and the output form."""

    keep: list[str]
    derive_readonly: bool = False
    output_format: str = FORMAT_MARKDOWN
    appendix: str = ""
    no_subagents_note: bool = False


def _as_copy_error(call: Callable[[], T]) -> T:
    """Run ``call``, turning a :class:`CodexOutputError` into an :class:`AgentCopyError`."""
    try:
        return call()
    except CodexOutputError as exc:
        raise AgentCopyError(str(exc)) from exc


def render_parsed(
    loaded: dict[str, object],
    body: str,
    source: str,
    spec: RenderSpec,
    body_edits: list[tuple[str, str]] | None = None,
) -> str | None:
    """Render one parsed agent; ``None`` when ``deriveReadonly`` says it must not ship.

    A ``None`` return means the agent carries a tool restriction ``readonly``
    cannot express (ADR-115 Decision 3). ``body_edits`` are literal
    ``(from, to)`` edits applied to the body only, so text that also appears in
    the frontmatter can never be rewritten by mistake. ``spec.appendix`` is
    added after the edits; ``codex-toml`` returns a TOML document.
    """
    try:
        if spec.derive_readonly and has_inexpressible_restriction(loaded):
            return None
    except AgentCopyError as exc:
        raise AgentCopyError(f"{source}: {exc}") from exc
    kept = {key: loaded[key] for key in spec.keep if key in loaded}
    if spec.derive_readonly and derive_readonly(loaded):
        kept[_READONLY_KEY] = True
    if body_edits:
        body = apply_body_replacements(body, body_edits, source)
    if spec.output_format == FORMAT_CODEX_TOML:
        unenforced = unenforceable_disallowed(loaded)
        if unenforced:
            raise AgentCopyError(
                f"{source}: `disallowedTools` names {', '.join(unenforced)}, "
                "which a Codex agent file cannot enforce; only `Agent` is supported"
            )
        if forbids_subagents(loaded):
            body = body.rstrip("\n") + NO_SUBAGENTS
    elif spec.no_subagents_note and forbids_subagents(loaded):
        body = body.rstrip("\n") + NO_SUBAGENTS
    if spec.appendix:
        body = body.rstrip("\n") + spec.appendix
    if spec.output_format == FORMAT_CODEX_TOML:
        toml_text: str = _as_copy_error(lambda: render_codex_toml(kept, body, source))
        return toml_text
    dumped = yaml.safe_dump(
        kept, sort_keys=False, allow_unicode=True, default_flow_style=False, width=10**9
    )
    return f"---\n{dumped}---\n{body}"


def render_agent(
    text: str,
    keep: list[str],
    *,
    derive_readonly_flag: bool,
    source: str,
    body_edits: list[tuple[str, str]] | None = None,
) -> str | None:
    """Parse ``text`` and render it with :func:`render_parsed`."""
    loaded, body = parse_agent(text, source)
    spec = RenderSpec(keep, derive_readonly_flag)
    return render_parsed(loaded, body, source, spec, body_edits)


def _body_replacements(
    stanza: dict[str, object], source_dir: Path, excludes: frozenset[str]
) -> dict[str, list[tuple[str, str]]]:
    """Return ``{file name: [(from, to), ...]}`` from the ``bodyReplace`` mapping.

    Fails when a named file is not in ``source_dir`` or is excluded from the copy.
    """
    raw = stanza.get(REPLACE_KEY, {})
    problem = f"`artifacts.agents.{REPLACE_KEY}` must map agent file names to {{from: to}} maps"
    if not isinstance(raw, dict):
        raise AgentCopyError(problem)
    edits: dict[str, list[tuple[str, str]]] = {}
    for file, pairs in raw.items():
        if not isinstance(file, str) or not isinstance(pairs, dict) or not pairs:
            raise AgentCopyError(problem)
        if not all(isinstance(k, str) and k and isinstance(v, str) for k, v in pairs.items()):
            raise AgentCopyError(problem)
        edits[file] = list(pairs.items())
    missing = sorted(set(edits) - {p.name for p in source_dir.glob(f"*{_SOURCE_SUFFIX}")})
    if missing:
        raise AgentCopyError(f"bodyReplace names agents not in {source_dir}: {missing}")
    excluded = sorted(set(edits) & excludes)
    if excluded:
        raise AgentCopyError(
            f"bodyReplace names agents that are excluded from the copy: {excluded}"
        )
    return edits


def apply_body_replacements(text: str, edits: list[tuple[str, str]], source: str) -> str:
    """Apply literal edits; each ``from`` must occur exactly once in ``text``."""
    for old, new in edits:
        found = text.count(old)
        if found != 1:
            raise AgentCopyError(
                f"{source}: bodyReplace text occurs {found} times, expected 1: {old!r}"
            )
        text = text.replace(old, new)
    return text


def _read_stanza(config_path: Path) -> dict[str, object] | None:
    try:
        cfg = load_platform_config(config_path)
    except ConfigError as exc:
        raise AgentCopyError(str(exc)) from exc
    artifacts = cfg.get("artifacts")
    stanza = artifacts.get("agents") if isinstance(artifacts, dict) else None
    return stanza if uses_agent_tree_copy(stanza) else None


def _keep_list(stanza: dict[str, object]) -> list[str]:
    keep = stanza[KEEP_KEY]
    if not isinstance(keep, list) or not keep or not all(isinstance(k, str) for k in keep):
        raise AgentCopyError(
            "`artifacts.agents.frontmatterKeep` must be a non-empty list of strings"
        )
    return list(keep)


def _resolve_dirs(repo_root: Path, stanza: dict[str, object]) -> tuple[Path, Path]:
    for key in ("sourceDir", "outputDir"):
        errors = validate_relative_path(f"artifacts.agents.{key}", stanza.get(key))
        if errors:
            raise AgentCopyError("; ".join(errors))
    return repo_root / str(stanza["sourceDir"]), repo_root / str(stanza["outputDir"])


def _excludes(stanza: dict[str, object]) -> frozenset[str]:
    raw = stanza.get("excludeFilenames", list(_DEFAULT_EXCLUDES))
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise AgentCopyError("`artifacts.agents.excludeFilenames` must be a list of strings")
    return frozenset(raw)


def generate_agent_copies(
    repo_root: Path, config_path: Path, *, check: bool = False, what_if: bool = False
) -> AgentCopyResult | None:
    """Render one platform's agent copy; ``None`` when the platform does not opt in.

    ``check`` writes nothing and records every differing file in ``drift``.
    ``what_if`` writes nothing and prints what would change. Raises
    :class:`AgentCopyError` for a bad stanza or source file.
    """
    stanza = _read_stanza(config_path)
    if stanza is None:
        return None
    keep = _keep_list(stanza)
    options = _as_copy_error(lambda: read_output_options(stanza))
    source_dir, output_dir = _resolve_dirs(repo_root, stanza)
    if output_dir.is_symlink():
        # A redirected output folder would let the prune step delete files outside the repo.
        raise AgentCopyError(
            f"{output_dir}: output directory is a symlink; refusing to write or prune"
        )
    if not source_dir.is_dir():
        raise AgentCopyError(f"sourceDir not found: {source_dir}")
    excludes = _excludes(stanza)
    replacements = _body_replacements(stanza, source_dir, excludes)
    sources = [p for p in sorted(source_dir.glob(f"*{_SOURCE_SUFFIX}")) if p.name not in excludes]
    if not sources:
        raise AgentCopyError(f"no agent files found under {source_dir}")
    parsed = {src: parse_agent(src.read_text(encoding="utf-8"), src.as_posix()) for src in sources}
    _as_copy_error(
        lambda: check_names_match_stems(
            (src.stem, fm.get("name")) for src, (fm, _) in parsed.items()
        )
    )
    restricted = (
        {src for src, (fm, _) in parsed.items() if declared_tools_of(fm, src) is not None}
        if options.skip_restricted
        else set()
    )
    spec = RenderSpec(
        keep,
        stanza.get("deriveReadonly") is True,
        options.fmt,
        not_installed_paragraph(sorted(src.stem for src in restricted)) if restricted else "",
        options.no_subagents_note,
    )
    result = AgentCopyResult(inputs=len(sources))
    expected: set[str] = set()
    for src, (loaded, body) in parsed.items():
        rendered = (
            None
            if src in restricted
            else render_parsed(loaded, body, src.as_posix(), spec, replacements.get(src.name))
        )
        if rendered is None:
            if src.name in replacements:
                raise AgentCopyError(
                    f"bodyReplace names {src.name}, which is skipped because its tools list "
                    "restricts it"
                )
            result.skipped.append(src.name)
            why = "declares a tools list" if options.skip_restricted else _READONLY_SKIP_REASON
            print(f"  SKIPPED: {src.name} ({why})")
            continue
        expected.add(f"{src.stem}{options.suffix}")
        _emit(
            output_dir / f"{src.stem}{options.suffix}",
            rendered,
            result,
            check=check,
            what_if=what_if,
        )
    _prune(output_dir, expected, options.suffix, result, check=check, what_if=what_if)
    return result


def declared_tools_of(loaded: dict[str, object], src: Path) -> list[object] | None:
    """:func:`declared_tools` with the source path added to its error."""
    try:
        tools: list[object] | None = declared_tools(loaded)
        return tools
    except AgentCopyError as exc:
        raise AgentCopyError(f"{src.as_posix()}: {exc}") from exc


def _emit(
    target: Path, rendered: str, result: AgentCopyResult, *, check: bool, what_if: bool
) -> None:
    reason = regen_detect_reason(target)
    if reason is not None:
        print(f"  NOTICE: skipped {target} (NO-REGEN: {reason})")
        return
    current = target.read_text(encoding="utf-8") if target.is_file() else None
    if current == rendered:
        return
    if check:
        result.drift.append(target.as_posix())
        return
    if what_if:
        print(f"  Would write: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    publish_bytes_preserving_mode(target, rendered.encode("utf-8"))
    result.written += 1


def _prune(
    output_dir: Path,
    expected: set[str],
    suffix: str,
    result: AgentCopyResult,
    *,
    check: bool,
    what_if: bool,
) -> None:
    if not output_dir.is_dir():
        return
    for existing in sorted(output_dir.glob(f"*{suffix}")):
        if existing.name in expected or regen_detect_reason(existing) is not None:
            continue
        if check:
            result.drift.append(existing.as_posix())
        elif not what_if:
            existing.unlink()
            result.pruned += 1
