#!/usr/bin/env python
# mypy: disable-error-code=type-arg
# mypy: disable-error-code=no-any-return
# mypy: disable-error-code=arg-type
# mypy: disable-error-code=assignment
# mypy: disable-error-code=return-value
# mypy: disable-error-code=var-annotated
# mypy: disable-error-code=operator
# mypy: disable-error-code=union-attr
"""
Automatically extracts skill learnings from session conversation with LLM fallback.

SETUP REQUIREMENTS:
  - Python 3.12+ with anthropic package installed
  - pyenv in PATH (recommended): Add to ~/.bashrc or ~/.zshrc:
      export PATH="$HOME/.pyenv/bin:$PATH"
      eval "$(pyenv init -)"
  - OR: System Python 3.12+ with: pip install anthropic

See .claude/hooks/Stop/README.md for detailed setup instructions.

Claude Code Stop hook that analyzes conversations for skill-related learnings
and updates skill observation memories automatically.

Uses hybrid approach:
1. Pattern-based heuristics with confidence scoring (fast, cost-free)
2. LLM fallback with Claude Haiku when confidence < threshold (accurate but costs tokens)

Confidence Levels:
- HIGH (0.8-1.0): Strong corrections, must fix
- MEDIUM (0.5-0.79): Patterns/preferences, should consider
- LOW (0.3-0.49): Repeated patterns, track for frequency

Hook Type: Stop (non-blocking)
Exit Codes (ADR-035, see `.agents/architecture/ADR-035-exit-code-standardization.md`):
  0 = Normal completion, or an optional (non-loader) learning step failed
  1 = Internal skill pattern loader defect (SkillPatternLoadError; Logic Error)
  2 = Required skill_pattern_loader companion missing/unimportable
      (SkillPatternCompanionError; Config Error)
  3 = Skill pattern loader hit an external I/O failure, e.g. disk or
      permissions (SkillPatternExternalError; External Error)

Related:
- .claude/skills/reflect/SKILL.md
- .serena/memories/{skill-name}-observations.md
- https://github.com/rjmurillo/ai-agents/pull/908
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Security-rejection logger. Structured WARNING records let SIEM and grep
# tooling categorize containment-guard rejections without parsing prose.
# Code prefix convention mirrors .agents/governance/FAILURE-MODES.md.
_SECURITY_LOG = logging.getLogger("ai_agents.hooks.skill_learning.security")
if not _SECURITY_LOG.handlers:
    _sec_handler = logging.StreamHandler(sys.stderr)
    _sec_handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s [%(code)s]: %(message)s")
    )
    _SECURITY_LOG.addHandler(_sec_handler)
    _SECURITY_LOG.setLevel(logging.WARNING)

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_lib_dir: str | None = None
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402


def _atomic_write_text(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        encoding="utf-8",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


# Base directory for all project operations (path traversal floor / arbitrary
# write blocker). The sentinel is deliberately outside any expected worktree.
_FAILED_PROJECT_ROOT = Path("/__nonexistent_containment_sentinel__")


def _reject_project_root(reason: str, env_dir: str = "") -> Path:
    """Log the existing CWE-22 diagnostic and return the fail-closed sentinel."""
    _SECURITY_LOG.warning(
        reason,
        extra={
            "code": "E_CWE22_PROJECT_DIR_MISMATCH",
            "env_dir": env_dir,
            "cwe": "CWE-22",
            "hook": "skill-learning",
        },
    )
    return _FAILED_PROJECT_ROOT


def _git_worktree_root_from_cwd() -> Path | None:
    """Return Git's worktree root for cwd only when cwd is contained by it."""
    try:
        cwd = Path.cwd().resolve(strict=True)
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

    raw_root = result.stdout.strip()
    if _validate_path_string(raw_root) is None:
        return None
    try:
        candidate = Path(raw_root).expanduser()
        if not candidate.is_absolute():
            return None
        root = candidate.resolve(strict=True)
        cwd.relative_to(root)
    except (OSError, ValueError):
        return None
    return root


def _detect_safe_base_dir() -> Path:
    """Derive the worktree from cwd and validate any project-dir corroboration."""
    worktree_root = _git_worktree_root_from_cwd()
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if worktree_root is None:
        return _reject_project_root(
            "Cannot derive a contained Git worktree from cwd -- refusing", env_dir
        )
    if not env_dir:
        return worktree_root

    validated_env = _validate_path_string(env_dir)
    if validated_env is None:
        return _reject_project_root(
            "CLAUDE_PROJECT_DIR is malformed -- refusing", env_dir
        )
    try:
        candidate = Path(validated_env).expanduser()
        if not candidate.is_absolute():
            return _reject_project_root(
                "CLAUDE_PROJECT_DIR is not absolute -- refusing", env_dir
            )
        corroborated_root = candidate.resolve(strict=True)
    except OSError:
        return _reject_project_root(
            "CLAUDE_PROJECT_DIR cannot be resolved -- refusing", env_dir
        )
    if corroborated_root != worktree_root:
        return _reject_project_root(
            "CLAUDE_PROJECT_DIR does not match the cwd Git worktree -- refusing",
            env_dir,
        )
    return worktree_root


