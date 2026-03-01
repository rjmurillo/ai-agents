"""Core data structures for semantic tension tracking."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class HookEvent(Enum):
    """Claude Code hook events."""

    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_RESPONSE = "PostResponse"
    USER_PROMPT = "UserPromptSubmit"
    PRE_COMPACT = "PreCompact"
    NOTIFICATION = "Notification"
    STOP = "Stop"
    SUBAGENT_START = "SubagentStart"
    PERMISSION_REQUEST = "PermissionRequest"


class ReasoningDirection(Enum):
    """Direction of reasoning flow (λ_observe)."""

    CONVERGENT = "->"  # Moving toward conclusion
    DIVERGENT = "<-"  # Exploring alternatives / backtracking
    RECURSIVE = "<>"  # Self-referential / iterating


class SemanticZone(Enum):
    """Knowledge boundary zones based on ΔS."""

    SAFE = "safe"  # ΔS < 0.4 - well-known territory
    TRANSITIONAL = "transitional"  # 0.4 <= ΔS < 0.6 - moving between concepts
    RISK = "risk"  # 0.6 <= ΔS < 0.85 - approaching unknown territory
    DANGER = "danger"  # ΔS >= 0.85 - high hallucination risk


@dataclass
class ZoneThresholds:
    """Thresholds for semantic zone classification.

    Single source of truth for zone boundaries used across the codebase.
    """

    safe: float = 0.4  # ΔS < safe → SAFE zone
    transitional: float = 0.6  # safe <= ΔS < transitional → TRANSITIONAL
    risk: float = 0.85  # transitional <= ΔS < risk → RISK; ΔS >= risk → DANGER


# Default thresholds used when no config is provided
DEFAULT_ZONE_THRESHOLDS = ZoneThresholds()


def classify_zone(delta_s: float, thresholds: ZoneThresholds | None = None) -> SemanticZone:
    """Classify semantic zone from ΔS value.

    Args:
        delta_s: Semantic tension value
        thresholds: Optional custom thresholds (uses defaults if None)

    Returns:
        SemanticZone classification
    """
    if thresholds is None:
        thresholds = DEFAULT_ZONE_THRESHOLDS

    if delta_s < thresholds.safe:
        return SemanticZone.SAFE
    elif delta_s < thresholds.transitional:
        return SemanticZone.TRANSITIONAL
    elif delta_s < thresholds.risk:
        return SemanticZone.RISK
    return SemanticZone.DANGER


@dataclass
class SemanticNode:
    """A node in the semantic reasoning tree.

    Captures a single reasoning step with its semantic context.
    """

    topic: str
    delta_s: float
    lambda_observe: ReasoningDirection
    module_used: str
    insight: str
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: str = ""
    project_id: str = ""  # For future project isolation
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    embedding: list[float] | None = None
    parent_id: str | None = None  # For tree structure
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def zone(self) -> SemanticZone:
        """Classify the semantic zone based on ΔS using default thresholds."""
        return classify_zone(self.delta_s)

    def zone_with_thresholds(self, thresholds: ZoneThresholds) -> SemanticZone:
        """Classify the semantic zone based on ΔS with custom thresholds.

        Args:
            thresholds: Custom zone thresholds

        Returns:
            SemanticZone classification
        """
        return classify_zone(self.delta_s, thresholds)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "topic": self.topic,
            "delta_s": self.delta_s,
            "lambda_observe": self.lambda_observe.value,
            "module_used": self.module_used,
            "insight": self.insight,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "project_id": self.project_id,
            "zone": self.zone.value,
            "parent_id": self.parent_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticNode":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            topic=data["topic"],
            delta_s=data["delta_s"],
            lambda_observe=ReasoningDirection(data["lambda_observe"]),
            module_used=data["module_used"],
            insight=data["insight"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            session_id=data.get("session_id", ""),
            project_id=data.get("project_id", ""),
            parent_id=data.get("parent_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class HookContext:
    """Context passed to hook handlers."""

    event: HookEvent
    session_id: str = ""
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_result: str | None = None
    exit_code: int | None = None
    prompt: str | None = None
    working_directory: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_stdin_json(cls, data: dict[str, Any], event: HookEvent) -> "HookContext":
        """Create context from Claude's stdin JSON."""
        return cls(
            event=event,
            session_id=data.get("session_id", ""),
            tool_name=data.get("tool_name"),
            tool_input=data.get("tool_input"),
            tool_result=data.get("tool_result"),
            exit_code=data.get("exit_code"),
            prompt=data.get("prompt"),
            working_directory=data.get("cwd"),
        )


@dataclass
class HookResult:
    """Result returned from hook handlers."""

    allow: bool = True
    block: bool = False
    message: str | None = None
    additional_context: str | None = None
    record_node: bool = False
    node: SemanticNode | None = None

    def to_stdout_json(self) -> dict[str, Any]:
        """Serialize for Claude's stdout JSON response."""
        result: dict[str, Any] = {}
        if self.message:
            result["message"] = self.message
        if self.additional_context:
            result["additionalContext"] = self.additional_context
        return result

    @property
    def exit_code(self) -> int:
        """Get exit code for Claude hooks (0=allow, 1=error, 2=block)."""
        if self.block:
            return 2
        if not self.allow:
            return 1
        return 0
