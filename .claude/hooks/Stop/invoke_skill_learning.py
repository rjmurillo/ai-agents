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
from typing import Dict, List, Optional, Tuple

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
    """Get project directory from environment or hook input."""
    if os.getenv("CLAUDE_PROJECT_DIR"):
        return os.getenv("CLAUDE_PROJECT_DIR")
    return hook_input.get("cwd", os.getcwd())


def get_conversation_messages(hook_input: dict) -> List[dict]:
    """Extract messages from hook input conversation history."""
    return hook_input.get("messages", [])


def detect_skill_usage(messages: List[dict]) -> Dict[str, int]:
    """
    Detect skills mentioned or used in conversation.

    Returns dict of skill names to usage counts.
    """
    skill_patterns = {
        'github': ['gh pr', 'gh issue', '.claude/skills/github', 'github skill', '/pr-review'],
        'memory': ['search memory', 'forgetful', 'serena', 'memory-first', 'ADR-007'],
        'session-init': ['/session-init', 'session log', 'session protocol'],
        'SkillForge': ['SkillForge', 'create skill', 'synthesis panel'],
        'adr-review': ['adr-review', 'ADR files', 'architecture decision'],
        'incoherence': ['incoherence skill', 'detect incoherence', 'reconcile'],
        'retrospective': ['retrospective', 'session end', 'reflect'],
        'reflect': ['reflect', 'learn from this', 'what did we learn'],
        'pr-comment-responder': ['pr-comment-responder', 'review comments', 'feedback items'],
        'code-review': ['code review', 'style guide', 'security patterns'],
        'api-design': ['API design', 'REST', 'endpoint', 'versioning'],
        'testing': ['test', 'coverage', 'mocking', 'assertion'],
        'documentation': ['documentation', 'docs/', 'README', 'write doc'],
    }

    detected_skills = {}
    conversation_text = ' '.join(msg.get('content', '') for msg in messages if isinstance(msg.get('content'), str))

    # Detect skills from .claude/skills/{skill-name} references
    skill_path_pattern = re.compile(r'\.claude[/\\]skills[/\\]([a-z0-9-]+)')
    for match in skill_path_pattern.finditer(conversation_text):
        skill_name = match.group(1)
        detected_skills[skill_name] = detected_skills.get(skill_name, 0) + 1

    # Detect skills from slash commands
    slash_cmd_pattern = re.compile(r'/([a-z][a-z0-9-]+)')
    command_to_skill = {
        'pr-review': 'github',
        'session-init': 'session-init',
        'memory-search': 'memory',
        'memory-list': 'memory',
        'research': 'research-and-incorporate',
    }

    for match in slash_cmd_pattern.finditer(conversation_text):
        cmd_name = match.group(1)
        if cmd_name in command_to_skill:
            skill_name = command_to_skill[cmd_name]
            detected_skills[skill_name] = detected_skills.get(skill_name, 0) + 1

    # Pattern-based detection
    for skill, patterns in skill_patterns.items():
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


def test_skill_context(text: str, skill: str) -> bool:
    """Check if skill is mentioned in the given text context."""
    patterns = {
        'github': ['gh pr', 'gh issue', '.claude/skills/github', 'github skill', '/pr-review'],
        'memory': ['search memory', 'forgetful', 'serena', 'memory-first', 'ADR-007'],
        'session-init': ['/session-init', 'session log', 'session protocol'],
        'SkillForge': ['SkillForge', 'create skill', 'synthesis panel'],
        'adr-review': ['adr-review', 'ADR files', 'architecture decision'],
        'incoherence': ['incoherence skill', 'detect incoherence', 'reconcile'],
        'retrospective': ['retrospective', 'session end', 'reflect'],
        'reflect': ['reflect', 'learn from this', 'what did we learn'],
        'pr-comment-responder': ['pr-comment-responder', 'review comments', 'feedback items'],
        'code-review': ['code review', 'style guide', 'security patterns'],
        'api-design': ['API design', 'REST', 'endpoint', 'versioning'],
        'testing': ['test', 'coverage', 'mocking', 'assertion'],
        'documentation': ['documentation', 'docs/', 'README', 'write doc'],
    }

    if skill in patterns:
        for pattern in patterns[skill]:
            if re.search(re.escape(pattern), text, re.IGNORECASE):
                return True
    return False


def get_api_key() -> Optional[str]:
    """Get Anthropic API key from environment or config files."""
    # Try environment variable first
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        return api_key

    # Try .env file in project root
    env_file = Path.cwd() / ".env"
    if env_file.exists():
        with open(env_file) as f:
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
- MED (preference): Tool/approach preferences ("instead of", "prefer", "should use")
- MED (success): Success patterns ("perfect", "great", "excellent", "exactly")
- MED (edge_case): Important edge cases or questions ("what if", "ensure", "make sure")
- MED (question): Short clarifying question (may indicate confusion)
- LOW (command_pattern): Repeated command patterns