def _is_relative_to(path: Path, base: Path) -> bool:
    """
    Return True if 'path' is located inside 'base' (or equal to it), after resolution.
    Implemented for Python versions that may not support Path.is_relative_to.
    """
    try:
        path = path.resolve(strict=False)
        base = base.resolve(strict=False)
    except Exception:
        return False
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _validate_path_string(path_str: str) -> str | None:
    """
    Validate and sanitize path string BEFORE Path() construction.

    Returns the validated string if safe, None if validation fails.
    This prevents tainted data from flowing into Path() constructor.

    Rejects:
    - Non-string types
    - Null bytes (CWE-158)
    - Control characters (newlines, tabs, etc.)
    - Obvious path traversal patterns
    """
    # Type and null byte check
    if not isinstance(path_str, str) or "\x00" in path_str:
        return None

    # Control character check (newline, carriage return, tab, vertical tab, form feed)
    if any(char in path_str for char in ["\n", "\r", "\t", "\v", "\f"]):
        return None

    # Normalize path separators for consistent checking
    normalized = path_str.replace("\\", "/")

    # Reject obvious traversal patterns
    # Note: This is pre-validation; full validation happens after Path() resolution
    if "/../" in normalized or normalized.startswith("../"):
        return None

    return path_str


SAFE_BASE_DIR = _detect_safe_base_dir()
OBSERVATIONS_SUFFIX = "-observations.md"
PROJECT_DIR: Path | None = None


def _get_safe_root_from_env(env_value: str) -> Path:
    """
    Convert an environment-provided root path into a safe project root.

    This function encapsulates all handling of potentially tainted path strings:
      1. String-level validation via _validate_path_string.
      2. Conversion to Path with expanduser/resolve.
      3. Enforcement that the result is absolute and within SAFE_BASE_DIR.

    On any validation failure, SAFE_BASE_DIR is returned.
    """
    # Step 1: String-level validation
    validated_root = _validate_path_string(env_value)
    if validated_root is None:
        return SAFE_BASE_DIR

    try:
        # Step 2: Safely construct and normalize a Path from the validated string.
        # Security note: path validation precedes resolution
        # JUSTIFICATION: Input has passed _validate_path_string, and the resulting
        # Path is immediately constrained to SAFE_BASE_DIR via _is_relative_to.
        candidate_root = Path(validated_root).expanduser().resolve(
            strict=False
        )  # Path validated before resolution
    except Exception:
        # If the environment value cannot be parsed as a path, fall back to SAFE_BASE_DIR
        return SAFE_BASE_DIR

    # Step 3: Enforce absolute path within SAFE_BASE_DIR
    if not candidate_root.is_absolute() or not _is_relative_to(candidate_root, SAFE_BASE_DIR):
        return SAFE_BASE_DIR

    return candidate_root


# =============================================================================
# SKILL PATTERN DEFINITIONS (Dynamically loaded from SKILL.md files)
# =============================================================================
# Patterns are loaded at runtime from SKILL.md trigger tables via
# skill_pattern_loader.py. This eliminates manual maintenance when
# skills are added, modified, or removed.
#
# The loader scans:
#   1. {project}/.claude/skills/*/SKILL.md  (Claude Code repo)
#   2. {project}/.github/skills/*/SKILL.md  (Copilot/GitHub repo)
#   3. ~/.claude/skills/*/SKILL.md          (Claude Code user)
#   4. ~/.copilot/skills/*/SKILL.md         (Copilot CLI user)
#
# The loader is a required runtime companion. Import or execution failure must
# leave this hook non-successful instead of reporting an empty-pattern success.
# =============================================================================


class SkillPatternLoadError(RuntimeError):
    """Required skill-pattern loading failed (internal loader defect).

    Base class for the three ADR-035 failure classes this hook distinguishes.
    Catch the specific subclass first; this base class is the fallback for
    an unexpected defect in the loader itself, including a ``SyntaxError``
    raised while importing the companion module (a broken companion file is
    a logic defect in that file, not a missing dependency or an external I/O
    failure) (ADR-035 exit 1, "Logic Error"). See
    `.agents/architecture/ADR-035-exit-code-standardization.md` lines 120-126
    for the canonical exit-code table this mirrors verbatim: ``0=Success,
    1=Logic Error, 2=Config Error, 3=External Error, 4=Auth Error``.
    """


class SkillPatternCompanionError(SkillPatternLoadError):
    """The ``skill_pattern_loader`` companion module could not be imported.

    Raised when the companion file declared in
    ``build/scripts/generate_hooks_events.py``'s ``_COMPANIONS_BY_OWNER`` is
    missing or fails to import. This is a missing-dependency/configuration
    problem, not a logic bug in the loader (ADR-035 exit 2, "Config Error").
    """


class SkillPatternExternalError(SkillPatternLoadError):
    """The skill pattern loader hit an external I/O failure.

    Raised when either importing the ``skill_pattern_loader`` companion
    module (e.g. a local filesystem ``PermissionError`` reading the module
    file) or calling :func:`skill_pattern_loader.load_skill_patterns`
    (scanning SKILL.md files or writing its stat cache) fails with an
    ``OSError``: disk full, permission denied, or a filesystem race. This is
    an external resource failure, not a defect in the loader's own logic and
    not an authentication/authorization failure -- a local filesystem
    ``PermissionError`` is a resource-access failure (ADR-035 exit 3,
    "External Error"), distinct from the service auth/credential failures
    ADR-035 exit 4 ("Auth Error") reserves for token/session expiry.
    """


