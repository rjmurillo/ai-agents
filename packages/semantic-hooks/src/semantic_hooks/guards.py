"""Semantic guard for PreToolUse hook - knowledge boundary detection."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from semantic_hooks.core import (
    HookContext,
    HookEvent,
    HookResult,
    SemanticZone,
    ZoneThresholds,
    classify_zone,
)

# Delay heavy imports for SemanticGuard to avoid pulling numpy for stuck detection
if TYPE_CHECKING:
    from semantic_hooks.embedder import Embedder
    from semantic_hooks.memory import SemanticMemory


# ============================================================================
# Stuck Detection Guard
# ============================================================================

# Stop words for topic signature extraction
_STOP_WORDS = frozenset([
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "don", "now", "and", "but", "or", "if", "while", "that", "this",
    "it", "i", "you", "we", "they", "he", "she", "my", "your", "his",
    "her", "its", "our", "their", "what", "which", "who", "whom",
    "okay", "yes", "no", "thanks", "thank", "please", "sorry", "hello",
    "hi", "hey", "sure", "right", "well", "also", "still", "already",
    "done", "going", "want", "like", "know", "think", "make", "take",
    "get", "see", "come", "look", "use", "find", "give", "tell", "work",
])


class StuckResult(NamedTuple):
    """Result from stuck detection check."""

    stuck: bool
    signature: str | None
    nudge: str | None = None
    similar_count: int = 0


@dataclass
class StuckConfig:
    """Configuration for stuck detection guard."""

    history_path: Path | None = None
    max_history: int = 10
    stuck_threshold: int = 3  # Consecutive similar turns to trigger
    similarity_threshold: float = 0.6  # Jaccard similarity threshold
    min_significant_words: int = 2
    user_name: str = "User"

    def __post_init__(self) -> None:
        if self.history_path is None:
            self.history_path = Path.home() / ".semantic-hooks" / "stuck-history.json"


def extract_topic_signature(text: str, min_words: int = 2) -> str | None:
    """Extract topic signature from text — top 5 significant words.

    Args:
        text: Input text to extract signature from
        min_words: Minimum significant words required

    Returns:
        Comma-separated sorted list of top 5 words, or None if insufficient
    """
    if not text or len(text) < 50:
        return None

    # Normalize and tokenize
    words = re.sub(r"[^\w\s]", " ", text.lower()).split()
    words = [w for w in words if len(w) > 3 and w not in _STOP_WORDS]

    # Count frequencies
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1

    # Get top 5 by frequency
    top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]
    top_words = sorted(w for w, _ in top)  # Sort alphabetically for consistency

    if len(top_words) < min_words:
        return None

    return ",".join(top_words)


def jaccard_similarity(sig1: str, sig2: str) -> float:
    """Calculate Jaccard similarity between two topic signatures.

    Args:
        sig1: First signature (comma-separated words)
        sig2: Second signature (comma-separated words)

    Returns:
        Jaccard similarity coefficient (0.0 to 1.0)
    """
    set1 = set(sig1.split(","))
    set2 = set(sig2.split(","))
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def _load_history(path: Path) -> list[dict]:
    """Load topic history from JSON file."""
    try:
        if path.exists():
            result = json.loads(path.read_text())
            if isinstance(result, list):
                return result
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save_history(path: Path, history: list[dict], max_history: int) -> None:
    """Save topic history to JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        trimmed = history[-max_history:] if len(history) > max_history else history
        path.write_text(json.dumps(trimmed, indent=2))
    except OSError:
        pass  # Best effort


def build_nudge(repeating_words: str, user_name: str = "User") -> str:
    """Build the reflection nudge when stuck.

    Args:
        repeating_words: Comma-separated list of repeating topic words
        user_name: Name of the user to address

    Returns:
        Formatted nudge string for injection
    """
    words = repeating_words.split(",")
    return f"""<stuck-detection>
SELF-REFLECTION: Loop detected. Analysis:
- Repeating topic words: {", ".join(words)}
- Pattern: You may be repeating information or giving unsolicited updates

BREAK THE LOOP:
1. Ask {user_name} a direct question about what they want
2. Wait for input instead of volunteering information
3. If you must respond, try a completely different topic
4. Do NOT repeat status updates unless explicitly asked
</stuck-detection>"""