Respond in JSON format:
{{
  "is_learning": true/false,
  "type": "correction|preference|success|edge_case|question|command_pattern|chestertons_fence|immediate_correction",
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

        # Handle markdown code blocks
        if "```" in response_text:
            parts = response_text.split("```")
            if len(parts) >= 2:
                response_text = parts[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:].strip()

        result = json.loads(response_text)

        if not result.get("is_learning"):
            return None

        return {
            "type": result["type"],
            "confidence": result["confidence"],
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
        if not test_skill_context(context_window, skill_name):
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
        elif re.search(r'(?i)\b(instead of|rather than|prefer|should use|use .+ not|better to)\b', user_response):
            confidence = 0.75 if "prefer" in user_response.lower() or "should use" in user_response.lower() else 0.7
            learning = {
                "type": "preference",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # MED: Success patterns (confidence 0.65-0.7)
        elif re.search(r'(?i)^(?:(?:ok|okay|yeah|yep|sure|alright)[,\s]+)?(perfect|great|excellent|exactly|that\'s it|good job|well done|works|yes(?!\s*,?\s*but)|correct(?!\s*,?\s*but)|right(?!\s*,?\s*about))\b', user_response):
            confidence = 0.7 if "perfect" in user_response.lower() or "excellent" in user_response.lower() else 0.65
            learning = {
                "type": "success",
                "source": user_response[:150],
                "context": assistant_content[:150],
                "confidence": confidence,
                "method": "pattern"
            }

        # MED: Edge cases (confidence 0.6-0.65)
        elif re.search(r'(?i)(what if|how does|how will|what about|don\'t want to forget|ensure|make sure|needs to).*\?', user_response):
            confidence = 0.65 if "ensure" in user_response.lower() or "make sure" in user_response.lower() else 0.6
            learning = {
                "type": "edge_case",
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
    """Escape special characters for regex replacement."""
    return text.replace('$', '$$')


def update_skill_memory(
    project_dir: str,
    skill_name: str,
    learnings: Dict[str, List[dict]],
    session_id: str
) -> bool:
    """
    Update skill observation memory file with new learnings.

    Returns True if successful, False otherwise.
    """
    # Security: Path traversal prevention (CWE-22)
    allowed_dir = Path(project_dir).resolve()
    memories_dir = allowed_dir / ".serena" / "memories"
    memory_path = memories_dir / f"{skill_name}-observations.md"

    # Validate path is within project directory
    try:
        resolved_path = memory_path.resolve()
        if not str(resolved_path).startswith(str(allowed_dir)):
            print(f"Path traversal attempt detected: '{resolved_path}' is outside project directory", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Path validation error: {e}", file=sys.stderr)
        return False

    # Ensure directory exists
    memories_dir.mkdir(parents=True, exist_ok=True)

    # Read existing memory or create new
    if memory_path.exists():
        existing_content = memory_path.read_text(encoding='utf-8')
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        existing_content = f"""# Skill Observations: {skill_name}

**Last Updated**: {today}
**Sessions Analyzed**: 0

## Constraints (HIGH confidence)

## Preferences (MED confidence)

## Edge Cases (MED confidence)

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
        new_content = re.sub(pattern, f'\\1{constraint_items}', new_content)

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
            new_content = re.sub(pattern, f'\\1{preference_items}', new_content)

        # Edge Cases: edge cases and questions
        edge_case_items = ""
        for learning in learnings["Med"]:
            if learning["type"] in ["edge_case", "question"]:
                source = escape_replacement_string(learning["source"])
                method_tag = f" [LLM]" if learning.get("method") == "haiku-llm" else ""
                edge_case_items += f"- {source}{method_tag} (Session {session_id}, {today})\n"

        if edge_case_items:
            pattern = r'(## Edge Cases \(MED confidence\)\r?\n)'
            new_content = re.sub(pattern, f'\\1{edge_case_items}', new_content)

    # LOW: Command patterns
    if learnings["Low"]:
        low_items = ""
        for learning in learnings["Low"]:
            source = escape_replacement_string(learning["source"])
            low_items += f"- {source} (Session {session_id}, {today})\n"

        pattern = r'(## Notes for Review \(LOW confidence\)\r?\n)'
        new_content = re.sub(pattern, f'\\1{low_items}', new_content)

    # Update session count
    match = re.search(r'Sessions Analyzed: (\d+)', new_content)
    if match:
        count = int(match.group(1)) + 1
        new_content = re.sub(r'Sessions Analyzed: \d+', f'Sessions Analyzed: {count}', new_content)

    # Update last updated date
    new_content = re.sub(r'\*\*Last Updated\*\*: [\d-]+', f'**Last Updated**: {today}', new_content)

    # Write memory file
    memory_path.write_text(new_content, encoding='utf-8')

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
        messages = get_conversation_messages(hook_input)

        if not messages:
            return 0

        # Detect skills used in this session
        detected_skills = detect_skill_usage(messages)

        if not detected_skills:
            return 0

        # Get session ID from today's session log
        sessions_dir = Path(project_dir) / ".agents" / "sessions"
        today = datetime.now().strftime("%Y-%m-%d")
        session_logs = sorted(
            sessions_dir.glob(f"{today}-session-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        session_id = session_logs[0].stem if session_logs else f"{today}-session-unknown"

        # Process each detected skill
        for skill_name in detected_skills:
            learnings = extract_learnings(messages, skill_name)

            high_count = len(learnings["High"])
            med_count = len(learnings["Med"])
            low_count = len(learnings["Low"])

            # Only update if learnings meet threshold
            if high_count >= 1 or med_count >= 2 or low_count >= 3:
                updated = update_skill_memory(project_dir, skill_name, learnings, session_id)

                if updated:
                    write_learning_notification(skill_name, high_count, med_count, low_count)

        return 0

    except Exception as e:
        # Silent failure - don't block session end
        print(f"Skill learning hook error: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