SKILL_PATTERNS: dict[str, list[str]] = {}
COMMAND_TO_SKILL: dict[str, str] = {}
_patterns_loaded = False


def _ensure_patterns_loaded(project_dir: Path) -> None:
    """Lazy-load skill patterns from SKILL.md files on first use.

    Uses stat-based caching for performance (~2ms warm, ~40ms cold).

    Raises (see the class docstrings for the ADR-035 exit each maps to):
        SkillPatternCompanionError: the companion module cannot be imported
            (``ImportError``, e.g. the file is missing).
        SkillPatternExternalError: the companion import or the companion's
            ``load_skill_patterns`` call hit an ``OSError`` (disk or
            permission failure).
        SkillPatternLoadError: the companion import hit a ``SyntaxError``
            (a broken companion file), or ``load_skill_patterns`` raised any
            other unexpected defect.
    """
    global SKILL_PATTERNS, COMMAND_TO_SKILL, _patterns_loaded
    if _patterns_loaded:
        return
    try:
        from skill_pattern_loader import load_skill_patterns
    except ImportError as exc:
        raise SkillPatternCompanionError(
            f"required skill_pattern_loader companion is unavailable: {exc}"
        ) from exc
    except SyntaxError as exc:
        raise SkillPatternLoadError(
            f"skill_pattern_loader companion has invalid syntax: {exc}"
        ) from exc
    except OSError as exc:
        raise SkillPatternExternalError(
            f"skill_pattern_loader companion import hit an external I/O failure: {exc}"
        ) from exc
    try:
        loaded_patterns, loaded_commands = load_skill_patterns(project_dir)
    except OSError as exc:
        raise SkillPatternExternalError(
            f"skill pattern loader hit an external I/O failure: {exc}"
        ) from exc
    except Exception as exc:
        raise SkillPatternLoadError(
            f"required skill pattern loader failed: {exc}"
        ) from exc
    if loaded_patterns:
        SKILL_PATTERNS = loaded_patterns
    if loaded_commands:
        COMMAND_TO_SKILL = loaded_commands
    _patterns_loaded = True


# LLM fallback configuration
CONFIDENCE_THRESHOLD = float(os.getenv("SKILL_LEARNING_CONFIDENCE_THRESHOLD", "0.7"))
# M7-T6: privacy default flipped from true to false. The pre-fix default
# uploaded session transcripts to Anthropic on every Stop hook fire unless
# the operator explicitly opted out, with the API key sourced implicitly
# from environment or .env. Both are PII / credential surprises. Now the
# operator MUST explicitly set SKILL_LEARNING_USE_LLM=true to opt in.
USE_LLM_FALLBACK = os.getenv("SKILL_LEARNING_USE_LLM", "false").lower() == "true"
LLM_MODEL = "claude-haiku-4-5-20251001"
LLM_MAX_TOKENS = 200
# M7-T6: bound the synchronous outbound call. Per .claude/rules/release-it.md
# every external integration MUST timeout; SessionEnd hooks are user-facing.
LLM_TIMEOUT_SEC = float(os.getenv("SKILL_LEARNING_LLM_TIMEOUT_SEC", "10"))

# Try to import Anthropic SDK (optional dependency)
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


def write_learning_notification(skill_name: str, high_count: int, med_count: int, low_count: int):
    """Write silent notification about learnings extracted."""
    total = high_count + med_count + low_count
    if total > 0:
        print(
            f"✔️ learned from session ➡️ {skill_name} "
            f"({high_count} HIGH, {med_count} MED, {low_count} LOW)"
        )


def get_project_directory(_hook_input: dict) -> str:
    """Return the validated cwd worktree root or the fail-closed sentinel."""
    return str(SAFE_BASE_DIR)


def get_safe_project_path(project_dir: str) -> Path | None:
    """
    Resolve and validate the project directory against a safe root.

    This prevents path traversal or escaping the expected project tree when
    CLAUDE_PROJECT_DIR or hook-provided cwd are influenced by external input.
    """
    if SAFE_BASE_DIR == _FAILED_PROJECT_ROOT:
        return None
    try:
        resolved_project = Path(project_dir).resolve()
    except OSError:
        # If resolution fails for any reason, treat as unsafe
        return None

    # Validate project_dir is within SAFE_BASE_DIR (the Git worktree root).
    # Previously this used CLAUDE_PROJECT_ROOT which could be a subdirectory,
    # causing the check to fail when project_dir was the worktree root itself.
    if hasattr(resolved_project, "is_relative_to"):
        if not resolved_project.is_relative_to(SAFE_BASE_DIR):
            return None
    else:
        try:
            resolved_project.relative_to(SAFE_BASE_DIR)
        except ValueError:
            return None

    return resolved_project


def get_conversation_messages(hook_input: dict) -> list[dict]:
    """Extract messages from hook input conversation history."""
    return hook_input.get("messages", [])