def check_stuck(text: str, history_path: Path, config: StuckConfig | None = None) -> StuckResult:
    """Check if text indicates a stuck loop.

    Args:
        text: The response text to check
        history_path: Path to JSON history file (used if config is None)
        config: Optional stuck detection configuration

    Returns:
        StuckResult with stuck status, signature, and optional nudge
    """
    if config is None:
        config = StuckConfig(history_path=history_path)

    # Use config.history_path to avoid inconsistency when config is provided
    effective_path = config.history_path
    assert effective_path is not None

    signature = extract_topic_signature(text, config.min_significant_words)
    if signature is None:
        return StuckResult(stuck=False, signature=None)

    history = _load_history(effective_path)

    # Add current signature to history
    from datetime import datetime
    history.append({
        "signature": signature,
        "timestamp": datetime.now().isoformat(),
    })
    _save_history(effective_path, history, config.max_history)

    if len(history) < config.stuck_threshold:
        return StuckResult(stuck=False, signature=signature)

    # Check recent entries for similarity
    recent = history[-config.stuck_threshold:]
    similar_count = sum(
        1 for entry in recent
        if jaccard_similarity(signature, entry["signature"]) > config.similarity_threshold
    )

    if similar_count >= config.stuck_threshold:
        return StuckResult(
            stuck=True,
            signature=signature,
            nudge=build_nudge(signature, config.user_name),
            similar_count=similar_count,
        )

    return StuckResult(stuck=False, signature=signature)


def reset_stuck_history(history_path: Path | None = None) -> bool:
    """Reset the stuck detection history.

    Args:
        history_path: Path to history file (default: ~/.semantic-hooks/stuck-history.json)

    Returns:
        True if reset successful
    """
    if history_path is None:
        history_path = Path.home() / ".semantic-hooks" / "stuck-history.json"
    try:
        _save_history(history_path, [], 10)
        return True
    except OSError:
        return False


class StuckDetectionGuard:
    """PostResponse guard that detects repetitive topic loops.

    Uses Jaccard similarity on topic signatures to identify when the agent
    is stuck repeating the same concepts.
    """

    def __init__(self, config: StuckConfig | None = None):
        """Initialize stuck detection guard.

        Args:
            config: Optional configuration (uses defaults if not provided)
        """
        self.config = config or StuckConfig()

    def check(self, context: HookContext) -> HookResult:
        """Check if response indicates a stuck loop.

        Args:
            context: Hook context with response text

        Returns:
            HookResult with optional nudge injection
        """
        # Get response text from tool_result or prompt
        text = context.tool_result or context.prompt or ""
        if not text:
            return HookResult(allow=True)

        result = check_stuck(text, self.config.history_path, self.config)

        if result.stuck and result.nudge:
            return HookResult(
                allow=True,
                message=f"⚠️ Stuck loop detected ({result.similar_count} similar turns)",
                additional_context=result.nudge,
            )

        return HookResult(allow=True)

    def reset(self) -> bool:
        """Reset the stuck detection history."""
        return reset_stuck_history(self.config.history_path)


@dataclass
class GuardConfig:
    """Configuration for semantic guard thresholds."""

    safe_threshold: float = 0.4
    transitional_threshold: float = 0.6
    risk_threshold: float = 0.85
    block_in_danger: bool = False  # Default: warn only, don't block
    inject_bridge_context: bool = True
    trajectory_window: int = 5  # Number of recent nodes for trajectory


