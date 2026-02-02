#!/usr/bin/env python3
"""
Automatically extracts skill learnings from session conversation with LLM fallback.

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
Exit Codes: Always 0 (silent background learning)

Related:
- .claude/skills/reflect/SKILL.md
- .serena/memories/{skill-name}-observations.md
- https://github.com/rjmurillo/ai-agents/pull/908
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Base directory for all project operations to prevent path traversal / arbitrary writes
# We treat the repository root (two levels up from this file) as the safe base.
SAFE_BASE_DIR = Path(__file__).resolve().parents[2]
OBSERVATIONS_SUFFIX = "-observations.md"
PROJECT_DIR: Optional[Path] = None


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


def _validate_path_string(path_str: str) -> Optional[str]:
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
        # nosec B602 - CodeQL py/path-injection suppression
        # JUSTIFICATION: Input has passed _validate_path_string, and the resulting
        # Path is immediately constrained to SAFE_BASE_DIR via _is_relative_to.
        candidate_root = Path(validated_root).expanduser().resolve(strict=False)  # lgtm[py/path-injection]
    except Exception:
        # If the environment value cannot be parsed as a path, fall back to SAFE_BASE_DIR
        return SAFE_BASE_DIR

    # Step 3: Enforce absolute path within SAFE_BASE_DIR
    if not candidate_root.is_absolute() or not _is_relative_to(candidate_root, SAFE_BASE_DIR):
        return SAFE_BASE_DIR

    return candidate_root


# =============================================================================
# SKILL PATTERN DEFINITIONS (Single Source of Truth)
# =============================================================================
# IMPORTANT: These patterns are used in 2 functions:
#   1. detect_skill_usage() - Detects which skills were used in conversation
#   2. check_skill_context() - Validates skill context for learning extraction
#
# If you add/modify patterns here, both functions automatically stay in sync.
# The command_to_skill mapping below handles slash command -> skill resolution.
# =============================================================================

SKILL_PATTERNS: Dict[str, List[str]] = {
    # GitHub skill: PR/issue operations, skill path, explicit mentions
    'github': ['gh pr', 'gh issue', '.claude/skills/github', 'github skill', '/pr-review', 'pull request'],
    # Memory skill: Forgetful, Serena, memory operations
    'memory': ['search memory', 'forgetful', 'serena', 'memory-first', 'ADR-007', 'mcp__serena'],
    # Session initialization
    'session-init': ['/session-init', 'session log', 'session protocol', 'session-init skill'],
    # SkillForge meta-skill
    'SkillForge': ['SkillForge', 'create skill', 'synthesis panel', 'skill creation'],
    # ADR review skill
    'adr-review': ['adr-review', 'ADR files', 'architecture decision', 'decision record'],
    # Incoherence detection
    'incoherence': ['incoherence skill', 'detect incoherence', 'reconcile', 'incoherence detection'],
    # Retrospective/reflection
    'retrospective': ['retrospective', 'session end', 'retrospective skill'],
    'reflect': ['reflect skill', 'learn from this', 'what did we learn', '/reflect'],
    # PR comment handling
    'pr-comment-responder': ['pr-comment-responder', 'review comments', 'feedback items', 'PR feedback'],
    # Code review patterns
    'code-review': ['code review skill', 'style guide', 'security patterns', 'review code'],
    # API design patterns
    'api-design': ['API design skill', 'REST API', 'API endpoint', 'API versioning'],
    # Testing patterns - more specific to avoid false positives on generic "test"
    'testing': ['test coverage', 'unit test', 'integration test', 'mocking', 'test assertion', 'testing skill'],
    # Documentation - more specific patterns to avoid matching generic "documentation" text
    'documentation': ['.claude/skills/documentation', 'documentation skill', 'write documentation', 'update docs', 'README update'],
}

# Slash command to skill mapping
COMMAND_TO_SKILL: Dict[str, str] = {
    'pr-review': 'github',
    'session-init': 'session-init',
    'memory-search': 'memory',
    'memory-list': 'memory',
    'research': 'research-and-incorporate',
    'reflect': 'reflect',
    'forgetful': 'memory',
}

# LLM fallback configuration
CONFIDENCE_THRESHOLD = float(os.getenv("SKILL_LEARNING_CONFIDENCE_THRESHOLD", "0.7"))
USE_LLM_FALLBACK = os.getenv("SKILL_LEARNING_USE_LLM", "true").lower() == "true"
LLM_MODEL = "claude-haiku-4-5-20251001"
LLM_MAX_TOKENS = 200

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
        print(f"✔️ learned from session ➡️ {skill_name} ({high_count} HIGH, {med_count} MED, {low_count} LOW)")


def get_project_directory(hook_input: dict) -> str:
    """Get a validated project directory from environment or hook input.

    The resulting path is:
      * absolute
      * normalized
      * contained within SAFE_BASE_DIR
    If validation fails, SAFE_BASE_DIR is returned.
    """
    raw_dir = None

    env_dir = os.getenv("CLAUDE_PROJECT_DIR")
    if env_dir:
        raw_dir = env_dir
    elif isinstance(hook_input, dict):
        cwd_val = hook_input.get("cwd")
        if isinstance(cwd_val, str) and cwd_val.strip():
            raw_dir = cwd_val

    if not raw_dir:
        raw_dir = os.getcwd()

    # Validate and sanitize path string BEFORE Path() construction (CodeQL CWE-22)
    validated_dir = _validate_path_string(raw_dir)
    if validated_dir is None:
        return str(SAFE_BASE_DIR)

    try:
        # nosec B602 - CodeQL py/path-injection suppression
        # JUSTIFICATION: Defense-in-depth path validation prevents traversal:
        #   1. PRE-VALIDATION: _validate_path_string() rejects malicious patterns
        #   2. ROOT ANCHORING: All user input is interpreted under SAFE_BASE_DIR
        #   3. POST-VALIDATION: _is_relative_to() enforces SAFE_BASE_DIR boundary
        #   4. FALLBACK: Returns SAFE_BASE_DIR on any validation failure
        # See: .github/codeql/suppressions.yml and .agents/analysis/908-codeql-path-traversal-analysis.md

        base_path = SAFE_BASE_DIR

        # Treat validated_dir as relative to SAFE_BASE_DIR when possible.
        # If an absolute path is provided, normalize it but only use it if it
        # still falls under SAFE_BASE_DIR after resolution.
        user_path = Path(validated_dir).expanduser()
        if user_path.is_absolute():
            candidate = user_path.resolve(strict=False)  # lgtm[py/path-injection]
        else:
            candidate = (base_path / user_path).resolve(strict=False)  # lgtm[py/path-injection]
    except Exception:
        # Fall back to safe base directory on any resolution error
        return str(SAFE_BASE_DIR)

    # Enforce that the project directory is absolute and within SAFE_BASE_DIR
    if not candidate.is_absolute():
        return str(SAFE_BASE_DIR)

    if not _is_relative_to(candidate, SAFE_BASE_DIR):
        # Reject directories outside the allowed tree
        return str(SAFE_BASE_DIR)

    return str(candidate)


def get_safe_project_path(project_dir: str) -> Optional[Path]:
    """
    Resolve and validate the project directory against a safe root.

    This prevents path traversal or escaping the expected project tree when
    CLAUDE_PROJECT_DIR or hook-provided cwd are influenced by external input.
    """
    try:
        # Determine candidate safe root from environment or current working directory
        root_raw = os.getenv("CLAUDE_PROJECT_ROOT", os.getcwd())

        # Convert environment-provided root to a safe root within SAFE_BASE_DIR.
        # This encapsulates all handling of potentially tainted path strings.
        safe_root = _get_safe_root_from_env(root_raw)

        resolved_project = Path(project_dir).resolve()
    except OSError:
        # If resolution fails for any reason, treat as unsafe
        return None

    # Python 3.9+ has is_relative_to; fall back to relative_to otherwise
    if hasattr(resolved_project, "is_relative_to"):
        if not resolved_project.is_relative_to(safe_root):
            return None
    else:
        try:
            resolved_project.relative_to(safe_root)
        except ValueError:
            return None

    return resolved_project


def get_conversation_messages(hook_input: dict) -> List[dict]:
    """Extract messages from hook input conversation history."""
    return hook_input.get("messages", [])


def detect_skill_usage(messages: List[dict]) -> Dict[str, int]:
    """
    Detect skills mentioned or used in conversation.

    Returns dict of skill names to usage counts.

    Uses SKILL_PATTERNS (module-level) for pattern matching.
    Uses COMMAND_TO_SKILL (module-level) for slash command resolution.
    """
    detected_skills = {}
    conversation_text = ' '.join(msg.get('content', '') for msg in messages if isinstance(msg.get('content'), str))

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


def get_api_key() -> Optional[str]:
    """Get Anthropic API key from environment or config files."""
    # Try environment variable first
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        return api_key

    # Try .env file in project root (prefer validated project directory)
    env_root = PROJECT_DIR
    if env_root is None:
        env_value = os.getenv("CLAUDE_PROJECT_DIR")
        candidate_root: Optional[Path] = None
        if env_value:
            try:
                candidate_root = Path(env_value).resolve(strict=False)
            except Exception:
                candidate_root = None
        # Only trust CLAUDE_PROJECT_DIR if it is inside SAFE_BASE_DIR
        if candidate_root is not None and _is_relative_to(candidate_root, SAFE_BASE_DIR):
            env_root = candidate_root
        else:
            # Fall back to a safe default within the repository
            env_root = SAFE_BASE_DIR

    env_file = env_root / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"\'')

    return None


def classify_learning_by_llm(
    assistant_msg: str,
    user_response: str,
    skill_name: str
) -> Optional[Dict]:
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

        prompt = f"""Analyze this conversation exchange for skill-related learnings about the "{skill_name}" skill.

