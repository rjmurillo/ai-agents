"""Semantic guard for PreToolUse hook - knowledge boundary detection."""

from dataclasses import dataclass

from semantic_hooks.core import HookContext, HookEvent, HookResult, SemanticZone
from semantic_hooks.embedder import Embedder, compute_trajectory_embedding, semantic_tension
from semantic_hooks.memory import SemanticMemory


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
        """Classify semantic zone from ΔS value."""
        if delta_s < self.config.safe_threshold:
            return SemanticZone.SAFE
        elif delta_s < self.config.transitional_threshold:
            return SemanticZone.TRANSITIONAL
        elif delta_s < self.config.risk_threshold:
            return SemanticZone.RISK
        return SemanticZone.DANGER

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
    memory = SemanticMemory(embedder=embedder)

    return SemanticGuard(memory=memory, embedder=embedder, config=guard_config)
