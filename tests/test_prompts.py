"""Tests for python/prompts.py — system prompt generation."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python.prompts import build_cc_system_prompt, CC_SYSTEM_PROMPT_PREFIX


class TestBuildSystemPrompt:
    """Test system prompt builder."""

    def test_contains_tool_descriptions(self):
        prompt = build_cc_system_prompt()
        assert "read_file" in prompt
        assert "search_code" in prompt
        assert "file_tree" in prompt
        assert "git_log" in prompt
        assert "git_diff" in prompt
        assert "SHOW_VARS" in prompt

    def test_contains_strategies(self):
        prompt = build_cc_system_prompt()
        assert "map-reduce" in prompt.lower() or "Map phase" in prompt
        assert "FINAL_VAR" in prompt

    def test_contains_large_codebase_strategy(self):
        prompt = build_cc_system_prompt()
        assert "100k" in prompt or "large" in prompt.lower()

    def test_custom_additions(self):
        prompt = build_cc_system_prompt(
            custom_additions="Always respond in Spanish."
        )
        assert "Always respond in Spanish" in prompt
        assert "Additional Instructions" in prompt

    def test_no_custom_additions(self):
        prompt = build_cc_system_prompt(custom_additions=None)
        assert "Additional Instructions" not in prompt

    def test_prefix_not_empty(self):
        assert len(CC_SYSTEM_PROMPT_PREFIX) > 100