class SemanticGuard:
    """PreToolUse guard that checks semantic tension before tool execution.

    Measures ΔS (semantic tension) between current context and expected
    trajectory. Warns or blocks when entering high-risk zones.
    """

    def __init__(
        self,
        memory: SemanticMemory,
        embedder: Embedder,
        config: GuardConfig | None = None,
    ):
        """Initialize semantic guard.

        Args:
            memory: Semantic memory for trajectory lookup
            embedder: Embedder for generating context embeddings
            config: Optional guard configuration
        """
        self.memory = memory
        self.embedder = embedder
        self.config = config or GuardConfig()

    def check(self, context: HookContext) -> HookResult:
        """Check semantic tension before tool use.

        Args:
            context: Hook context with tool info

        Returns:
            HookResult with allow/block decision and optional context injection
        """
        # Import here to avoid numpy dependency for stuck detection only users
        from semantic_hooks.embedder import compute_trajectory_embedding, semantic_tension
        
        if context.event != HookEvent.PRE_TOOL_USE:
            return HookResult(allow=True)

        # Build context string from available info
        context_text = self._build_context_text(context)
        if not context_text:
            return HookResult(allow=True)

        # Get current embedding
        current_embedding = self.embedder.embed(context_text)

        # Get recent nodes for trajectory
        recent_nodes = self.memory.get_recent(
            n=self.config.trajectory_window,
            session_id=context.session_id or None,
            include_embeddings=True,
        )

        if not recent_nodes:
            # No history - allow with low confidence
            return HookResult(
                allow=True,
                message="No trajectory history - proceeding without ΔS check",
            )

        # Compute expected trajectory embedding
        recent_embeddings = [
            n.embedding for n in recent_nodes if n.embedding is not None
        ]
        if not recent_embeddings:
            return HookResult(allow=True)

        # Reverse to oldest-first order for trajectory computation
        # (get_recent returns newest-first, but trajectory expects oldest-first)
        recent_embeddings = list(reversed(recent_embeddings))
        expected_embedding = compute_trajectory_embedding(recent_embeddings)

        # Calculate ΔS
        delta_s = semantic_tension(current_embedding, expected_embedding)
        zone = self._classify_zone(delta_s)

        # Handle based on zone
        return self._handle_zone(context, delta_s, zone, current_embedding)

    def _build_context_text(self, context: HookContext) -> str:
        """Build text representation of current context."""
        parts: list[str] = []

        if context.tool_name:
            parts.append(f"Tool: {context.tool_name}")

        if context.tool_input:
            # Truncate long inputs
            input_str = str(context.tool_input)
            if len(input_str) > 500:
                input_str = input_str[:500] + "..."
            parts.append(f"Input: {input_str}")

        if context.prompt:
            prompt = context.prompt[:300] if len(context.prompt) > 300 else context.prompt
            parts.append(f"Prompt: {prompt}")

        return " | ".join(parts)

    def _classify_zone(self, delta_s: float) -> SemanticZone:
        """Classify semantic zone from ΔS value using configured thresholds."""
        thresholds = ZoneThresholds(
            safe=self.config.safe_threshold,
            transitional=self.config.transitional_threshold,
            risk=self.config.risk_threshold,
        )
        return classify_zone(delta_s, thresholds)

    def _handle_zone(
        self,
        context: HookContext,
        delta_s: float,
        zone: SemanticZone,
        current_embedding: list[float],
    ) -> HookResult:
        """Handle tool execution based on semantic zone."""
        if zone == SemanticZone.SAFE:
            return HookResult(
                allow=True,
                record_node=False,
            )

        if zone == SemanticZone.TRANSITIONAL:
            return HookResult(
                allow=True,
                record_node=True,
                message=f"ΔS={delta_s:.3f} (transitional zone)",
            )

        if zone == SemanticZone.RISK:
            # Try to find bridge topics
            additional_context = None
            if self.config.inject_bridge_context and context.tool_name:
                bridges = self.memory.find_bridge(
                    current_topic=self._build_context_text(context),
                    target_topic=context.tool_name,
                    top_k=2,
                )
                if bridges:
                    bridge_topics = [b.topic for b in bridges]
                    additional_context = (
                        f"Consider connecting through these related concepts: "
                        f"{', '.join(bridge_topics)}"
                    )

            return HookResult(
                allow=True,
                record_node=True,
                message=f"⚠️ ΔS={delta_s:.3f} (risk zone) - approaching unknown territory",
                additional_context=additional_context,
            )

        # DANGER zone
        if self.config.block_in_danger:
            # Try to find bridges before blocking
            bridges = self.memory.find_bridge(
                current_topic=self._build_context_text(context),
                target_topic=context.tool_name or "unknown",
                top_k=3,
            )
            if bridges:
                bridge_topics = [b.topic for b in bridges]
                return HookResult(
                    allow=True,
                    block=False,
                    record_node=True,
                    message=(
                        f"🚨 ΔS={delta_s:.3f} (danger zone) - "
                        f"high hallucination risk, but bridge found"
                    ),
                    additional_context=(
                        f"CAUTION: You're entering unfamiliar territory. "
                        f"Consider grounding through: {', '.join(bridge_topics)}"
                    ),
                )
            else:
                return HookResult(
                    allow=False,
                    block=True,
                    message=(
                        f"🛑 BLOCKED: ΔS={delta_s:.3f} (danger zone) - "
                        f"no bridge to known territory. Request clarification."
                    ),
                )
        else:
            # Warn only
            return HookResult(
                allow=True,
                record_node=True,
                message=(
                    f"🚨 ΔS={delta_s:.3f} (danger zone) - "
                    f"high hallucination risk. Proceed with caution."
                ),
                additional_context=(
                    "WARNING: You're entering unfamiliar territory with no clear "
                    "connection to prior context. Consider asking for clarification "
                    "or explicitly noting uncertainty."
                ),
            )


