"""Semantic recorder for PostToolUse hook - node recording."""

from datetime import datetime

from semantic_hooks.core import (
    HookContext,
    HookEvent,
    HookResult,
    ReasoningDirection,
    SemanticNode,
)
from semantic_hooks.embedder import Embedder
from semantic_hooks.memory import SemanticMemory


class SemanticRecorder:
    """PostToolUse recorder that creates semantic nodes after tool execution.

    Records reasoning steps with semantic metadata for trajectory tracking.
    """

    def __init__(
        self,
        memory: SemanticMemory,
        embedder: Embedder,
    ):
        """Initialize recorder.

        Args:
            memory: Semantic memory for node storage
            embedder: Embedder for generating node embeddings
        """
        self.memory = memory
        self.embedder = embedder
        self._current_parent_id: str | None = None

    def record(
        self,
        context: HookContext,
        delta_s: float | None = None,
        force: bool = False,
    ) -> HookResult:
        """Record semantic node after tool execution.

        Args:
            context: Hook context with tool result
            delta_s: Pre-computed ΔS value (optional)
            force: Record even for low-significance events

        Returns:
            HookResult with recorded node
        """
        if context.event != HookEvent.POST_TOOL_USE:
            return HookResult(allow=True)

        # Determine reasoning direction from exit code
        direction = self._infer_direction(context)

        # Extract topic and insight
        topic = self._extract_topic(context)
        insight = self._extract_insight(context)

        # Skip trivial nodes unless forced
        if not force and self._is_trivial(context, topic, insight):
            return HookResult(allow=True, record_node=False)

        # Create node
        node = SemanticNode(
            topic=topic,
            delta_s=delta_s or 0.0,
            lambda_observe=direction,
            module_used=context.tool_name or "unknown",
            insight=insight,
            timestamp=datetime.now(),
            session_id=context.session_id,
            parent_id=self._current_parent_id,
            metadata={
                "exit_code": context.exit_code,
                "working_directory": context.working_directory,
            },
        )

        # Store node
        self.memory.add_node(node)

        # Update parent for tree structure
        if direction == ReasoningDirection.CONVERGENT:
            self._current_parent_id = node.id

        return HookResult(
            allow=True,
            record_node=True,
            node=node,
            message=f"Recorded: {topic} (ΔS={node.delta_s:.3f}, {direction.value})",
        )

    def _infer_direction(self, context: HookContext) -> ReasoningDirection:
        """Infer reasoning direction from context."""
        if context.exit_code is None:
            return ReasoningDirection.CONVERGENT

        if context.exit_code == 0:
            return ReasoningDirection.CONVERGENT
        elif context.exit_code == 1:
            return ReasoningDirection.DIVERGENT
        else:
            return ReasoningDirection.RECURSIVE

    def _extract_topic(self, context: HookContext) -> str:
        """Extract topic from tool context."""
        tool = context.tool_name or "unknown"

        if context.tool_input:
            # Try to extract meaningful identifier
            input_data = context.tool_input
            if isinstance(input_data, dict):
                # Common patterns
                if "file_path" in input_data:
                    return f"{tool}: {input_data['file_path']}"
                if "path" in input_data:
                    return f"{tool}: {input_data['path']}"
                if "command" in input_data:
                    cmd = str(input_data["command"])[:50]
                    return f"{tool}: {cmd}"
                if "query" in input_data:
                    query = str(input_data["query"])[:50]
                    return f"{tool}: {query}"

        return tool

    def _extract_insight(self, context: HookContext) -> str:
        """Extract compressed insight from tool result."""
        if not context.tool_result:
            return f"Executed {context.tool_name}"

        result = context.tool_result

        # Truncate long results
        if len(result) > 200:
            # Try to extract key info
            lines = result.split("\n")
            if len(lines) > 5:
                # First and last few lines often most informative
                result = "\n".join(lines[:2] + ["..."] + lines[-2:])
                # Cap the multi-line result to avoid exceeding reasonable length
                if len(result) > 200:
                    result = result[:200] + "..."
            else:
                result = result[:200] + "..."

        return result

    def _is_trivial(self, context: HookContext, topic: str, insight: str) -> bool:
        """Check if node is too trivial to record."""
        # Skip very short, non-informative results
        if len(insight) < 10 and context.exit_code == 0:
            return True

        # Skip common low-value tools
        trivial_tools = {"echo", "pwd", "whoami"}
        return bool(
            context.tool_name and context.tool_name.lower() in trivial_tools
        )

    def start_session(self, session_id: str) -> None:
        """Initialize session tracking.

        Args:
            session_id: New session identifier
        """
        self._current_parent_id = None

    def end_session(self, session_id: str) -> dict:
        """Finalize session and return summary.

        Args:
            session_id: Session to finalize

        Returns:
            Session summary with node count and zone distribution
        """
        tree = self.memory.export_tree(session_id=session_id)
        self._current_parent_id = None
        return tree


def create_recorder_from_config(config_path: str | None = None) -> SemanticRecorder:
    """Factory function to create recorder from config file.

    Args:
        config_path: Path to YAML config

    Returns:
        Configured SemanticRecorder instance
    """
    from semantic_hooks.memory import load_config_and_create_memory

    _, embedder, memory = load_config_and_create_memory(config_path)
    return SemanticRecorder(memory=memory, embedder=embedder)
