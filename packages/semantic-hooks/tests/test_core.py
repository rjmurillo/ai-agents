"""Tests for core data structures."""


from semantic_hooks.core import (
    HookContext,
    HookEvent,
    HookResult,
    ReasoningDirection,
    SemanticNode,
    SemanticZone,
)


class TestSemanticNode:
    """Tests for SemanticNode dataclass."""

    def test_zone_classification_safe(self):
        node = SemanticNode(
            topic="test",
            delta_s=0.3,
            lambda_observe=ReasoningDirection.CONVERGENT,
            module_used="test",
            insight="test insight",
        )
        assert node.zone == SemanticZone.SAFE

    def test_zone_classification_transitional(self):
        node = SemanticNode(
            topic="test",
            delta_s=0.5,
            lambda_observe=ReasoningDirection.CONVERGENT,
            module_used="test",
            insight="test insight",
        )
        assert node.zone == SemanticZone.TRANSITIONAL

    def test_zone_classification_risk(self):
        node = SemanticNode(
            topic="test",
            delta_s=0.7,
            lambda_observe=ReasoningDirection.CONVERGENT,
            module_used="test",
            insight="test insight",
        )
        assert node.zone == SemanticZone.RISK

    def test_zone_classification_danger(self):
        node = SemanticNode(
            topic="test",
            delta_s=0.9,
            lambda_observe=ReasoningDirection.CONVERGENT,
            module_used="test",
            insight="test insight",
        )
        assert node.zone == SemanticZone.DANGER

    def test_to_dict_roundtrip(self):
        node = SemanticNode(
            topic="test topic",
            delta_s=0.5,
            lambda_observe=ReasoningDirection.DIVERGENT,
            module_used="bash",
            insight="did something",
            session_id="sess123",
        )
        data = node.to_dict()
        restored = SemanticNode.from_dict(data)

        assert restored.topic == node.topic
        assert restored.delta_s == node.delta_s
        assert restored.lambda_observe == node.lambda_observe
        assert restored.module_used == node.module_used
        assert restored.insight == node.insight


class TestHookResult:
    """Tests for HookResult."""

    def test_exit_code_allow(self):
        result = HookResult(allow=True, block=False)
        assert result.exit_code == 0

    def test_exit_code_block(self):
        result = HookResult(allow=False, block=True)
        assert result.exit_code == 2


    def test_exit_code_disallow_without_block(self):
        """allow=False, block=False should return exit code 1 (error)."""
        result = HookResult(allow=False, block=False)
        assert result.exit_code == 1

    def test_to_stdout_json_with_context(self):
        result = HookResult(
            allow=True,
            message="test message",
            additional_context="extra context",
        )
        output = result.to_stdout_json()
        assert output["message"] == "test message"
        assert output["additionalContext"] == "extra context"

    def test_to_stdout_json_empty(self):
        result = HookResult(allow=True)
        output = result.to_stdout_json()
        assert output == {}


class TestHookContext:
    """Tests for HookContext."""

    def test_from_stdin_json(self):
        data = {
            "session_id": "sess123",
            "tool_name": "bash",
            "tool_input": {"command": "ls"},
            "cwd": "/home/user",
        }
        context = HookContext.from_stdin_json(data, HookEvent.PRE_TOOL_USE)

        assert context.event == HookEvent.PRE_TOOL_USE
        assert context.session_id == "sess123"
        assert context.tool_name == "bash"
        assert context.tool_input == {"command": "ls"}
        assert context.working_directory == "/home/user"