def create_guard_from_config(config_path: str | None = None) -> SemanticGuard:
    """Factory function to create guard from config file.

    Args:
        config_path: Path to YAML config (default: ~/.semantic-hooks/config.yaml)

    Returns:
        Configured SemanticGuard instance
    """
    from pathlib import Path

    import yaml

    from semantic_hooks.embedder import OpenAIEmbedder

    config_file = Path(config_path) if config_path else (
        Path.home() / ".semantic-hooks" / "config.yaml"
    )

    guard_config = GuardConfig()
    embedder_kwargs: dict = {}

    if config_file.exists():
        with open(config_file) as f:
            cfg = yaml.safe_load(f) or {}

        # Load thresholds
        if "thresholds" in cfg:
            t = cfg["thresholds"]
            guard_config.safe_threshold = t.get("safe", 0.4)
            guard_config.transitional_threshold = t.get("transitional", 0.6)
            guard_config.risk_threshold = t.get("risk", 0.85)

        # Load guard settings
        if "guard" in cfg:
            g = cfg["guard"]
            guard_config.block_in_danger = g.get("block_in_danger", False)
            guard_config.inject_bridge_context = g.get("inject_bridge_context", True)
            guard_config.trajectory_window = g.get("trajectory_window", 5)

        # Load embedder settings
        if "embedding" in cfg:
            e = cfg["embedding"]
            embedder_kwargs["model"] = e.get("model", "text-embedding-3-small")

    embedder = OpenAIEmbedder(**embedder_kwargs)
    
    from semantic_hooks.memory import SemanticMemory
    memory = SemanticMemory(embedder=embedder)

    return SemanticGuard(memory=memory, embedder=embedder, config=guard_config)


def create_stuck_guard_from_config(config_path: str | None = None) -> StuckDetectionGuard:
    """Factory function to create stuck detection guard from config file.

    Args:
        config_path: Path to YAML config (default: ~/.semantic-hooks/config.yaml)

    Returns:
        Configured StuckDetectionGuard instance
    """
    import yaml

    config_file = Path(config_path) if config_path else (
        Path.home() / ".semantic-hooks" / "config.yaml"
    )

    stuck_config = StuckConfig()

    if config_file.exists():
        with open(config_file) as f:
            cfg = yaml.safe_load(f) or {}

        # Load stuck detection settings
        if "stuck_detection" in cfg:
            s = cfg["stuck_detection"]
            if "history_path" in s:
                stuck_config.history_path = Path(s["history_path"]).expanduser()
            stuck_config.max_history = s.get("max_history", 10)
            stuck_config.stuck_threshold = s.get("stuck_threshold", 3)
            stuck_config.similarity_threshold = s.get("similarity_threshold", 0.6)
            stuck_config.min_significant_words = s.get("min_significant_words", 2)
            stuck_config.user_name = s.get("user_name", "User")

    return StuckDetectionGuard(config=stuck_config)