Assistant said:
{assistant_msg[:500]}

User responded:
{user_response}

Is this a learning signal? If yes, extract the learning and classify it:

Categories:
- HIGH (correction): Strong user corrections ("no", "wrong", "never do", "must use")
- HIGH (chestertons_fence): Removed something without understanding why
- HIGH (immediate_correction): User immediately asked to debug/fix right after
- MED (preference): Tool/approach preferences ("instead of using", "prefer to", "should use X")
- MED (success): Success patterns ("perfect", "excellent", "exactly", "that's it") - no qualifiers like "but"
- MED (edge_case): Important edge cases ("what if the/this", "ensure that", "make sure")
- MED (documentation): Documentation feedback ("update the docs", "needs documentation")
- MED (question): Short clarifying question (may indicate confusion)
- LOW (command_pattern): Repeated command patterns

Respond in JSON format:
{{
  "is_learning": true/false,
  "type": "correction|preference|success|edge_case|documentation|question|command_pattern|chestertons_fence|immediate_correction",
  "confidence": 0.0-1.0,
  "category": "High|Med|Low",
  "extracted_learning": "The key lesson learned",
  "reasoning": "Why this is/isn't a learning"
}}"""

        message = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}]
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


def extract_learnings(messages: List[dict], skill_name: str) -> Dict[str, List[dict]]:
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
        if re.search(r'(?i)\b(no\b|nope|not like that|that\'s wrong|incorrect|never do|always do|don\'t ever|must use|should not|avoid|stop)\b', user_response):
            confidence = 0.9 if len(re.findall(r'(?i)\b(no|wrong|never|must)\b', user_response)) > 1 else 0.85
            learning = {
                "type": "correction",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # HIGH: Chesterton's Fence (confidence 0.95)
        elif re.search(r'(?i)(trashed without understanding|removed without knowing|deleted without checking|why was this here)', user_response):
            learning = {
                "type": "chestertons_fence",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": 0.95,
                "method": "pattern"
            }

        # HIGH: Immediate corrections (confidence 0.8-0.85)
        elif re.search(r'(?i)\b(debug|root cause|correct|fix all|address|broken|error|issue|problem)\b', user_response) and len(user_response) < 200:
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
            r'works(?:\s+great|\s+perfectly|!)(?!\s+(?:but|however|except))|'  # "works great/perfectly!" not followed by "but"
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
            confidence = 0.65 if re.search(r'(?i)\b(ensure|make sure|verify)\b', user_response) else 0.6
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
            confidence = 0.65 if re.search(r'(?i)\b(must|should|needs?)\b', user_response) else 0.6
            learning = {
                "type": "documentation",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # MED: Clarifying questions (confidence 0.55-0.6)
        elif re.search(r'\?', user_response) and len(user_response) < 50 and re.search(r'(?i)^(why|how|what|when|where|can|does|is|are)\b', user_response):
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
            r'(?i)^(?:ok|okay|sure|got it|sounds good|thanks|thank you|yep|yeah|alright|fine|k|kk)(?:[.!,]?\s*)?$',
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
    learnings: Dict[str, List[dict]],
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
            print(f"Invalid project directory: '{project_dir}' does not resolve to absolute path", file=sys.stderr)
            return False
        if not _is_relative_to(allowed_dir, SAFE_BASE_DIR):
            print(f"Path traversal attempt detected: '{allowed_dir}' is outside safe base directory", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Path validation error for project_dir: {e}", file=sys.stderr)
        return False

    # Step 2: Validate skill_name does not contain path traversal characters
    # This prevents attacks via skill names like "../../../etc/passwd" or "..\\attack"
    # Regex allowlist: only alphanumeric, underscore, and hyphen characters permitted
    if not re.fullmatch(r"[A-Za-z0-9_-]+", skill_name):
        print(f"Invalid skill name: '{skill_name}' contains unsupported characters", file=sys.stderr)
        return False

    # Step 3: Construct paths using validated allowed_dir
    memories_dir = allowed_dir / ".serena" / "memories"

    # Ensure directory exists before resolving paths
    memories_dir.mkdir(parents=True, exist_ok=True)

    # lgtm[py/path-injection]
    # CodeQL suppression: skill_name validated in Step 2 to not contain path traversal chars
    memory_path = memories_dir / f"{skill_name}{OBSERVATIONS_SUFFIX}"

    # Step 4: Validate resolved path is within project directory
    try:
        resolved_path = memory_path.resolve()
        # Include directory separator to prevent prefix attacks
        # e.g., "/home/user" should not match "/home/usermalicious"
        if not str(resolved_path).startswith(str(allowed_dir) + os.sep):
            print(f"Path traversal attempt detected: '{resolved_path}' is outside project directory", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Path validation error for memory_path: {e}", file=sys.stderr)
        return False

    # Step 5: Use validated resolved_path for all file operations
    # Read existing memory or create new
    # lgtm[py/path-injection]
    # CodeQL suppression: resolved_path validated in Step 4 to be within project directory
    if resolved_path.exists():
        # lgtm[py/path-injection]
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
            method_tag = f" [LLM]" if learning.get("method") == "haiku-llm" else ""
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
                method_tag = f" [LLM]" if learning.get("method") == "haiku-llm" else ""
                preference_items += f"- {source}{method_tag} (Session {session_id}, {today})\n"

        if preference_items:
            pattern = r'(## Preferences \(MED confidence\)\r?\n)'
            new_content = re.sub(pattern, r'\1' + preference_items, new_content)

        # Edge Cases: edge cases and questions
        edge_case_items = ""
        for learning in learnings["Med"]:
            if learning["type"] in ["edge_case", "question"]:
                source = escape_replacement_string(learning["source"])
                method_tag = f" [LLM]" if learning.get("method") == "haiku-llm" else ""
                edge_case_items += f"- {source}{method_tag} (Session {session_id}, {today})\n"

        if edge_case_items:
            pattern = r'(## Edge Cases \(MED confidence\)\r?\n)'
            new_content = re.sub(pattern, r'\1' + edge_case_items, new_content)

        # Documentation feedback
        documentation_items = ""
        for learning in learnings["Med"]:
            if learning["type"] == "documentation":
                source = escape_replacement_string(learning["source"])
                method_tag = f" [LLM]" if learning.get("method") == "haiku-llm" else ""
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
                method_tag = f" [LLM]" if learning.get("method") == "haiku-llm" else ""
                other_med_items += f"- [{learning_type}] {source}{method_tag} (Session {session_id}, {today})\n"

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
    # lgtm[py/path-injection]
    # CodeQL suppression: resolved_path validated in Step 4 to be within project directory
    resolved_path.write_text(new_content, encoding='utf-8')

    return True


def main():
    """Main hook execution."""
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

        messages = get_conversation_messages(hook_input)

        if not messages:
            return 0

        # Detect skills used in this session
        detected_skills = detect_skill_usage(messages)

        if not detected_skills:
            return 0

        # Get session ID from today's session log
        # lgtm[py/path-injection]
        # CodeQL suppression: project_dir is validated against safe root and used only for reading session logs
        sessions_dir = safe_project_path / ".agents" / "sessions"
        today = datetime.now().strftime("%Y-%m-%d")

        # Check if sessions directory exists before globbing to avoid silent failures
        # lgtm[py/path-injection]
        # CodeQL suppression: sessions_dir constructed from validated project_dir for read-only glob
        if sessions_dir.exists():
            # lgtm[py/path-injection]
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

    except Exception as e:
        # Silent failure - don't block session end
        print(f"Skill learning hook error: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