def detect_skill_usage(messages: list[dict]) -> dict[str, int]:
    """
    Detect skills mentioned or used in conversation.

    Returns dict of skill names to usage counts.

    Uses SKILL_PATTERNS (module-level) for pattern matching.
    Uses COMMAND_TO_SKILL (module-level) for slash command resolution.
    """
    detected_skills = {}
    conversation_text = ' '.join(
        msg.get('content', '')
        for msg in messages
        if isinstance(msg.get('content'), str)
    )

    # Detect skills from .claude/skills/{skill-name} references
    skill_path_pattern = re.compile(r'\.claude[/\\]skills[/\\]([a-z0-9-]+)')
    for match in skill_path_pattern.finditer(conversation_text):
        skill_name = match.group(1)
        detected_skills[skill_name] = detected_skills.get(skill_name, 0) + 1

    # Detect skills from slash commands using centralized mapping
    slash_cmd_pattern = re.compile(r'/([a-z][a-z0-9-]+)')
    for match in slash_cmd_pattern.finditer(conversation_text):
        cmd_name = match.group(1)
        if cmd_name in COMMAND_TO_SKILL:
            skill_name = COMMAND_TO_SKILL[cmd_name]
            detected_skills[skill_name] = detected_skills.get(skill_name, 0) + 1

    # Pattern-based detection using centralized patterns
    for skill, patterns in SKILL_PATTERNS.items():
        match_count = 0
        for msg in messages:
            content = msg.get('content', '')
            if isinstance(content, str):
                for pattern in patterns:
                    if re.search(re.escape(pattern), content, re.IGNORECASE):
                        match_count += 1

        if match_count >= 2:  # Threshold: mentioned at least twice
            detected_skills[skill] = detected_skills.get(skill, 0) + match_count

    return detected_skills


def check_skill_context(text: str, skill: str) -> bool:
    """
    Check if skill is mentioned in the given text context.

    For mapped skills, checks against SKILL_PATTERNS (module-level).
    For dynamically detected skills (not in map), checks for skill name mention
    or skill path reference to avoid silently discarding learnings.

    Uses SKILL_PATTERNS (module-level) - same source as detect_skill_usage().
    """
    # Check mapped skills against centralized patterns
    if skill in SKILL_PATTERNS:
        for pattern in SKILL_PATTERNS[skill]:
            if re.search(re.escape(pattern), text, re.IGNORECASE):
                return True
        return False

    # For dynamically detected skills (not in pattern map):
    # Check for skill name mention or skill path reference
    # This ensures dynamically discovered skills get their learnings persisted
    skill_name_pattern = re.compile(re.escape(skill), re.IGNORECASE)
    skill_path_pattern = re.compile(rf'\.claude[/\\]skills[/\\]{re.escape(skill)}', re.IGNORECASE)

    if skill_name_pattern.search(text) or skill_path_pattern.search(text):
        return True

    return False


def get_api_key() -> str | None:
    """Get Anthropic API key from environment.

    M7-T6: implicit ``.env`` pickup removed. The pre-fix code silently
    parsed ``.env`` files for ``ANTHROPIC_API_KEY``, surprising operators
    who did not realize a hook would scan their credential files. The
    operator MUST now provide ``ANTHROPIC_API_KEY`` (or an explicit
    ``SKILL_LEARNING_API_KEY``) via the environment to opt into the LLM
    fallback path. Combined with the ``USE_LLM_FALLBACK`` opt-in flag,
    this gives the operator full control over both intent and credential.
    """
    return os.getenv("SKILL_LEARNING_API_KEY") or os.getenv("ANTHROPIC_API_KEY")


def classify_learning_by_llm(
    assistant_msg: str,
    user_response: str,
    skill_name: str
) -> dict | None:
    """
    Use Claude Haiku to classify uncertain learnings.

    Returns dict with:
    - type: str (correction/preference/success/edge_case/question/command_pattern)
    - confidence: float (0-1)
    - source: str (extracted learning text)
    - category: str (High/Med/Low)
    """
    if not ANTHROPIC_AVAILABLE:
        return None

    api_key = get_api_key()
    if not api_key:
        return None

    try:
        client = Anthropic(api_key=api_key)

        prompt = (
            f'Analyze this conversation exchange for skill-related learnings about the '
            f'"{skill_name}" skill.\n\n'
            f"Assistant said:\n{assistant_msg[:500]}\n\n"
            f"User responded:\n{user_response}\n\n"
            "Is this a learning signal? If yes, extract the learning and classify it:\n\n"
            "Categories:\n"
            '- HIGH (correction): Strong user corrections '
            '("no", "wrong", "never do", "must use")\n'
            "- HIGH (chestertons_fence): Removed something without understanding why\n"
            "- HIGH (immediate_correction): User immediately asked to debug/fix "
            "right after\n"
            '- MED (preference): Tool/approach preferences '
            '("instead of using", "prefer to", "should use X")\n'
            '- MED (success): Success patterns '
            '("perfect", "excellent", "exactly", "that\'s it") - no qualifiers like "but"\n'
            '- MED (edge_case): Important edge cases '
            '("what if the/this", "ensure that", "make sure")\n'
            '- MED (documentation): Documentation feedback '
            '("update the docs", "needs documentation")\n'
            "- MED (question): Short clarifying question (may indicate confusion)\n"
            "- LOW (command_pattern): Repeated command patterns\n\n"
            "Respond in JSON format:\n"
            "{\n"
            '  "is_learning": true/false,\n'
            '  "type": "correction|preference|success|edge_case|documentation|question|'
            'command_pattern|chestertons_fence|immediate_correction",\n'
            '  "confidence": 0.0-1.0,\n'
            '  "category": "High|Med|Low",\n'
            '  "extracted_learning": "The key lesson learned",\n'
            '  "reasoning": "Why this is/isn\'t a learning"\n'
            "}"
        )

        # M7-T6: timeout bounds the synchronous call so a stalled API
        # cannot wedge the SessionEnd hook indefinitely. The Anthropic
        # SDK accepts a per-call timeout in seconds.
        message = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            timeout=LLM_TIMEOUT_SEC,
        )

        response_text = message.content[0].text.strip()

        # Use regex to reliably extract JSON from markdown code blocks or raw text
        json_str = response_text
        match = re.search(r"```(?:json)?\s*({.*?})\s*```", response_text, re.DOTALL)
        if match:
            json_str = match.group(1)

        result = json.loads(json_str)

        if not result.get("is_learning"):
            return None

        # Validate and normalize confidence to float
        try:
            confidence = float(result["confidence"])
            if not (0.0 <= confidence <= 1.0):
                print(f"LLM confidence out of range: {confidence}", file=sys.stderr)
                return None
        except (ValueError, TypeError):
            print(f"Invalid LLM confidence value: {result.get('confidence')}", file=sys.stderr)
            return None

        return {
            "type": result["type"],
            "confidence": confidence,
            "source": result.get("extracted_learning", user_response[:150]),
            "category": result["category"],
            "method": "haiku-llm"
        }

    except Exception as e:
        print(f"LLM classification error: {e}", file=sys.stderr)
        return None


