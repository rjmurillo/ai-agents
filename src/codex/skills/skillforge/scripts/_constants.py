#!/usr/bin/env python3
"""
_constants.py - Shared constants for skill validation scripts

These constants are used by:
- quick_validate.py (packaging validation)
- validate-skill.py (full structural validation)
- discover_skills.py (skill indexing)
"""

# ===========================================================================
# FRONTMATTER PROPERTIES
# ===========================================================================

# Required fields
REQUIRED_PROPERTIES = {
    "name",  # Skill identifier (hyphen-case, max 64 chars)
    "description",  # Discovery text (max 1024 chars, no angle brackets)
}

# Optional fields
OPTIONAL_PROPERTIES = {
    "license",  # Distribution license (MIT, Apache-2.0, etc.)
    "allowed-tools",  # Tool restrictions: space-separated string (spec), comma-separated, or YAML list
    "compatibility",  # Environment requirements (agentskills.io spec, 1-500 chars)
    "metadata",  # Custom fields (author, domains, etc.)
    "model",  # Optional model alias; omit to inherit, bare alias only, no versioned id
    "model-rationale",  # ADR-080: justification for a bare cost-tier alias pin
    "context",  # Execution context ('fork' for isolated sub-agent)
    "agent",  # Agent type when context: fork
    "hooks",  # Lifecycle hooks (PreToolUse, PostToolUse, Stop)
    "user-invocable",  # Slash menu visibility (default: true)
    "version",  # Semantic version (e.g., 1.0.0)
    "argument-hint",  # Slash-command argument hint(s) for user-invocable skills
    "size-exception",  # Opt out of the 500-line skill_size block (justified overage)
}

# All allowed properties
ALLOWED_PROPERTIES = REQUIRED_PROPERTIES | OPTIONAL_PROPERTIES

# Recommended but optional fields
RECOMMENDED_PROPERTIES = {"license"}

# ===========================================================================
# VALIDATION CONSTANTS
# ===========================================================================

# Valid agent types for context: fork
VALID_AGENT_TYPES = {"Explore", "Plan", "general-purpose"}

# Valid hook event names
VALID_HOOK_EVENTS = {"PreToolUse", "PostToolUse", "Stop"}

# Valid hook types
VALID_HOOK_TYPES = {"command", "prompt"}

# Known tool names for allowed-tools validation (warning only, not error)
KNOWN_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "Write",
    "Edit",
    "Bash",
    "Task",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
    "NotebookEdit",
    "AskUserQuestion",  # Claude Code tool name
}

# Field constraints
NAME_MAX_LENGTH = 64
DESCRIPTION_MAX_LENGTH = 1024
COMPATIBILITY_MAX_LENGTH = 500  # agentskills.io spec: compatibility is 1-500 chars
# agentskills.io progressive disclosure: keep the SKILL.md body under about 5,000
# tokens. Estimated as characters / 4, a conservative rule of thumb that
# needs no tokenizer dependency.
BODY_TOKEN_BUDGET = 5000
CHARS_PER_TOKEN_ESTIMATE = 4
# agentskills.io progressive disclosure: keep the main SKILL.md under 500 lines.
BODY_MAX_LINES = 500

# Skill name regex (unified across all validators), per the agentskills.io spec
# - Lowercase letters, digits, and hyphens only
# - May start with a letter or a digit (for example "3d-print")
# - Cannot start or end with a hyphen (the regex requires an alphanumeric at each end)
# - Cannot have consecutive hyphens (checked separately)
NAME_REGEX = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"

# SemVer 2.0.0 (https://semver.org): no leading zeros in numeric parts, hyphens
# allowed in pre-release and build identifiers (1.0.0-rc-hotfix). ASCII digits
# only, and \Z so a trailing newline does not pass. discover_skills.py and
# validate-skill.py keep a byte-identical fallback copy for when this module
# cannot be imported; tests/skills/skillforge/test_semver_regex.py pins them.
SEMVER_REGEX = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-(0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*)(\.(0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*))*)?(\+[0-9a-zA-Z-]+(\.[0-9a-zA-Z-]+)*)?\Z"
