"""Tests for python/classifier.py and scripts/quick_classifier.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python.classifier import RLMClassifier, RLMDecision
from python.config import AutoTriggerConfig
from scripts.quick_classifier import quick_classify


class TestQuickClassifier:
    """Test the regex-based quick classifier."""

    # ── Should trigger RLM ──

    def test_analyze_triggers(self):
        assert quick_classify("Analyze the auth system")["use_rlm"] is True

    def test_review_all_triggers(self):
        assert quick_classify("Review all modules for bugs")["use_rlm"] is True

    def test_entire_codebase_triggers(self):
        result = quick_classify("Search the entire codebase for TODO")
        assert result["use_rlm"] is True

    def test_security_vulnerabilities_triggers(self):
        result = quick_classify("Find security vulnerabilities")
        assert result["use_rlm"] is True

    def test_architecture_triggers(self):
        result = quick_classify("Explain the architecture of this project")
        assert result["use_rlm"] is True

    def test_refactor_triggers(self):
        assert quick_classify("Refactor the payment module")["use_rlm"] is True

    def test_across_all_files_triggers(self):
        result = quick_classify("Find all imports across all files")
        assert result["use_rlm"] is True

    def test_dead_code_triggers(self):
        result = quick_classify("Find dead code in the project")
        assert result["use_rlm"] is True

    def test_dependency_graph_triggers(self):
        result = quick_classify("Map the dependency graph")
        assert result["use_rlm"] is True

    def test_count_all_triggers(self):
        result = quick_classify("Count all functions in the codebase")
        assert result["use_rlm"] is True

    def test_how_does_work_triggers(self):
        result = quick_classify("How does the authentication system work?")
        assert result["use_rlm"] is True

    # ── Should NOT trigger RLM ──

    def test_create_file_bypass(self):
        result = quick_classify("Create a new file called utils.py")
        assert result["use_rlm"] is False

    def test_write_function_bypass(self):
        result = quick_classify("Write a function to sort a list")
        assert result["use_rlm"] is False

    def test_run_tests_bypass(self):
        result = quick_classify("Run tests for the auth module")
        assert result["use_rlm"] is False

    def test_commit_bypass(self):
        assert quick_classify("Commit these changes")["use_rlm"] is False

    def test_implement_bypass(self):
        result = quick_classify("Implement a new endpoint for /users")
        assert result["use_rlm"] is False

    def test_fix_this_bypass(self):
        result = quick_classify("Fix this error in line 42")
        assert result["use_rlm"] is False

    def test_add_method_bypass(self):
        result = quick_classify("Add a method to the User class")
        assert result["use_rlm"] is False

    # ── Edge cases ──

    def test_empty_query(self):
        assert quick_classify("")["use_rlm"] is False

    def test_short_query(self):
        assert quick_classify("hello")["use_rlm"] is False

    def test_no_match(self):
        result = quick_classify("What is the meaning of life?")
        assert result["use_rlm"] is False

    def test_confidence_increases_with_matches(self):
        single = quick_classify("Analyze the code")
        multi = quick_classify(
            "Analyze the entire codebase, review all files, "
            "find dead code and security vulnerabilities"
        )
        assert multi["confidence"] > single["confidence"]

    def test_result_has_reason(self):
        result = quick_classify("Analyze the system")
        assert "reason" in result
        assert len(result["reason"]) > 0


class TestRLMClassifier:
    """Test the full heuristic classifier."""

    def _make_classifier(self, **kwargs) -> RLMClassifier:
        config = AutoTriggerConfig(**kwargs)
        return RLMClassifier(config)

    # ── Force mode ──

    def test_force_always_true(self):
        classifier = self._make_classifier(enabled=False)
        decision = classifier.should_use_rlm("hello", force=True)
        assert decision.use_rlm is True
        assert decision.confidence == 1.0

    # ── Disabled ──

    def test_disabled_always_false(self):
        classifier = self._make_classifier(enabled=False)
        decision = classifier.should_use_rlm(
            "Analyze the entire codebase for vulnerabilities"
        )
        assert decision.use_rlm is False

    # ── Context size trigger ──

    def test_large_context_triggers(self):
        classifier = self._make_classifier(min_context_chars=100)
        decision = classifier.should_use_rlm(
            "What is this?",
            context="x" * 200,
        )
        assert decision.use_rlm is True
        assert decision.confidence >= 0.9

    def test_small_context_no_trigger(self):
        classifier = self._make_classifier(min_context_chars=50000)
        decision = classifier.should_use_rlm(
            "What is this?",
            context="small content",
        )
        assert decision.use_rlm is False

    # ── File lines trigger ──

    def test_large_file_triggers(self):
        classifier = self._make_classifier(min_file_lines=100)
        decision = classifier.should_use_rlm(
            "Explain this file",
            file_lines=500,
        )
        assert decision.use_rlm is True

    def test_small_file_no_trigger(self):
        classifier = self._make_classifier(min_file_lines=5000)
        decision = classifier.should_use_rlm(
            "Explain this file",
            file_lines=100,
        )
        assert decision.use_rlm is False

    # ── Project size trigger ──

    def test_large_project_triggers(self):
        classifier = self._make_classifier(min_project_files=10)
        decision = classifier.should_use_rlm(
            "How does this work?",
            project_files=100,
        )
        assert decision.use_rlm is True

    # ── Keyword triggers ──

    def test_trigger_keywords(self):
        classifier = self._make_classifier(
            trigger_keywords=["analyze", "refactor"],
        )
        decision = classifier.should_use_rlm("Analyze the auth module")
        assert decision.use_rlm is True

    def test_bypass_keywords(self):
        classifier = self._make_classifier(
            trigger_keywords=["analyze"],
            bypass_keywords=["create file"],
        )
        decision = classifier.should_use_rlm("Create file for analysis")
        assert decision.use_rlm is False

    # ── Multi-file context ──

    def test_dict_context_triggers(self):
        classifier = self._make_classifier()
        context = {f"file{i}.py": f"content {i}" for i in range(5)}
        decision = classifier.should_use_rlm(
            "Compare these files",
            context=context,
        )
        assert decision.use_rlm is True

    # ── Computation keywords ──

    def test_compute_triggers(self):
        classifier = self._make_classifier()
        decision = classifier.should_use_rlm(
            "Calculate the statistics for code coverage"
        )
        assert decision.use_rlm is True

    # ── Decision object ──

    def test_decision_bool(self):
        decision = RLMDecision(use_rlm=True, reason="test", confidence=0.9)
        assert bool(decision) is True

        decision2 = RLMDecision(use_rlm=False, reason="test", confidence=0.5)
        assert bool(decision2) is False

    def test_decision_repr(self):
        decision = RLMDecision(use_rlm=True, reason="big file", confidence=0.85)
        r = repr(decision)
        assert "RLM" in r
        assert "85%" in r
        assert "big file" in r