#!/usr/bin/env python3
"""
Unit tests for LLM markdown parsing fix (PR #955 line 461 comment).

This test specifically covers the bug fix that prevents file corruption when
parsing LLM responses containing markdown code fences.

The bug was that the old code used string.split("```") which could fail
with certain response formats, leading to corrupted JSON and file corruption.

The fix uses regex to reliably extract JSON from markdown blocks.

Run with: python3 tests/test_llm_markdown_parsing.py
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Add .claude/hooks/Stop directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "Stop"))

from invoke_skill_learning import classify_learning_by_llm


class TestMarkdownCodeFenceParsing(unittest.TestCase):
    """
    Test the markdown code fence parsing fix at line 461-465.

    This is the critical bug fix that prevents file corruption.
    """

    @patch('invoke_skill_learning.ANTHROPIC_AVAILABLE', True)
    @patch('invoke_skill_learning.Anthropic')
    @patch('invoke_skill_learning.get_api_key')
    def test_plain_json_no_markdown(self, mock_get_key, mock_anthropic):
        """Test parsing plain JSON without markdown code fences."""
        mock_get_key.return_value = "test-key"

        # Mock LLM response with plain JSON
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"is_learning": true, "type": "correction", "confidence": 0.9, "category": "High", "extracted_learning": "Test", "reasoning": "Test"}')]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        result = classify_learning_by_llm("Assistant", "User", "skill")

        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "correction")
        self.assertEqual(result["confidence"], 0.9)

    @patch('invoke_skill_learning.ANTHROPIC_AVAILABLE', True)
    @patch('invoke_skill_learning.Anthropic')
    @patch('invoke_skill_learning.get_api_key')
    def test_markdown_with_json_label(self, mock_get_key, mock_anthropic):
        """Test parsing markdown code fence with 'json' label."""
        mock_get_key.return_value = "test-key"

        # Mock LLM response with markdown ```json
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='```json\n{"is_learning": true, "type": "preference", "confidence": 0.7, "category": "Med", "extracted_learning": "Test", "reasoning": "Test"}\n```')]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        result = classify_learning_by_llm("Assistant", "User", "skill")

        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "preference")
        self.assertEqual(result["confidence"], 0.7)

    @patch('invoke_skill_learning.ANTHROPIC_AVAILABLE', True)
    @patch('invoke_skill_learning.Anthropic')
    @patch('invoke_skill_learning.get_api_key')
    def test_markdown_without_language_label(self, mock_get_key, mock_anthropic):
        """Test parsing markdown code fence without language label (```)."""
        mock_get_key.return_value = "test-key"

        # Mock LLM response with markdown ``` (no language)
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='```\n{"is_learning": true, "type": "success", "confidence": 0.65, "category": "Med", "extracted_learning": "Test", "reasoning": "Test"}\n```')]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        result = classify_learning_by_llm("Assistant", "User", "skill")

        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "success")
        self.assertEqual(result["confidence"], 0.65)

    @patch('invoke_skill_learning.ANTHROPIC_AVAILABLE', True)
    @patch('invoke_skill_learning.Anthropic')
    @patch('invoke_skill_learning.get_api_key')
    def test_markdown_with_whitespace(self, mock_get_key, mock_anthropic):
        """Test parsing markdown with extra whitespace."""
        mock_get_key.return_value = "test-key"

        # Mock LLM response with whitespace around JSON
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='```json\n\n  {"is_learning": true, "type": "edge_case", "confidence": 0.6, "category": "Med", "extracted_learning": "Test", "reasoning": "Test"}  \n\n```')]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        result = classify_learning_by_llm("Assistant", "User", "skill")

        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "edge_case")

    @patch('invoke_skill_learning.ANTHROPIC_AVAILABLE', True)
    @patch('invoke_skill_learning.Anthropic')
    @patch('invoke_skill_learning.get_api_key')
    def test_markdown_with_text_before_fence(self, mock_get_key, mock_anthropic):
        """Test parsing when there's text before the code fence."""
        mock_get_key.return_value = "test-key"

        # Mock LLM response with explanatory text before JSON
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='Here is the analysis:\n```json\n{"is_learning": true, "type": "documentation", "confidence": 0.65, "category": "Med", "extracted_learning": "Test", "reasoning": "Test"}\n```')]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        result = classify_learning_by_llm("Assistant", "User", "skill")

        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "documentation")

    @patch('invoke_skill_learning.ANTHROPIC_AVAILABLE', True)
    @patch('invoke_skill_learning.Anthropic')
    @patch('invoke_skill_learning.get_api_key')
    def test_markdown_with_text_after_fence(self, mock_get_key, mock_anthropic):
        """Test parsing when there's text after the code fence."""
        mock_get_key.return_value = "test-key"

        # Mock LLM response with explanatory text after JSON
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='```json\n{"is_learning": true, "type": "question", "confidence": 0.55, "category": "Med", "extracted_learning": "Test", "reasoning": "Test"}\n```\nThis indicates a learning signal.')]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        result = classify_learning_by_llm("Assistant", "User", "skill")

        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "question")

    @patch('invoke_skill_learning.ANTHROPIC_AVAILABLE', True)
    @patch('invoke_skill_learning.Anthropic')
    @patch('invoke_skill_learning.get_api_key')
    def test_multiline_json_in_markdown(self, mock_get_key, mock_anthropic):
        """Test parsing multiline JSON inside markdown."""
        mock_get_key.return_value = "test-key"

        # Mock LLM response with multiline JSON
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='''```json
{
  "is_learning": true,
  "type": "correction",
  "confidence": 0.85,
  "category": "High",
  "extracted_learning": "Multi-line test",
  "reasoning": "Testing multiline"
}
```''')]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        result = classify_learning_by_llm("Assistant", "User", "skill")

        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "correction")
        self.assertEqual(result["extracted_learning"], "Multi-line test")

    @patch('invoke_skill_learning.ANTHROPIC_AVAILABLE', True)
    @patch('invoke_skill_learning.Anthropic')
    @patch('invoke_skill_learning.get_api_key')
    def test_json_with_nested_braces(self, mock_get_key, mock_anthropic):
        """Test parsing JSON with nested objects."""
        mock_get_key.return_value = "test-key"

        # Mock LLM response with nested JSON
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='```json\n{"is_learning": true, "type": "correction", "confidence": 0.9, "category": "High", "extracted_learning": "Test with {nested: data}", "reasoning": "Test", "meta": {"level": 2}}\n```')]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        result = classify_learning_by_llm("Assistant", "User", "skill")

        self.assertIsNotNone(result)
        self.assertIn("nested", result["extracted_learning"])

    @patch('invoke_skill_learning.ANTHROPIC_AVAILABLE', True)
    @patch('invoke_skill_learning.Anthropic')
    @patch('invoke_skill_learning.get_api_key')
    def test_invalid_json_after_parsing(self, mock_get_key, mock_anthropic):
        """Test that invalid JSON after parsing is handled gracefully."""
        mock_get_key.return_value = "test-key"

        # Mock LLM response with invalid JSON
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='```json\n{invalid json here\n```')]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        result = classify_learning_by_llm("Assistant", "User", "skill")

        # Should return None when JSON parsing fails
        self.assertIsNone(result)

    @patch('invoke_skill_learning.ANTHROPIC_AVAILABLE', True)
    @patch('invoke_skill_learning.Anthropic')
    @patch('invoke_skill_learning.get_api_key')
    def test_no_code_fence_fallback_to_raw(self, mock_get_key, mock_anthropic):
        """Test that raw JSON without code fences still works."""
        mock_get_key.return_value = "test-key"

        # Mock LLM response with no code fence
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"is_learning": true, "type": "correction", "confidence": 0.8, "category": "High", "extracted_learning": "Raw JSON", "reasoning": "Test"}')]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.return_value = mock_client

        result = classify_learning_by_llm("Assistant", "User", "skill")

        self.assertIsNotNone(result)
        self.assertEqual(result["extracted_learning"], "Raw JSON")


if __name__ == "__main__":
    # Run with verbose output to see all test names
    unittest.main(verbosity=2)
