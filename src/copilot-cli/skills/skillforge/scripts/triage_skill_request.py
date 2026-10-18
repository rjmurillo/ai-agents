#!/usr/bin/env python3
"""
triage_skill_request.py - Intelligent skill routing from any user input

Part of the skillforge skill (Phase 0: Skill Triage).

Analyzes ANY user input (prompt, error, code, URL, question, request) and
determines the best action:
- USE_EXISTING: Existing skill handles this perfectly
- IMPROVE_EXISTING: Existing skill is close but needs enhancement
- CREATE_NEW: No good match, create new skill
- COMPOSE: Multiple skills needed, suggest chain
- CLARIFY: Ambiguous input, need more information

Usage:
    python triage_skill_request.py "create a skill for code review"
    python triage_skill_request.py "help me debug this error" --json
    python triage_skill_request.py "TypeError: Cannot read property 'map'"

Exit Codes:
    0 - Success
    1 - General failure
    2 - Skill index not found (run discover_skills.py first)
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ===========================================================================
# RESULT TYPES
# ===========================================================================


@dataclass
class Result:
    """Standard result object for script operations."""

    success: bool
    message: str
    data: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "errors": self.errors,
            "warnings": self.warnings,
            "timestamp": datetime.now().isoformat(),
        }


class Action:
    """Possible triage actions."""

    USE_EXISTING = "USE_EXISTING"
    IMPROVE_EXISTING = "IMPROVE_EXISTING"
    CREATE_NEW = "CREATE_NEW"
    COMPOSE = "COMPOSE"
    CLARIFY = "CLARIFY"


class InputCategory:
    """Categories of user input."""

    EXPLICIT_CREATE = "explicit_create"  # "create a skill for X"
    EXPLICIT_IMPROVE = "explicit_improve"  # "improve the X skill"
    SKILL_QUESTION = "skill_question"  # "do I have a skill for X?"
    TASK_REQUEST = "task_request"  # "help me with X", "I need to X"
    ERROR_MESSAGE = "error_message"  # Stack traces, errors
    CODE_SNIPPET = "code_snippet"  # Code pasted
    URL_CONTENT = "url_content"  # URLs
    GENERAL = "general"  # Unclear


# ===========================================================================
# INPUT CLASSIFICATION
# ===========================================================================

# Patterns for detecting input category
# The first pattern skips "the build skill" and "my make skill": there the verb is
# the name of an existing skill, not a request to create one.
EXPLICIT_CREATE_PATTERNS = [
    r"(?<!\bthe\s)(?<!\bmy\s)(?<!\bour\s)(?<!\bthis\s)"
    r"\b(?:create|build|make|design|develop)\s+(?:a\s+)?(?:new\s+)?skill\b",
    r"\b(?:new|custom)\s+skill\s+(?:for|to)\b",
    r"\bultimate\s+skill\b",
]

# A bare "skillforge:" or "skillforge " prefix only addresses the router. It is
# checked after the improve patterns so "improve the skillforge skill" stays an
# improve request.
SKILLFORGE_PREFIX_PATTERN = r"\bskillforge[:\s]"

EXPLICIT_IMPROVE_PATTERNS = [
    r"\b(?:improve|enhance|update|upgrade|fix|extend)\s+(?:the\s+)?(?:\w+\s+)?skill\b",
    r"\bskill\s+(?:needs?|could\s+use|should\s+have)\b",
    r"\b(?:add|include)\s+(?:to|in)\s+(?:the\s+)?\w+\s+skill\b",
]

SKILL_QUESTION_PATTERNS = [
    r"\bdo\s+(?:i|we)\s+have\s+(?:a\s+)?skill\b",
    r"\bwhich\s+skill\b",
    r"\bwhat\s+skill\b",
    r"\brecommend\s+(?:a\s+)?skill\b",
    r"\bskill\s+for\b",
    r"\bfind\s+(?:a\s+)?skill\b",
    r"\bsuggest\s+(?:a\s+)?skill\b",
    r"\bis\s+there\s+(?:a\s+)?skill\b",
]

TASK_REQUEST_PATTERNS = [
    r"\b(?:help|assist)\s+(?:me\s+)?(?:with|to)\b",
    r"\bi\s+need\s+to\b",
    r"\bhow\s+(?:do\s+i|can\s+i|to)\b",
    r"\bcan\s+you\b",
    r"\bplease\b.*\b(?:help|do|make|create|fix|build)\b",
]

ERROR_PATTERNS = [
    r"Error:",
    r"Exception:",
    r"TypeError:",
    r"ReferenceError:",
    r"SyntaxError:",
    r"at\s+\S+\s+\(",
    r"Traceback \(most recent call",
    r'File "[^"]+", line \d+',
]

CODE_PATTERNS = [
    r"^\s*(function|const|let|var|class|import|export|def|async|await)\s+",
    r"^\s*<[a-zA-Z][^>]*>",
    r"=>",
    r"^\s*@\w+",
]

URL_PATTERNS = [
    r"https?://[^\s]+",
]


def _explicit_create(query_lower: str, signals: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Record the requested purpose and classify the input as an explicit create."""
    # SECURITY: Use bounded character class to prevent ReDoS (polynomial backtracking)
    purpose_match = re.search(r"skill\s+(?:for|to)\s+([a-zA-Z0-9 \-,\'\"]{1,200})", query_lower)
    if purpose_match:
        signals["extracted_purpose"] = purpose_match.group(1).strip()
    return InputCategory.EXPLICIT_CREATE, signals