def extract_learnings(messages: list[dict], skill_name: str) -> dict[str, list[dict]]:
    """
    Extract learnings from conversation with confidence scoring and LLM fallback.

    Returns dict with High/Med/Low keys, each containing list of learnings.
    Each learning has: type, source, context, confidence, method.
    """
    learnings = {
        "High": [],
        "Med": [],
        "Low": []
    }

    # Analyze message pairs (assistant -> user)
    for i in range(len(messages) - 1):
        msg = messages[i]
        next_msg = messages[i + 1]

        if msg.get("role") != "assistant" or next_msg.get("role") != "user":
            continue

        assistant_content = msg.get("content", "")
        user_response = next_msg.get("content", "")

        if not isinstance(assistant_content, str) or not isinstance(user_response, str):
            continue

        # Build context window
        context_window = ""
        if i > 0:
            prev_content = messages[i - 1].get("content", "")
            if isinstance(prev_content, str):
                context_window += prev_content + " "
        context_window += assistant_content + " " + user_response
        if i + 2 < len(messages):
            next_content = messages[i + 2].get("content", "")
            if isinstance(next_content, str):
                context_window += " " + next_content

        # Skip if skill not mentioned in context
        if not check_skill_context(context_window, skill_name):
            continue

        # Pattern-based extraction with confidence scoring
        learning = None

        # HIGH: Strong corrections (confidence 0.85-0.95)
        correction_pattern = (
            r"(?i)\b(no\b|nope|not like that|that\'s wrong|incorrect|"
            r"never do|always do|don\'t ever|must use|should not|avoid|stop)\b"
        )
        chestertons_fence_pattern = (
            r"(?i)(trashed without understanding|removed without knowing|"
            r"deleted without checking|why was this here)"
        )
        immediate_correction_pattern = (
            r"(?i)\b(debug|root cause|correct|fix all|address|broken|"
            r"error|issue|problem)\b"
        )

        if re.search(correction_pattern, user_response):
            strong_correction_hits = re.findall(
                r"(?i)\b(no|wrong|never|must)\b",
                user_response,
            )
            confidence = 0.9 if len(strong_correction_hits) > 1 else 0.85
            learning = {
                "type": "correction",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # HIGH: Chesterton's Fence (confidence 0.95)
        elif re.search(chestertons_fence_pattern, user_response):
            learning = {
                "type": "chestertons_fence",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": 0.95,
                "method": "pattern"
            }

        # HIGH: Immediate corrections (confidence 0.8-0.85)
        elif (
            re.search(immediate_correction_pattern, user_response)
            and len(user_response) < 200
        ):
            confidence = 0.85 if len(user_response) < 50 else 0.8
            learning = {
                "type": "immediate_correction",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # MED: Tool preferences (confidence 0.7-0.75)
        # Bug 7 fix: More specific patterns to avoid false positives
        # Requires preference indicators with tool/approach context
        elif re.search(
            r'(?i)\b('
            r'(?:instead of|rather than)\s+(?:using|that|the|this)|'  # "instead of using X"
            r'prefer\s+(?:to|using|that)|'  # "prefer to/using/that"
            r'should\s+use\s+\w+|'  # "should use X"
            r'use\s+\w+\s+(?:instead|rather)|'  # "use X instead/rather"
            r'better\s+to\s+(?:use|do|have)'  # "better to use/do/have"
            r')\b',
            user_response
        ):
            confidence = 0.75 if re.search(r'(?i)\b(prefer|should use)\b', user_response) else 0.7
            learning = {
                "type": "preference",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # MED: Success patterns (confidence 0.65-0.7)
        # Bug 5 fix: Tighter patterns to avoid false positives
        # Excludes: "Great question", "Works for me but", "Yes, but..."
        # Requires affirmation at start without qualifiers
        elif re.search(
            r'(?i)^(?:(?:ok|okay|yeah|yep|sure|alright)[,!\s]+)?'
            r'(?:'
            r'perfect(?![a-z])|'  # "perfect" but not "perfectly"
            r'excellent(?:!|\s*$)|'  # "excellent!" or end of string
            r'exactly(?:!|\s*$)|'  # "exactly!" or end of string
            r"that's\s+(?:it|right|correct)|"  # "that's it/right/correct"
            r'good\s+job|well\s+done|'  # "good job", "well done"
            # "works great/perfectly!" not followed by "but"
            r'works(?:\s+great|\s+perfectly|!)(?!\s+(?:but|however|except))|'
            r'(?:yes|correct|right)(?:\s*[!.])?$'  # "yes/correct/right" at end
            r')',
            user_response
        ) and not re.search(r'(?i)\b(but|however|except|although|though)\b', user_response):
            confidence = 0.7 if re.search(r'(?i)\b(perfect|excellent)\b', user_response) else 0.65
            learning = {
                "type": "success",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # MED: Edge cases (confidence 0.6-0.65)
        # Bug 6 fix: Added negative lookaheads to exclude rhetorical/unrelated questions
        # Excludes: "what if we had lunch?", "how does this work in general?"
        # Requires skill-relevant context indicators
        elif re.search(
            r'(?i)(?:'
            r'what\s+if\s+(?:the|this|we|it|there|a\s+user)|'  # "what if the/this/we..."
            r'how\s+(?:does|will|would)\s+(?:it|this|the)|'  # "how does/will it..."
            r'what\s+about\s+(?:the|when|if|edge|corner|error)|'  # "what about the/when..."
            r"(?:don't|do\s+not)\s+(?:want\s+to\s+)?forget|"  # "don't forget"
            r'(?:ensure|make\s+sure|verify)\s+(?:that|the|it|we)'  # "ensure that/the..."
            r').*\?',
            user_response
        ) and not re.search(
            r'(?i)\b(lunch|dinner|coffee|meeting|call|later|tomorrow)\b',
            user_response
        ):
            confidence = (
                0.65
                if re.search(r'(?i)\b(ensure|make sure|verify)\b', user_response)
                else 0.6
            )
            learning = {
                "type": "edge_case",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # MED: Documentation feedback (confidence 0.6-0.65)
        # Bug 8 fix: Added missing documentation learning type
        # Detects user feedback about documentation quality/needs
        elif re.search(
            r'(?i)\b('
            r'(?:update|add|fix|improve)\s+(?:the\s+)?(?:docs?|documentation|readme)|'
            r'(?:docs?|documentation|readme)\s+(?:is|are|needs?|should)|'
            r'document(?:ed)?\s+(?:this|that|it|the)|'
            r'add\s+(?:a\s+)?comment|'
            r'(?:missing|lacking|needs?)\s+(?:docs?|documentation)'
            r')\b',
            user_response
        ):
            confidence = (
                0.65
                if re.search(r'(?i)\b(must|should|needs?)\b', user_response)
                else 0.6
            )
            learning = {
                "type": "documentation",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # MED: Clarifying questions (confidence 0.55-0.6)
        elif (
            re.search(r'\?', user_response)
            and len(user_response) < 50
            and re.search(
                r'(?i)^(why|how|what|when|where|can|does|is|are)\b',
                user_response,
            )
        ):
            confidence = 0.6 if len(user_response) < 30 else 0.55
            learning = {
                "type": "question",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # LOW: Command patterns (confidence 0.4-0.5)
        elif re.search(r'(?i)^(\./|pwsh |gh |git )', user_response):
            learning = {
                "type": "command_pattern",
                "source": user_response[:100],
                "context": assistant_content[:100],
                "confidence": 0.45,
                "method": "pattern"
            }

        # LOW: Short acknowledgements without substance (confidence 0.35-0.45)
        # These may indicate workflow patterns worth tracking
        elif re.search(
            r'(?i)^(?:ok|okay|sure|got it|sounds good|thanks|thank you|yep|yeah|'
            r'alright|fine|k|kk)(?:[.!,]?\s*)?$',
            user_response.strip()
        ) and len(user_response.strip()) < 30:
            learning = {
                "type": "acknowledgement",
                "source": user_response[:50],
                "context": assistant_content[:100],
                "confidence": 0.4,
                "method": "pattern"
            }

        # LOW: Repeated tool/file mentions (confidence 0.35-0.45)
        # User keeps referring to same resources, may indicate workflow patterns
        elif re.search(
            r'(?i)\b(same|again|also|another|more|repeat|similar|like before|as usual)\b',
            user_response
        ) and len(user_response) < 100:
            learning = {
                "type": "repeated_pattern",
                "source": user_response[:100],
                "context": assistant_content[:100],
                "confidence": 0.4,
                "method": "pattern"
            }

        # LLM fallback for uncertain cases
        if learning and learning["confidence"] < CONFIDENCE_THRESHOLD and USE_LLM_FALLBACK:
            llm_result = classify_learning_by_llm(assistant_content, user_response, skill_name)
            if llm_result:
                # Use LLM classification if it has higher confidence
                if llm_result["confidence"] > learning["confidence"]:
                    learning = llm_result

        # Categorize by confidence
        if learning:
            if learning["confidence"] >= 0.8:
                learnings["High"].append(learning)
            elif learning["confidence"] >= 0.5:
                learnings["Med"].append(learning)
            else:
                learnings["Low"].append(learning)

    return learnings


def escape_replacement_string(text: str) -> str:
    """
    Escape special characters for regex replacement strings.

    In re.sub() replacement strings, backslashes are interpreted as escape
    sequences (e.g., \\1 for backreferences). User content containing backslashes
    must be escaped by doubling them to prevent interpretation as special sequences.

    Example: "Use \\1 for regex" -> "Use \\\\1 for regex"
    """
    return text.replace("\\", "\\\\")


def update_skill_memory(
    project_dir: Path,
    skill_name: str,
    learnings: dict[str, list[dict]],
    session_id: str
) -> bool:
    """
    Update skill observation memory file with new learnings.

    Returns True if successful, False otherwise.
    """
    # Security: Path traversal prevention (CWE-22)
    # Step 1: Validate and resolve project_dir FIRST before any path operations
    # get_project_directory already constrains this to SAFE_BASE_DIR, but we keep
    # local validation in case update_skill_memory is called directly elsewhere.
    try:
        allowed_dir = project_dir.resolve(strict=False)
        # Validate project_dir looks like a real directory path
        if not allowed_dir.is_absolute():
            print(
                f"Invalid project directory: '{project_dir}' does not resolve to absolute path",
                file=sys.stderr,
            )
            return False
        if not _is_relative_to(allowed_dir, SAFE_BASE_DIR):
            print(
                f"Path traversal attempt detected: '{allowed_dir}' "
                "is outside safe base directory",
                file=sys.stderr,
            )
            return False
    except Exception as e:
        print(f"Path validation error for project_dir: {e}", file=sys.stderr)
        return False

    # Step 2: Validate skill_name does not contain path traversal characters
    # This prevents attacks via skill names like "../../../etc/passwd" or "..\\attack"
    # Regex allowlist: only alphanumeric, underscore, and hyphen characters permitted
    if not re.fullmatch(r"[A-Za-z0-9_-]+", skill_name):
        print(
            f"Invalid skill name: '{skill_name}' contains unsupported characters",
            file=sys.stderr,
        )
        return False

    # Step 3: Construct paths using validated allowed_dir
    memories_dir = allowed_dir / ".serena" / "memories"

    # Ensure directory exists before resolving paths
    memories_dir.mkdir(parents=True, exist_ok=True)

    # Path validated before resolution
    # CodeQL suppression: skill_name validated in Step 2 to not contain path traversal chars
    memory_path = memories_dir / f"{skill_name}{OBSERVATIONS_SUFFIX}"

    # Step 4: Validate resolved path is within project directory
    try:
        resolved_path = memory_path.resolve()
        # Include directory separator to prevent prefix attacks
        # e.g., "/home/user" should not match "/home/usermalicious"
        if not str(resolved_path).startswith(str(allowed_dir) + os.sep):
            print(
                f"Path traversal attempt detected: '{resolved_path}' "
                "is outside project directory",
                file=sys.stderr,
            )
            return False
    except Exception as e:
        print(f"Path validation error for memory_path: {e}", file=sys.stderr)
        return False

    # Step 5: Use validated resolved_path for all file operations
    # Read existing memory or create new
    # Path validated before resolution
    # CodeQL suppression: resolved_path validated in Step 4 to be within project directory
    if resolved_path.exists():
        # Path validated before resolution
        # CodeQL suppression: resolved_path validated in Step 4
        existing_content = resolved_path.read_text(encoding='utf-8')
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        existing_content = f"""# Skill Observations: {skill_name}

**Last Updated**: {today}
**Sessions Analyzed**: 0

## Constraints (HIGH confidence)

## Preferences (MED confidence)

## Edge Cases (MED confidence)

## Documentation (MED confidence)

## Notes for Review (LOW confidence)

"""

    new_content = existing_content
    today = datetime.now().strftime("%Y-%m-%d")

    # HIGH: Append to Constraints section
    if learnings["High"]:
        constraint_items = ""
        for learning in learnings["High"]:
            source = escape_replacement_string(learning["source"])
            method_tag = " [LLM]" if learning.get("method") == "haiku-llm" else ""
            constraint_items += f"- {source}{method_tag} (Session {session_id}, {today})\n"

        pattern = r'(## Constraints \(HIGH confidence\)\r?\n)'
        # Use r'\1' (raw string) to preserve backreference - f'\1' creates ASCII SOH character
        new_content = re.sub(pattern, r'\1' + constraint_items, new_content)

    # MED: Group by type
    if learnings["Med"]:
        # Preferences: success patterns and tool preferences
        preference_items = ""
        for learning in learnings["Med"]:
            if learning["type"] in ["success", "preference"]:
                source = escape_replacement_string(learning["source"])
                method_tag = " [LLM]" if learning.get("method") == "haiku-llm" else ""
                preference_items += f"- {source}{method_tag} (Session {session_id}, {today})\n"

        if preference_items:
            pattern = r'(## Preferences \(MED confidence\)\r?\n)'
            new_content = re.sub(pattern, r'\1' + preference_items, new_content)

        # Edge Cases: edge cases and questions
        edge_case_items = ""
        for learning in learnings["Med"]:
            if learning["type"] in ["edge_case", "question"]:
                source = escape_replacement_string(learning["source"])
                method_tag = " [LLM]" if learning.get("method") == "haiku-llm" else ""
                edge_case_items += f"- {source}{method_tag} (Session {session_id}, {today})\n"

        if edge_case_items:
            pattern = r'(## Edge Cases \(MED confidence\)\r?\n)'
            new_content = re.sub(pattern, r'\1' + edge_case_items, new_content)

        # Documentation feedback
        documentation_items = ""
        for learning in learnings["Med"]:
            if learning["type"] == "documentation":
                source = escape_replacement_string(learning["source"])
                method_tag = " [LLM]" if learning.get("method") == "haiku-llm" else ""
                documentation_items += f"- {source}{method_tag} (Session {session_id}, {today})\n"

        if documentation_items:
            # Add section if it doesn't exist (for existing memory files)
            if "## Documentation (MED confidence)" not in new_content:
                # Insert before Notes for Review section
                new_content = re.sub(
                    r'(## Notes for Review \(LOW confidence\))',
                    r'## Documentation (MED confidence)\n\n\1',
                    new_content
                )
            pattern = r'(## Documentation \(MED confidence\)\r?\n)'
            new_content = re.sub(pattern, r'\1' + documentation_items, new_content)

        # Catch-all for MED learnings with types not handled above
        # (e.g., correction, chestertons_fence, immediate_correction, command_pattern from LLM)
        handled_med_types = {"success", "preference", "edge_case", "question", "documentation"}
        other_med_items = ""
        for learning in learnings["Med"]:
            if learning["type"] not in handled_med_types:
                source = escape_replacement_string(learning["source"])
                learning_type = learning["type"]
                method_tag = " [LLM]" if learning.get("method") == "haiku-llm" else ""
                other_med_items += (
                    f"- [{learning_type}] {source}{method_tag} "
                    f"(Session {session_id}, {today})\n"
                )

        if other_med_items:
            pattern = r'(## Preferences \(MED confidence\)\r?\n)'
            new_content = re.sub(pattern, r'\1' + other_med_items, new_content)

    # LOW: Command patterns
    if learnings["Low"]:
        low_items = ""
        for learning in learnings["Low"]:
            source = escape_replacement_string(learning["source"])
            low_items += f"- {source} (Session {session_id}, {today})\n"

        pattern = r'(## Notes for Review \(LOW confidence\)\r?\n)'
        new_content = re.sub(pattern, r'\1' + low_items, new_content)

    # Update session count
    match = re.search(r'Sessions Analyzed: (\d+)', new_content)
    if match:
        count = int(match.group(1)) + 1
        new_content = re.sub(r'Sessions Analyzed: \d+', f'Sessions Analyzed: {count}', new_content)

    # Update last updated date
    new_content = re.sub(r'\*\*Last Updated\*\*: [\d-]+', f'**Last Updated**: {today}', new_content)

    # Write memory file using validated resolved_path
    # Path validated before resolution
    # CodeQL suppression: resolved_path validated in Step 4 to be within project directory
    _atomic_write_text(resolved_path, new_content)

    return True


def main():
    """Main hook execution."""
    if skip_if_consumer_repo("skill-learning"):
        return 0

    try:
        # Check for piped input
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
        project_dir = get_project_directory(hook_input)
        safe_project_path = get_safe_project_path(project_dir)
        if safe_project_path is None:
            # Invalid or unsafe project directory; do not access the filesystem
            return 0

        global PROJECT_DIR
        PROJECT_DIR = safe_project_path

        # Load skill patterns dynamically from SKILL.md files
        _ensure_patterns_loaded(safe_project_path)

        messages = get_conversation_messages(hook_input)

        if not messages:
            return 0

        # Detect skills used in this session
        detected_skills = detect_skill_usage(messages)

        if not detected_skills:
            return 0

        # Get session ID from today's session log
        # Path validated before resolution
        # CodeQL suppression: project_dir is validated against safe root and used
        # only for reading session logs
        sessions_dir = safe_project_path / ".agents" / "sessions"
        today = datetime.now().strftime("%Y-%m-%d")

        # Check if sessions directory exists before globbing to avoid silent failures
        # Path validated before resolution
        # CodeQL suppression: sessions_dir constructed from validated project_dir for read-only glob
        if sessions_dir.exists():
            # Path validated before resolution
            # CodeQL suppression: Read-only operation on validated sessions directory
            session_logs = sorted(
                sessions_dir.glob(f"{today}-session-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            session_id = session_logs[0].stem if session_logs else f"{today}-session-unknown"
        else:
            # Sessions directory doesn't exist yet, use fallback ID
            session_id = f"{today}-session-unknown"

        # Process each detected skill
        for skill_name in detected_skills:
            learnings = extract_learnings(messages, skill_name)

            high_count = len(learnings["High"])
            med_count = len(learnings["Med"])
            low_count = len(learnings["Low"])

            # Only update if learnings meet threshold
            if high_count >= 1 or med_count >= 2 or low_count >= 3:
                updated = update_skill_memory(safe_project_path, skill_name, learnings, session_id)

                if updated:
                    write_learning_notification(skill_name, high_count, med_count, low_count)

        return 0

    except SkillPatternCompanionError as exc:
        # Missing/misconfigured runtime companion: Config Error (ADR-035 exit 2).
        print(f"Skill learning hook error: {exc}", file=sys.stderr)
        return 2
    except SkillPatternExternalError as exc:
        # Disk/permission/filesystem failure: External Error (ADR-035 exit 3).
        print(f"Skill learning hook error: {exc}", file=sys.stderr)
        return 3
    except SkillPatternLoadError as exc:
        # Unexpected defect in the loader itself: Logic Error (ADR-035 exit 1).
        print(f"Skill learning hook error: {exc}", file=sys.stderr)
        return 1
    except Exception as e:
        # Optional background learning failures do not block session end.
        print(f"Skill learning hook error: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
