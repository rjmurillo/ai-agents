"""Codex output rules for ``agent_tree_copy.py`` (ADR-115 Decision 7).

A Codex custom agent is one TOML file with ``name``, ``description`` and
``developer_instructions``. This module owns everything specific to that
output: the stanza keys ``outputFormat`` and ``skipToolRestricted`` and their
validation (one rule set, used by the build and by the schema validator), the
TOML basic-string escaper, the file renderer, the name-to-stem check, and the
paragraph appended to each body when agents are left out. A body whose source sets
``disallowedTools: Agent`` also gets a short ``Subagents`` section (``NO_SUBAGENTS``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

CODEX_KEEP = ["name", "description"]
FORMAT_KEY = "outputFormat"
SKIP_KEY = "skipToolRestricted"
NOTE_KEY = "noSubagentsNote"
FORMAT_MARKDOWN = "markdown"
FORMAT_CODEX_TOML = "codex-toml"
FORMATS = (FORMAT_MARKDOWN, FORMAT_CODEX_TOML)
_TOML_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


class CodexOutputError(Exception):
    """A stanza option or an agent cannot produce Codex output."""


def toml_basic_string(value: str) -> str:
    """Return ``value`` as a single-line TOML 1.0 basic string, quotes included.

    Escapes ``\\``, ``"`` and the control characters U+0000-U+001F and U+007F
    (``\\b \\t \\n \\f \\r`` or ``\\uXXXX``). Every other character, including
    non-BMP ones such as emoji, stays raw UTF-8. ``json.dumps`` is not a
    substitute: it emits surrogate pairs (invalid TOML) and leaves U+007F raw.
    """
    out: list[str] = []
    for char in value:
        if char in _TOML_ESCAPES:
            out.append(_TOML_ESCAPES[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def render_codex_toml(kept: dict[str, object], body: str, source: str) -> str:
    for key in CODEX_KEEP:
        if not isinstance(kept.get(key), str):
            raise CodexOutputError(f"{source}: frontmatter `{key}` must be a string for codex-toml")
    return (
        f"name = {toml_basic_string(str(kept['name']))}\n"
        f"description = {toml_basic_string(str(kept['description']))}\n"
        f"developer_instructions = {toml_basic_string(body)}\n"
    )


# Mirrors the Claude restriction `disallowedTools: Agent`. Codex cannot enforce it, so
# the build states it in the body. The model may ignore it; it is not a block.
NO_SUBAGENTS = "\n\n## Subagents\n\nDo not start subagents. Do the work in this session.\n"


def forbids_subagents(loaded: dict[str, object]) -> bool:
    """True when the Claude source sets ``disallowedTools: Agent``, which Codex cannot enforce."""
    raw = loaded.get("disallowedTools")
    names = raw if isinstance(raw, list) else str(raw or "").split(",")
    return "Agent" in [str(name).strip() for name in names]


def unenforceable_disallowed(loaded: dict[str, object]) -> list[str]:
    """Names in ``disallowedTools`` other than ``Agent``, which Codex cannot enforce.

    ``Agent`` is handled by :data:`NO_SUBAGENTS`. Any other name would ship as an
    unrestricted agent, so the build refuses it instead.
    """
    raw = loaded.get("disallowedTools")
    names = raw if isinstance(raw, list) else str(raw or "").split(",")
    stripped = [str(name).strip() for name in names]
    return [name for name in stripped if name and name != "Agent"]


def not_installed_paragraph(skipped_stems: list[str]) -> str:
    """Return the paragraph appended to each body when agents were left out.

    The list is the sorted skip list passed in, never a fixed set of names.
    When ``security`` is on it, the paragraph also says not to present a
    self-review as a security agent's review.
    """
    names = ", ".join(f"`{stem}`" for stem in sorted(skipped_stems))
    text = (
        "\n\n## Agents not installed on this host\n\n"
        f"These agents are not installed on this host: {names}. "
        "When a step above hands work to one of them, do that step yourself "
        "in this session and say that you did. "
        "A step you do yourself is a self-review, not an independent review, so report it as one. "
        "It does not satisfy a review gate: name the gate as unreviewed in your completion report. "
        "When you are asked to review or challenge work, set aside the author's reasoning "
        "and judge the artifact itself."
    )
    # A skipped `security` agent gets its own sentence: a self-review must not pass as its review.
    if "security" in skipped_stems:
        text += (
            " If the step is a security review or clears a security flag, do not mark it done: "
            "state that no security agent reviewed it and leave the flag open for the user."
        )
    return text + "\n"


def output_option_errors(name: str, stanza: dict[str, object]) -> list[str]:
    """Return problems with ``skipToolRestricted`` and ``outputFormat`` on a stanza.

    ``name`` is the artifact name used in the messages. The caller has already
    checked that ``frontmatterKeep`` is present.
    """
    errors: list[str] = []
    where = f"`artifacts.{name}."
    skip = stanza.get(SKIP_KEY, False)
    if not isinstance(skip, bool):
        errors.append(f"{where}{SKIP_KEY}`: must be a boolean")
    elif skip and stanza.get("deriveReadonly") is True:
        errors.append(f"{where}{SKIP_KEY}`: cannot combine with `deriveReadonly: true`")
    if not isinstance(stanza.get(NOTE_KEY, False), bool):
        errors.append(f"{where}{NOTE_KEY}`: must be a boolean")
    fmt = stanza.get(FORMAT_KEY, FORMAT_MARKDOWN)
    if fmt not in FORMATS:
        errors.append(f"{where}{FORMAT_KEY}`: must be `markdown` or `codex-toml`")
    elif fmt == FORMAT_CODEX_TOML:
        if stanza.get("frontmatterKeep") != CODEX_KEEP:
            errors.append(
                f"{where}{FORMAT_KEY}`: `codex-toml` needs `frontmatterKeep` of exactly "
                "[name, description]"
            )
        # The renderer has no `readonly` field to write. A read-only source would ship
        # with the parent's permissions, so the combination is refused up front.
        if stanza.get("deriveReadonly") is True:
            errors.append(
                f"{where}{FORMAT_KEY}`: `codex-toml` cannot combine with `deriveReadonly: true`"
            )
        # A Codex agent file cannot limit tools, so a source with a `tools` list must
        # not ship. Without the skip, such an agent would ship unrestricted.
        if skip is False:
            errors.append(
                f"{where}{FORMAT_KEY}`: `codex-toml` needs `{SKIP_KEY}: true`, "
                "because a Codex agent file cannot restrict tools"
            )
    return errors


@dataclass(frozen=True)
class OutputOptions:
    """Validated Codex-related options of one agents stanza."""

    fmt: str
    skip_restricted: bool
    no_subagents_note: bool = False

    @property
    def suffix(self) -> str:
        return ".toml" if self.fmt == FORMAT_CODEX_TOML else ".md"


def read_output_options(stanza: dict[str, object]) -> OutputOptions:
    """Return the options; raise :class:`CodexOutputError` on the first bad one."""
    errors = output_option_errors("agents", stanza)
    if errors:
        raise CodexOutputError(errors[0])
    return OutputOptions(
        str(stanza.get(FORMAT_KEY, FORMAT_MARKDOWN)),
        bool(stanza.get(SKIP_KEY, False)),
        stanza.get(NOTE_KEY) is True,
    )


def check_names_match_stems(named: Iterable[tuple[str, object]]) -> None:
    """Fail when an agent's frontmatter ``name`` differs from its file stem.

    Run over every source agent, shipped or skipped. Distinct stems then give
    distinct names, so no separate duplicate-name check exists.
    """
    for stem, name in named:
        if name != stem:
            raise CodexOutputError(f"{stem}.md: frontmatter name {name!r} differs from file stem")