def classify_input(query: str) -> tuple[str, dict[str, Any]]:
    """
    Classify user input into a category and extract signals.

    Returns:
        Tuple of (category, signals_dict)
    """
    query_lower = query.lower()
    signals = {
        "has_skill_mention": "skill" in query_lower,
        "has_error": False,
        "has_code": False,
        "has_url": False,
        "mentioned_skill_name": None,
        "extracted_purpose": None,
    }

    # Check for explicit skill creation request
    if any(re.search(pattern, query_lower) for pattern in EXPLICIT_CREATE_PATTERNS):
        return _explicit_create(query_lower, signals)

    # Check for explicit improvement request
    for pattern in EXPLICIT_IMPROVE_PATTERNS:
        if re.search(pattern, query_lower):
            # Try to extract skill name
            skill_match = re.search(
                r"(?:improve|enhance|update|fix)\s+(?:the\s+)?(\w+(?:-\w+)*)\s+skill", query_lower
            )
            if skill_match:
                signals["mentioned_skill_name"] = skill_match.group(1)
            return InputCategory.EXPLICIT_IMPROVE, signals

    # A "skillforge:" prefix with no improve verb asks the router to create.
    if re.search(SKILLFORGE_PREFIX_PATTERN, query_lower):
        return _explicit_create(query_lower, signals)

    # Check for skill question
    for pattern in SKILL_QUESTION_PATTERNS:
        if re.search(pattern, query_lower):
            return InputCategory.SKILL_QUESTION, signals

    # Check for error message
    for pattern in ERROR_PATTERNS:
        if re.search(pattern, query, re.MULTILINE):
            signals["has_error"] = True
            return InputCategory.ERROR_MESSAGE, signals

    # Check for code snippet
    for pattern in CODE_PATTERNS:
        if re.search(pattern, query, re.MULTILINE):
            signals["has_code"] = True
            return InputCategory.CODE_SNIPPET, signals

    # Check for URL
    for pattern in URL_PATTERNS:
        if re.search(pattern, query):
            signals["has_url"] = True
            return InputCategory.URL_CONTENT, signals

    # Check for task request
    for pattern in TASK_REQUEST_PATTERNS:
        if re.search(pattern, query_lower):
            return InputCategory.TASK_REQUEST, signals

    return InputCategory.GENERAL, signals


# ===========================================================================
# SKILL MATCHING (from skillrecommender)
# ===========================================================================


def get_index_path() -> Path:
    """Get the skill index file path."""
    return Path.home() / ".cache" / "skillrecommender" / "skill_index.json"


def load_skill_index() -> dict | None:
    """Load skill index from disk."""
    index_path = get_index_path()
    if not index_path.exists():
        return None
    try:
        return json.loads(index_path.read_text())
    except json.JSONDecodeError:
        return None


# ===========================================================================
# UNIVERSAL DOMAIN SYNONYMS
# ===========================================================================
# These are CONCEPT-based synonyms, not tied to any specific skill names.
# They help match user queries to skill domains regardless of what skills exist.

