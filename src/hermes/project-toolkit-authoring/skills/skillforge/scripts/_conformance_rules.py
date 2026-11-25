"""The agentskills.io conformance catalog: the Rule type and the specification rules.

One entry per rule in the specification and the skill-creation guides. Each
entry names its level as the source page words it (MUST for "must", SHOULD for
"should" or a recommendation), the page and section it comes from, and either
a static check or None. None marks a guideline no script can judge; the
conformance report lists it for human review instead of guessing.

A deviation is a rule this project departs from on purpose. The `project`
profile reports it as DEVIATION with the reason; the `spec` profile does not.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import _conformance_checks as c
from _conformance_parse import SkillDoc

SPEC = "https://agentskills.io/specification"
SCRIPTS = "https://agentskills.io/skill-creation/using-scripts"
PRACTICES = "https://agentskills.io/skill-creation/best-practices"
DESCRIPTIONS = "https://agentskills.io/skill-creation/optimizing-descriptions"
EVALS = "https://agentskills.io/skill-creation/evaluating-skills"

LEVELS = ("MUST", "SHOULD", "MAY")


@dataclass(frozen=True)
class Rule:
    id: str
    level: str
    source: str
    summary: str
    check: Callable[[SkillDoc], list[str]] | None = None
    deviation: str | None = None

    @property
    def manual(self) -> bool:
        return self.check is None


_EXTRA_FIELDS = (
    "Project skills carry harness fields (version, user-invocable, model, and others) "
    "at the top level, where Claude Code and Copilot CLI read them."
)
_METADATA = (
    "Project skills nest a capability declaration under metadata (ADR-110), so some "
    "values are mappings or lists."
)
_ALLOWED_TOOLS = (
    "Project skills write allowed-tools as a YAML list, the form the harness generators read."
)

SPEC_RULES: tuple[Rule, ...] = (
    # Specification ----------------------------------------------------------
    Rule(
        "spec.skill-md.present",
        "MUST",
        f"{SPEC}#directory-structure",
        "The skill directory contains SKILL.md.",
        c.skill_md_present,
    ),
    Rule(
        "spec.frontmatter.delimited",
        "MUST",
        f"{SPEC}#skill-md-format",
        "SKILL.md starts with YAML frontmatter between '---' lines.",
        c.frontmatter_delimited,
    ),
    Rule(
        "spec.frontmatter.mapping",
        "MUST",
        f"{SPEC}#skill-md-format",
        "The frontmatter is a valid YAML mapping.",
        c.frontmatter_mapping,
    ),
    Rule(
        "spec.frontmatter.known-fields",
        "MUST",
        f"{SPEC}#validation",
        "Frontmatter holds only spec fields; skills-ref rejects any other key.",
        c.frontmatter_known_fields,
        deviation=_EXTRA_FIELDS,
    ),
    Rule(
        "spec.name.present",
        "MUST",
        f"{SPEC}#name-field",
        "name is present and non-empty.",
        c.name_present,
    ),
    Rule(
        "spec.name.max-length",
        "MUST",
        f"{SPEC}#name-field",
        "name is at most 64 characters.",
        c.name_max_length,
    ),
    Rule(
        "spec.name.charset",
        "MUST",
        f"{SPEC}#name-field",
        "name holds only lowercase letters, digits, and hyphens.",
        c.name_charset,
    ),
    Rule(
        "spec.name.hyphen-edges",
        "MUST",
        f"{SPEC}#name-field",
        "name does not start or end with a hyphen.",
        c.name_hyphen_edges,
    ),
    Rule(
        "spec.name.no-double-hyphen",
        "MUST",
        f"{SPEC}#name-field",
        "name does not contain consecutive hyphens.",
        c.name_no_double_hyphen,
    ),
    Rule(
        "spec.name.matches-directory",
        "MUST",
        f"{SPEC}#name-field",
        "name matches the parent directory name.",
        c.name_matches_directory,
    ),
    Rule(
        "spec.description.present",
        "MUST",
        f"{SPEC}#description-field",
        "description is present and non-empty.",
        c.description_present,
    ),
    Rule(
        "spec.description.max-length",
        "MUST",
        f"{SPEC}#description-field",
        "description is at most 1024 characters.",
        c.description_max_length,
    ),
    Rule(
        "spec.description.what-and-when",
        "SHOULD",
        f"{SPEC}#description-field",
        "description says what the skill does and when to use it.",
    ),
    Rule(
        "spec.description.keywords",
        "SHOULD",
        f"{SPEC}#description-field",
        "description includes keywords that help agents find relevant tasks.",
    ),
    Rule(
        "spec.license.short",
        "SHOULD",
        f"{SPEC}#license-field",
        "license is short: a license name or the name of a bundled license file.",
    ),
    Rule(
        "spec.compatibility.length",
        "MUST",
        f"{SPEC}#compatibility-field",
        "compatibility, when present, is 1 to 500 characters.",
        c.compatibility_length,
    ),
    Rule(
        "spec.compatibility.only-when-needed",
        "SHOULD",
        f"{SPEC}#compatibility-field",
        "compatibility appears only for specific environment requirements.",
    ),
    Rule(
        "spec.metadata.string-map",
        "SHOULD",
        f"{SPEC}#metadata-field",
        "metadata maps string keys to string values; quote numbers and booleans.",
        c.metadata_string_map,
        deviation=_METADATA,
    ),
    Rule(
        "spec.metadata.unique-keys",
        "SHOULD",
        f"{SPEC}#metadata-field",
        "metadata key names are unique enough to avoid conflicts between clients.",
    ),
    Rule(
        "spec.allowed-tools.string",
        "SHOULD",
        f"{SPEC}#allowed-tools-field",
        "allowed-tools is a space-separated string (experimental field).",
        c.allowed_tools_string,
        deviation=_ALLOWED_TOOLS,
    ),
    Rule(
        "spec.body.max-lines",
        "SHOULD",
        f"{SPEC}#progressive-disclosure",
        "SKILL.md stays under 500 lines.",
        c.body_max_lines,
    ),
    Rule(
        "spec.body.token-budget",
        "SHOULD",
        f"{SPEC}#progressive-disclosure",
        "The SKILL.md body stays under about 5000 tokens.",
        c.body_token_budget,
    ),
    Rule(
        "spec.references.relative",
        "SHOULD",
        f"{SPEC}#file-references",
        "File references are relative paths from the skill root.",
        c.references_relative,
    ),
    Rule(
        "spec.references.resolve",
        "SHOULD",
        f"{SPEC}#file-references",
        "Every relative link in SKILL.md points to a file in the skill.",
        c.references_resolve,
    ),
    Rule(
        "spec.references.one-level",
        "SHOULD",
        f"{SPEC}#file-references",
        "File references stay one level deep; no file is reachable only through a chain.",
        c.references_one_level,
    ),
    Rule(
        "spec.references.focused",
        "SHOULD",
        f"{SPEC}#references",
        "Each reference file stays focused, so loading it costs little context.",
    ),
    Rule(
        "spec.scripts.dependencies",
        "SHOULD",
        f"{SPEC}#scripts",
        "Scripts are self-contained or document their dependencies.",
    ),
    Rule(
        "spec.scripts.error-messages",
        "SHOULD",
        f"{SPEC}#scripts",
        "Scripts print helpful error messages.",
    ),
    Rule(
        "spec.scripts.edge-cases",
        "SHOULD",
        f"{SPEC}#scripts",
        "Scripts handle edge cases gracefully.",
    ),
)
