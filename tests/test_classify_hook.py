"""Tests for scripts/classify-hook.py helper functions."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.quick_classifier import (
    quick_classify,
    _TRIGGER_PATTERNS,
    _BYPASS_PATTERNS,
)


class TestPatternCompilation:
    """Verify all patterns compile and are valid regex."""

    def test_trigger_patterns_compiled(self):
        assert len(_TRIGGER_PATTERNS) > 0
        for p in _TRIGGER_PATTERNS:
            assert p.pattern  # has a pattern string

    def test_bypass_patterns_compiled(self):
        assert len(_BYPASS_PATTERNS) > 0
        for p in _BYPASS_PATTERNS:
            assert p.pattern


class TestQuickClassifyEdgeCases:
    """Additional edge cases for quick classifier."""

    def test_case_insensitive(self):
        r1 = quick_classify("ANALYZE THE CODE")
        r2 = quick_classify("analyze the code")
        assert r1["use_rlm"] == r2["use_rlm"]

    def test_mixed_trigger_and_bypass(self):
        """When both trigger and bypass match, bypass wins."""
        result = quick_classify("Create a file to analyze results")
        assert result["use_rlm"] is False

    def test_unicode_query(self):
        result = quick_classify("Проанализируй код на ошибки")
        # Should not crash, may not trigger (English patterns)
        assert isinstance(result["use_rlm"], bool)

    def test_very_long_query(self):
        long_query = "Analyze " + "the code " * 1000
        result = quick_classify(long_query)
        assert isinstance(result["use_rlm"], bool)

    def test_result_structure(self):
        result = quick_classify("test query here")
        assert "use_rlm" in result
        assert "reason" in result
        assert "confidence" in result
        assert isinstance(result["use_rlm"], bool)
        assert isinstance(result["reason"], str)
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0


class TestBypassNotOverriddenByLargeProject:
    """
    Regression tests for the large-project logic in classify-hook.
    Bypass decisions must NOT be overridden when a project is large.
    """

    def test_bypass_reason_contains_keyword(self):
        """Bypass results must contain 'bypass' in reason so large-project
        logic can identify and skip them."""
        result = quick_classify("create a file to store data")
        assert result["use_rlm"] is False
        assert "bypass" in result["reason"]

    def test_no_bypass_reason_does_not_contain_bypass(self):
        """Non-bypass results should NOT contain 'bypass' in reason."""
        result = quick_classify("how does the auth system work")
        assert "bypass" not in result["reason"]

    def test_short_query_reason_does_not_contain_bypass(self):
        """Too-short queries should not be labelled as bypass."""
        result = quick_classify("hi")
        assert result["use_rlm"] is False
        assert "bypass" not in result["reason"]