DOMAIN_SYNONYMS = {
    # Document formats - maps concepts to related terms
    "spreadsheet": [
        "excel",
        "xlsx",
        "xls",
        "csv",
        "workbook",
        "tabular",
        "data table",
        "cells",
        "rows columns",
    ],
    "document": ["document", "word", "docx", "doc", "text document", "write document", "report"],
    "presentation": ["powerpoint", "pptx", "slides", "deck", "slide deck", "keynote", "pitch"],
    "pdf": ["pdf", "export pdf", "portable document"],
    # Development concepts
    "debugging": [
        "debug",
        "error",
        "exception",
        "stack trace",
        "traceback",
        "crash",
        "debugging",
        "fix bug",
        "breakpoint",
        "investigate",
    ],
    "testing": [
        "test",
        "unit test",
        "integration test",
        "e2e",
        "coverage",
        "spec",
        "tdd",
        "jest",
        "vitest",
        "pytest",
        "mocha",
    ],
    "security": [
        "security",
        "vulnerability",
        "owasp",
        "audit",
        "secure",
        "penetration",
        "pentest",
        "xss",
        "injection",
    ],
    "code_quality": [
        "review",
        "code review",
        "pr review",
        "pull request",
        "refactor",
        "clean code",
        "code smell",
        "lint",
    ],
    "database": [
        "database",
        "db",
        "schema",
        "migration",
        "sql",
        "postgres",
        "mysql",
        "mongodb",
        "data model",
        "orm",
    ],
    "api": ["api", "rest", "graphql", "endpoint", "openapi", "swagger", "restful", "http"],
    "frontend": [
        "ui",
        "ux",
        "frontend",
        "react",
        "vue",
        "angular",
        "css",
        "styling",
        "component",
        "user interface",
    ],
    "accessibility": [
        "accessibility",
        "a11y",
        "wcag",
        "screen reader",
        "aria",
        "keyboard navigation",
    ],
    "performance": [
        "performance",
        "optimize",
        "slow",
        "speed",
        "fast",
        "bottleneck",
        "profiling",
        "cache",
    ],
    "authentication": [
        "auth",
        "authenticate",
        "authorize",
        "authorization",
        "login",
        "authentication",
        "oauth",
        "jwt",
        "session",
        "sign in",
        "sign up",
        "password",
    ],
    "deployment": [
        "deploy",
        "deployment",
        "production",
        "release",
        "ship",
        "hosting",
        "ci",
        "cd",
        "pipeline",
    ],
    "devops": ["docker", "kubernetes", "k8s", "container", "helm", "terraform", "infrastructure"],
    "documentation": ["documentation", "docs", "readme", "changelog", "api docs", "jsdoc"],
    "architecture": [
        "architecture",
        "system design",
        "design pattern",
        "microservices",
        "monolith",
    ],
    "workflow": [
        "flowchart",
        "diagram",
        "workflow",
        "process",
        "swimlane",
        "sequence diagram",
        "uml",
    ],
    # AI/ML concepts
    "ai_ml": [
        "ai",
        "ml",
        "machine learning",
        "llm",
        "rag",
        "embedding",
        "langchain",
        "prompt",
        "model",
    ],
    # Creative
    "visual": ["visual", "image", "graphic", "art", "canvas", "design"],
}


# Words that frame a request without describing its subject. "create a skill for
# X" is scaffolding around X: scoring it would match every meta-skill.
SCAFFOLDING_WORDS = frozenset(
    {
        # Articles, prepositions, conjunctions, pronouns, auxiliaries
        "a",
        "an",
        "the",
        "for",
        "with",
        "to",
        "of",
        "and",
        "or",
        "in",
        "on",
        "at",
        "by",
        "from",
        "into",
        "through",
        "about",
        "that",
        "this",
        "it",
        "its",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "is",
        "are",
        "be",
        "do",
        "have",
        "want",
        "need",
        "help",
        "please",
        "can",
        "will",
        "would",
        "should",
        # Creation vocabulary
        "create",
        "creating",
        "make",
        "making",
        "build",
        "building",
        "new",
        "custom",
        "skill",
        "skills",
        # "a skill for running X" frames the request. With "running" as a content
        # term the test skill (which describes running tests) explains two terms of
        # the issue #6647 repro, escapes the single-term cap, and scores 64.
        "running",
    }
)

# Matched terms may carry an inflection ("test" matches "tests", "testing",
# "tested") but never extend into another word ("test" must not match "attest").
# A final consonant also doubles before "ing" and "ed" ("debug" matches
# "debugging", "ship" matches "shipped").
_DOUBLING_CONSONANTS = frozenset("bdglmnprt")

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

# Step 8 of calculate_match_score. A skill that explains none of the query terms
# keeps COVERAGE_FLOOR of its raw score, so a synonym match is discounted, not erased.
COVERAGE_FLOOR = 0.5
# One explained term in a request of this many content terms is not a match; the
# cap sits one point under the 50 point CREATE_NEW boundary.
SINGLE_TERM_MIN_QUERY_TERMS = 3
SINGLE_TERM_SCORE_CAP = 49
# A query word shorter than this earns no partial-name credit ("adr", "api").
MIN_PARTIAL_NAME_LENGTH = 4
# Categories where the user asks for a skill by name ("do I have a skill for
# build?", "improve the test skill"). Only these keep a scaffolding-named skill
# matchable and exempt an exact one-word name from the single-term cap.
NAME_LOOKUP_CATEGORIES = frozenset({InputCategory.SKILL_QUESTION, InputCategory.EXPLICIT_IMPROVE})


def tokenize_for_scoring(query: str) -> list[str]:
    """
    Split a query into lowercase content terms, dropping request scaffolding.

    Order is kept and duplicates are removed. Single characters are dropped.
    """
    seen: set[str] = set()
    tokens: list[str] = []
    for token in _TOKEN_PATTERN.findall(query.lower()):
        if len(token) < 2 or token in SCAFFOLDING_WORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def is_scaffolding_phrase(phrase: str) -> bool:
    """True when every word of the phrase is request scaffolding ("build", "make a")."""
    words = _TOKEN_PATTERN.findall(phrase.lower())
    return bool(words) and all(word in SCAFFOLDING_WORDS for word in words)


def contains_term(text: str, term: str) -> bool:
    """True when term appears in text as a whole word or phrase, allowing inflection."""
    term = term.lower()
    suffixes = ["s", "es", "ing", "ed"]
    if term and term[-1] in _DOUBLING_CONSONANTS:
        suffixes += [re.escape(term[-1]) + "ing", re.escape(term[-1]) + "ed"]
    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?:" + "|".join(suffixes) + r")?(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def _stems(token: str) -> set[str]:
    """Return the token plus each form with one inflectional suffix removed."""
    forms = {token}
    for suffix in ("ing", "es", "ed", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            forms.add(token[: -len(suffix)])
    return forms


def _skill_text_forms(skill: dict[str, Any]) -> set[str]:
    """Return every word form in the skill name, keywords, triggers, and description."""
    skill_text = " ".join(
        [
            str(skill.get("name", "")).replace("-", " ").replace("_", " "),
            str(skill.get("description", "")),
            " ".join(str(k) for k in skill.get("keywords", [])),
            " ".join(str(t) for t in skill.get("triggers", [])),
        ]
    )
    forms: set[str] = set()
    for word in _TOKEN_PATTERN.findall(skill_text.lower()):
        forms |= _stems(word)
    return forms


def count_explained_terms(
    tokens: list[str], skill: dict[str, Any], synonym_terms: frozenset[str] = frozenset()
) -> int:
    """
    Count query content terms the skill explains.

    A term is explained when the skill name, keywords, or description contain it,
    or when it is a synonym of a domain the skill declares (synonym_terms). The
    second path keeps a query like "excel workbook" covered by a skill that names
    the "spreadsheet" domain but never lists "excel" or "workbook".
    """
    explained_forms = _skill_text_forms(skill)
    synonym_forms: set[str] = set()
    for term in synonym_terms:
        synonym_forms |= _stems(term)
    return sum(1 for t in tokens if _stems(t) & (explained_forms | synonym_forms))


def calculate_coverage(
    tokens: list[str], skill: dict[str, Any], synonym_terms: frozenset[str] = frozenset()
) -> float:
    """
    Fraction of query content terms the skill name, keywords, description, or
    declared domain synonyms explain.

    Returns 1.0 when the query has no content terms, so a scaffolding-only
    request is not penalized for words it does not have.
    """
    if not tokens:
        return 1.0
    return count_explained_terms(tokens, skill, synonym_terms) / len(tokens)


def domain_synonym_terms(
    query_domains: list[tuple[str, list[str]]], skill_domains: set[str]
) -> frozenset[str]:
    """Collect the query words that matched a synonym of any domain the skill declares."""
    terms: set[str] = set()
    for domain, matched_terms in query_domains:
        if domain in skill_domains:
            for matched in matched_terms:
                terms.update(_TOKEN_PATTERN.findall(matched.lower()))
    return frozenset(terms)


def detect_query_domains(query: str) -> list[tuple[str, list[str]]]:
    """
    Detect which domains a query relates to using universal synonyms.

    Terms match on word boundaries, so "ci" does not fire inside "social" and
    "test" does not fire inside "attest". Inflected forms ("testing") still match.

    Returns:
        List of (domain_name, matched_terms) tuples, sorted by match count
    """
    query_lower = query.lower()
    detected = []

    for domain, synonyms in DOMAIN_SYNONYMS.items():
        matched_terms = [term for term in synonyms if contains_term(query_lower, term)]
        if matched_terms:
            detected.append((domain, matched_terms))

    # Sort by number of matches (more matches = stronger signal)
    detected.sort(key=lambda x: len(x[1]), reverse=True)
    return detected


def calculate_match_score(
    query: str, skill: dict[str, Any], category: str | None = None
) -> tuple[float, list[str]]:
    """
    Calculate how well a skill matches the query using UNIVERSAL domain matching.

    Returns:
        Tuple of (score 0-100, list of match reasons)
    """
    score, reasons, ceiling = score_skill(query, skill, category)
    return apply_ceiling(score, ceiling, reasons), reasons


def apply_ceiling(score: float, ceiling: int | None, reasons: list[str]) -> float:
    """Clamp score to the ceiling and record the cap when it lowered the score."""
    if ceiling is not None and score > ceiling:
        reasons.append("capped: one shared term in a long request")
        return ceiling
    return score


def score_skill(
    query: str, skill: dict[str, Any], category: str | None = None
) -> tuple[float, list[str], int | None]:
    """
    Score one skill against the query and report any score ceiling.

    The ceiling is set when a long request rests on a single shared term. The
    caller applies it after context boosts, so a boost cannot lift the score back
    over the CREATE_NEW boundary. The ceiling is set whatever the pre-boost score
    is: a score of 45 would otherwise be boosted past 50.

    category is the InputCategory of the request. A name lookup (SKILL_QUESTION,
    EXPLICIT_IMPROVE) keeps a scaffolding-named skill matchable.

    This function does NOT use any hardcoded skill names - it works purely based on:
    1. Domain detection from query using universal synonyms
    2. Matching detected domains against skill's domains/keywords/description
    3. Direct name/trigger matching from whatever skills exist

    Returns:
        Tuple of (score 0-100, list of match reasons, score ceiling or None)
    """
    query_lower = query.lower()
    # Content terms only: "create", "skill", "with" and similar scaffolding
    # words would otherwise match meta-skills for every creation request.
    content_tokens = tokenize_for_scoring(query)
    query_words = set(content_tokens)

    skill_name = skill.get("name", "").lower()
    skill_keywords = set(k.lower() for k in skill.get("keywords", []))
    skill_triggers = set(t.lower() for t in skill.get("triggers", []))
    skill_domains = set(d.lower() for d in skill.get("domains", []))
    skill_description = skill.get("description", "").lower()

    score = 0
    reasons = []

    # Step 1: Detect what domains the query is about
    query_domains = detect_query_domains(query)

    # Step 2: Check if skill's domains match detected query domains (STRONG signal)
    for domain, matched_terms in query_domains:
        # Direct domain match (skill has this domain in its domains list)
        if domain in skill_domains:
            # Strong domain match - base 35 + bonus for multiple term matches
            domain_score = min(50, 35 + len(matched_terms) * 5)
            score += domain_score
            reasons.append(f"domain: {domain} ({', '.join(matched_terms[:2])})")
            break  # Only count best domain match

    # Step 3: Check if query domain terms appear in skill keywords/description
    keyword_matched = False
    for domain, matched_terms in query_domains:
        # Check if domain synonyms appear in skill's keywords
        for term in matched_terms:
            if term in skill_keywords:
                score += 15
                reasons.append(f"keyword: {term}")
                keyword_matched = True
                break
        if keyword_matched:
            break

        # Also check if the DOMAIN NAME itself is in keywords (e.g., "spreadsheet" domain, skill has "spreadsheet" keyword)
        if domain in skill_keywords or domain.replace("_", " ") in skill_keywords:
            score += 15
            reasons.append(f"keyword: {domain}")
            keyword_matched = True
            break

    # Check if domain terms appear in skill's description
    desc_matched = False
    for domain, matched_terms in query_domains:
        for term in matched_terms:
            if contains_term(skill_description, term):
                score += 10
                reasons.append(f"description: {term}")
                desc_matched = True
                break
        if desc_matched:
            break

        # Also check domain name in description
        if contains_term(skill_description, domain):
            score += 10
            reasons.append(f"description: {domain}")
            desc_matched = True
            break

    # Step 4: Direct skill name match (works for any skill name). Whole words
    # only, hyphens read as spaces, so "test" never matches inside "attest". A
    # name made only of scaffolding words ("build", "make") is skipped when the
    # user creates something: "build a skill for X" frames the request, it does not
    # ask for the skill named build. In a name lookup ("do I have a skill for
    # build?") the exact name still matches.
    spaced_name = re.sub(r"[-_\s]+", " ", skill_name).strip()
    spaced_query = re.sub(r"[-_\s]+", " ", query_lower)
    is_lookup = category in NAME_LOOKUP_CATEGORIES
    scaffolding_named = is_scaffolding_phrase(spaced_name)
    exact_name = (
        bool(spaced_name)
        and re.search(rf"(?<![a-z0-9]){re.escape(spaced_name)}(?![a-z0-9])", spaced_query)
        is not None
    )
    names_skill = False
    if (
        spaced_name
        and contains_term(spaced_query, spaced_name)
        and (not scaffolding_named or (is_lookup and exact_name))
    ):
        score += 35
        reasons.append(f"name match: {skill_name}")
        # Only an exact name asked for in a lookup, or a multi-word name, is exempt
        # from the single-term cap. A common one-word name ("test") inside an
        # unrelated long create request is a shared word, not a request for the skill.
        names_skill = exact_name and (is_lookup or len(spaced_name.split()) > 1)
    else:
        # Check if significant query words appear in skill name
        name_words = set(spaced_name.split())
        name_overlap = query_words & name_words
        if name_overlap and any(len(w) >= MIN_PARTIAL_NAME_LENGTH for w in name_overlap):
            score += 20
            reasons.append(f"partial name: {', '.join(name_overlap)}")

    # Step 5: Trigger match (works for any skill's triggers), whole words only,
    # hyphens read as spaces on both sides like the name match in step 4. A
    # trigger made only of scaffolding words is skipped for the same reason,
    # except in a name lookup.
    for trigger in skill_triggers:
        spaced_trigger = re.sub(r"[-_\s]+", " ", trigger).strip()
        if (
            spaced_trigger
            and (is_lookup or not is_scaffolding_phrase(spaced_trigger))
            and contains_term(spaced_query, spaced_trigger)
        ):
            score += 25
            reasons.append(f"trigger: {trigger}")
            break

    # Step 6: General keyword overlap
    keyword_overlap = query_words & skill_keywords
    significant_overlap = [w for w in keyword_overlap if len(w) > 3]
    if significant_overlap:
        kw_score = min(20, len(significant_overlap) * 6)
        score += kw_score
        if "keyword:" not in str(reasons):  # Avoid duplicate
            reasons.append(f"keywords: {', '.join(significant_overlap[:3])}")

    # Step 7: Description word overlap (fallback)
    desc_words = set(skill_description.split())
    desc_overlap = query_words & desc_words
    significant_desc = [w for w in desc_overlap if len(w) > 4]
    if len(significant_desc) >= 2 and "description:" not in str(reasons):
        score += 8
        reasons.append("description overlap")

    # Step 8: Coverage. Discount the score by the share of query terms the skill
    # explains. The discount is half-strength (down to x0.5) so natural phrasing
    # with a few context words ("fix the failing pytest tests in my repo") still
    # reaches the routing thresholds. A request of three or more content terms
    # that rests on a single explained term is capped below the 50 point
    # CREATE_NEW boundary: one shared word is not a match, whatever the score was
    # before the context boosts. A name lookup that names the skill exactly, or a
    # multi-word skill name in the query, is exempt.
    synonym_terms = domain_synonym_terms(query_domains, skill_domains)
    explained = count_explained_terms(content_tokens, skill, synonym_terms)
    coverage = calculate_coverage(content_tokens, skill, synonym_terms)
    if score and coverage < 1.0:
        score = round(score * (COVERAGE_FLOOR + (1 - COVERAGE_FLOOR) * coverage))
        reasons.append(f"coverage: {coverage:.0%} of query terms")
    ceiling: int | None = None
    if not names_skill and explained <= 1 and len(content_tokens) >= SINGLE_TERM_MIN_QUERY_TERMS:
        ceiling = SINGLE_TERM_SCORE_CAP

    # A zero score carries no evidence, so do not report reasons for it.
    if score <= 0:
        return 0, [], None

    return min(100, score), reasons, ceiling


def find_matching_skills(
    query: str,
    skills: list[dict[str, Any]],
    limit: int = 5,
    signals: dict[str, Any] | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """
    Find skills that match the query, sorted by score.

    Uses UNIVERSAL domain-based matching - no hardcoded skill names.
    """
    matches = []
    signals = signals or {}

    # Detect query domains for context boosting
    query_domains = detect_query_domains(query)
    query_domain_names = [d[0] for d in query_domains]

    for skill in skills:
        score, reasons, ceiling = score_skill(query, skill, category)

        # Apply context-based boosting using DOMAINS (not skill names)
        skill_domains = [d.lower() for d in skill.get("domains", [])]

        # Error context + debugging domain boost
        if signals.get("has_error") and "debugging" in skill_domains:
            score += 25
            reasons.append("error context boost")

        # Code context + code quality domain boost
        if signals.get("has_code") and "code_quality" in skill_domains:
            score += 15
            reasons.append("code context boost")

        # URL context boost for code-related domains
        if signals.get("has_url"):
            if any(d in skill_domains for d in ["code_quality", "api", "documentation"]):
                score += 10
                reasons.append("URL context boost")

        # Boost skills whose domains align with detected query domains
        matching_domains = set(skill_domains) & set(query_domain_names)
        if matching_domains and score > 0:
            # Additional boost for strong domain alignment
            score += min(15, len(matching_domains) * 5)

        score = apply_ceiling(score, ceiling, reasons)

        if score > 0:
            matches.append(
                {
                    "name": skill.get("name"),
                    "score": min(100, score),
                    "reasons": reasons,
                    "source": skill.get("source"),
                    "description": skill.get("description", "")[:100],
                    "domains": skill.get("domains", []),
                }
            )

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches[:limit]


# ===========================================================================
# TRIAGE DECISION
# ===========================================================================


def make_triage_decision(
    category: str,
    signals: dict[str, Any],
    matches: list[dict[str, Any]],
    query: str,
    indexed_name_words: frozenset[str] = frozenset(),
) -> tuple[str, dict[str, Any]]:
    """
    Make the final triage decision based on input analysis and skill matches.

    indexed_name_words is every word in every indexed skill name. Unclear input
    that uses a short word from that set ("adr" in adr-generator) names a skill
    the matcher cannot credit, because partial-name credit needs a word of
    MIN_PARTIAL_NAME_LENGTH letters. That is a recall gap, so the decision asks
    instead of recommending a new skill.

    Returns:
        Tuple of (action, details_dict)
    """
    top_match = matches[0] if matches else None
    top_score = top_match["score"] if top_match else 0

    # Multi-domain detection
    if len(matches) >= 3:
        all_domains = set()
        for m in matches[:3]:
            all_domains.update(m.get("domains", []))
        multi_domain = len(all_domains) >= 3
    else:
        multi_domain = False

    details = {
        "category": category,
        "top_match": top_match,
        "top_score": top_score,
        "match_count": len(matches),
        "multi_domain": multi_domain,
    }

    # Decision tree based on category and match quality

    # Explicit create request
    if category == InputCategory.EXPLICIT_CREATE:
        if top_score >= 80:
            # High match - existing skill might already do this
            return Action.CLARIFY, {
                **details,
                "reason": f"Existing skill '{top_match['name']}' ({top_score}%) may already handle this. Create anyway or use existing?",
                "suggested_action": "Ask user to clarify if they want to create despite existing skill",
            }
        elif top_score >= 50:
            # Moderate match - could improve existing
            return Action.CLARIFY, {
                **details,
                "reason": f"Existing skill '{top_match['name']}' ({top_score}%) is similar. Create new or improve existing?",
                "suggested_action": "Ask if user wants new skill or to enhance existing",
            }
        else:
            # Low/no match - proceed with creation
            return Action.CREATE_NEW, {
                **details,
                "reason": "No strong existing match found. Proceeding with skill creation.",
                "purpose": signals.get("extracted_purpose"),
            }

    # Explicit improve request
    if category == InputCategory.EXPLICIT_IMPROVE:
        skill_name = signals.get("mentioned_skill_name")
        if skill_name:
            # Find the mentioned skill
            for m in matches:
                if skill_name.lower() in m["name"].lower():
                    return Action.IMPROVE_EXISTING, {
                        **details,
                        "reason": f"Improving existing skill: {m['name']}",
                        "target_skill": m["name"],
                    }
        # Couldn't find mentioned skill
        return Action.CLARIFY, {
            **details,
            "reason": "Could not identify which skill to improve",
            "suggested_action": "Ask user to specify skill name",
        }

    # Skill question - just recommend
    if category == InputCategory.SKILL_QUESTION:
        if top_score >= 60:
            return Action.USE_EXISTING, {
                **details,
                "reason": f"Recommending existing skill: {top_match['name']} ({top_score}%)",
                "recommended_skills": [m["name"] for m in matches[:3]],
            }
        else:
            return Action.CREATE_NEW, {
                **details,
                "reason": "No good existing skill matches. Consider creating one.",
            }

    # Error messages - prefer skills with debugging domain (UNIVERSAL, no hardcoded names)
    if category == InputCategory.ERROR_MESSAGE:
        # Find skills with debugging domain
        debugging_skills = [
            m for m in matches if "debugging" in [d.lower() for d in m.get("domains", [])]
        ]
        best_debug_skill = debugging_skills[0] if debugging_skills else None

        if best_debug_skill and best_debug_skill["score"] >= 50:
            return Action.USE_EXISTING, {
                **details,
                "reason": f"Error detected - recommending: {best_debug_skill['name']} ({best_debug_skill['score']}%)",
                "recommended_skills": [best_debug_skill["name"]],
            }
        elif top_score >= 50:
            return Action.USE_EXISTING, {
                **details,
                "reason": f"Error handling skill: {top_match['name']} ({top_score}%)",
                "recommended_skills": [m["name"] for m in matches[:3]],
            }
        else:
            return Action.CREATE_NEW, {
                **details,
                "reason": "No error handling skill found. Consider creating one.",
            }

    # Code, URL, or task request - route based on match quality
    if category in [
        InputCategory.CODE_SNIPPET,
        InputCategory.URL_CONTENT,
        InputCategory.TASK_REQUEST,
    ]:
        if multi_domain and top_score >= 50:
            return Action.COMPOSE, {
                **details,
                "reason": "Multiple domains detected. Suggest skill composition.",
                "recommended_chain": [m["name"] for m in matches[:3]],
            }
        elif top_score >= 80:
            return Action.USE_EXISTING, {
                **details,
                "reason": f"Strong match: {top_match['name']} ({top_score}%)",
                "recommended_skills": [m["name"] for m in matches[:3]],
            }
        elif top_score >= 50:
            return Action.IMPROVE_EXISTING, {
                **details,
                "reason": f"Partial match: {top_match['name']} ({top_score}%) could be enhanced for this use case",
                "target_skill": top_match["name"],
            }
        else:
            return Action.CREATE_NEW, {
                **details,
                "reason": "No good existing skill handles this. Consider creating one.",
            }

    # General/unclear input
    if top_score >= 70:
        return Action.USE_EXISTING, {
            **details,
            "reason": f"Best match: {top_match['name']} ({top_score}%)",
            "recommended_skills": [m["name"] for m in matches[:3]],
        }
    elif (
        len(tokenize_for_scoring(query)) >= SINGLE_TERM_MIN_QUERY_TERMS
        and top_score < 50
        and not any(
            len(t) < MIN_PARTIAL_NAME_LENGTH and t in indexed_name_words
            for t in tokenize_for_scoring(query)
        )
    ):
        # A described topic with no strong match is a topic no skill covers,
        # unless a short query word names an indexed skill (a recall gap).
        return Action.CREATE_NEW, {
            **details,
            "reason": "No good existing skill handles this topic. Consider creating one.",
        }
    elif top_score >= 40:
        return Action.CLARIFY, {
            **details,
            "reason": "Unclear intent. Partial matches found.",
            "suggested_action": "Ask user to clarify what they need",
        }
    else:
        return Action.CLARIFY, {
            **details,
            "reason": "Unclear intent and no good skill matches",
            "suggested_action": "Ask user to elaborate on their goal",
        }


# ===========================================================================
# MAIN TRIAGE FUNCTION
# ===========================================================================


def triage_request(query: str) -> Result:
    """
    Analyze any user input and determine the best skill-related action.

    Returns:
        Result with action recommendation and supporting data.
    """
    # Step 1: Classify input
    category, signals = classify_input(query)

    # Step 2: Load skill index
    index = load_skill_index()
    if not index:
        return Result(
            success=False,
            message="Skill index not found. Run discover_skills.py first.",
            errors=["Index file missing: ~/.cache/skillrecommender/skill_index.json"],
        )

    skills = index.get("skills", [])

    # Step 3: Find matching skills (pass signals for context-aware boosting)
    matches = find_matching_skills(query, skills, signals=signals, category=category)

    # Step 4: Make decision
    indexed_name_words = frozenset(
        word
        for skill in skills
        for word in _TOKEN_PATTERN.findall(str(skill.get("name", "")).lower())
    )
    action, details = make_triage_decision(category, signals, matches, query, indexed_name_words)

    # Build response
    return Result(
        success=True,
        message=f"Triage complete: {action}",
        data={
            "action": action,
            "details": details,
            "input_category": category,
            "signals": signals,
            "top_matches": matches[:5],
            "total_skills_scanned": len(skills),
        },
    )


# ===========================================================================
# CLI
# ===========================================================================


def format_output(result: Result) -> str:
    """Format result for human-readable output."""
    lines = []
    data = result.data

    action = data.get("action", "UNKNOWN")
    details = data.get("details", {})

    # Header
    lines.append(f"\n{'=' * 60}")
    lines.append(f"SKILL TRIAGE RESULT: {action}")
    lines.append(f"{'=' * 60}")

    # Category
    lines.append(f"\nInput Category: {data.get('input_category', 'unknown')}")

    # Reason
    if "reason" in details:
        lines.append(f"Reason: {details['reason']}")

    # Top matches
    matches = data.get("top_matches", [])
    if matches:
        lines.append("\nTop Skill Matches:")
        for i, m in enumerate(matches[:3], 1):
            lines.append(f"  {i}. {m['name']} ({m['score']}%)")
            lines.append(f"     {m.get('description', '')[:60]}...")
            if m.get("reasons"):
                lines.append(f"     Matched: {', '.join(m['reasons'][:2])}")

    # Action-specific guidance
    lines.append(f"\n{'─' * 60}")
    lines.append("RECOMMENDED NEXT STEP:")

    if action == Action.USE_EXISTING:
        skills = details.get("recommended_skills", [])
        lines.append(f"  Invoke existing skill: {skills[0] if skills else 'unknown'}")
        lines.append(f"  Example: use skill '{skills[0] if skills else 'skill-name'}' in your host")

    elif action == Action.IMPROVE_EXISTING:
        target = details.get("target_skill", "unknown")
        lines.append(f"  Improve skill: {target}")
        lines.append(f"  Command: SkillForge: improve {target}")

    elif action == Action.CREATE_NEW:
        purpose = details.get("purpose", "the requested functionality")
        lines.append(f"  Create new skill for: {purpose}")
        lines.append(f"  Command: SkillForge: create a skill for {purpose}")

    elif action == Action.COMPOSE:
        chain = details.get("recommended_chain", [])
        lines.append(f"  Compose skill chain: {' → '.join(chain)}")
        lines.append("  Run the chain in order and keep the scope minimal")

    elif action == Action.CLARIFY:
        suggestion = details.get("suggested_action", "Clarify your intent")
        lines.append(f"  {suggestion}")

    lines.append(f"{'─' * 60}\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze input and recommend skill action",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "create a skill for database migrations"
  %(prog)s "help me debug this error"
  %(prog)s "do I have a skill for testing?" --json
  %(prog)s "TypeError: Cannot read property 'map' of undefined"
        """,
    )

    parser.add_argument("query", type=str, help="The user input to analyze")

    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    # Run triage
    result = triage_request(args.query)

    # Output
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            print(format_output(result))
        else:
            print(f"Error: {result.message}", file=sys.stderr)
            for error in result.errors:
                print(f"  {error}", file=sys.stderr)

    # Exit code
    if not result.success:
        sys.exit(2 if "index" in result.message.lower() else 1)
    sys.exit(0)


if __name__ == "__main__":
    main()
