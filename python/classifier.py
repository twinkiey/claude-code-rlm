"""
claude-code-rlm: Auto-trigger classifier

Decides whether a query should be routed through RLM
or handled by standard Claude Code.
"""

from __future__ import annotations

from typing import Any
from .config import AutoTriggerConfig


class RLMDecision:
    """Result of the RLM classifier."""

    __slots__ = ("use_rlm", "reason", "confidence")

    def __init__(
        self,
        use_rlm: bool,
        reason: str,
        confidence: float,
    ):
        self.use_rlm = use_rlm
        self.reason = reason
        self.confidence = confidence  # 0.0 - 1.0

    def __repr__(self):
        verdict = "RLM" if self.use_rlm else "STANDARD"
        return (
            f"RLMDecision({verdict}, "
            f"confidence={self.confidence:.0%}, "
            f"reason='{self.reason}')"
        )

    def __bool__(self):
        return self.use_rlm


class RLMClassifier:
    """
    Heuristic classifier that decides when to use RLM.

    Logic:
    1. If user explicitly requested RLM (e.g. /rlm command) → always RLM
    2. Check bypass patterns → if match, skip RLM
    3. Check trigger conditions → if match, use RLM
    4. Default → standard CC (no RLM)
    """

    def __init__(self, config: AutoTriggerConfig):
        self.config = config
        self.trigger_keywords = [kw.lower() for kw in config.trigger_keywords]
        self.bypass_keywords = [kw.lower() for kw in config.bypass_keywords]

    def should_use_rlm(
        self,
        query: str,
        context: Any = None,
        force: bool = False,
        file_lines: int | None = None,
        project_files: int | None = None,
    ) -> RLMDecision:
        """
        Decide whether to use RLM for this query.

        Args:
            query: user's query text
            context: additional context (file content, dict, etc.)
            force: if True, always use RLM (manual trigger)
            file_lines: number of lines in active file
            project_files: number of files in project

        Returns:
            RLMDecision with verdict and reasoning
        """
        # Manual override
        if force:
            return RLMDecision(
                use_rlm=True,
                reason="manually triggered",
                confidence=1.0,
            )

        # Auto-trigger disabled
        if not self.config.enabled:
            return RLMDecision(
                use_rlm=False,
                reason="auto-trigger disabled",
                confidence=1.0,
            )

        query_lower = query.lower()

        # ── Bypass check ──
        for keyword in self.bypass_keywords:
            if keyword in query_lower:
                return RLMDecision(
                    use_rlm=False,
                    reason=f"bypass keyword: '{keyword}'",
                    confidence=0.8,
                )

        # ── Trigger checks ──
        triggers: list[str] = []
        confidence = 0.0

        # 1. Large context
        if context is not None:
            context_size = len(str(context))
            if context_size > self.config.min_context_chars:
                triggers.append(
                    f"large context: {context_size:,} chars "
                    f"(threshold: {self.config.min_context_chars:,})"
                )
                confidence = max(confidence, 0.9)

        # 2. Large file
        if file_lines is not None and file_lines > self.config.min_file_lines:
            triggers.append(
                f"large file: {file_lines:,} lines "
                f"(threshold: {self.config.min_file_lines:,})"
            )
            confidence = max(confidence, 0.85)

        # 3. Large project
        if (
            project_files is not None
            and project_files > self.config.min_project_files
        ):
            triggers.append(
                f"large project: {project_files} files "
                f"(threshold: {self.config.min_project_files})"
            )
            confidence = max(confidence, 0.7)

        # 4. Trigger keywords
        matched_keywords = [
            kw for kw in self.trigger_keywords
            if kw in query_lower
        ]
        if matched_keywords:
            triggers.append(f"keywords: {matched_keywords}")
            confidence = max(confidence, 0.75)

        # 5. Multiple files in context
        if isinstance(context, dict) and len(context) > 3:
            triggers.append(f"multi-file context: {len(context)} items")
            confidence = max(confidence, 0.8)

        # 6. Computation indicators
        compute_keywords = [
            "calculate", "compute", "benchmark", "measure",
            "count lines", "statistics", "how many", "count all",
            "percentage", "ratio", "average",
        ]
        matched_compute = [
            kw for kw in compute_keywords
            if kw in query_lower
        ]
        if matched_compute:
            triggers.append(f"computation: {matched_compute}")
            confidence = max(confidence, 0.7)

        # ── Decision ──
        if triggers:
            return RLMDecision(
                use_rlm=True,
                reason="; ".join(triggers),
                confidence=confidence,
            )

        return RLMDecision(
            use_rlm=False,
            reason="no triggers matched",
            confidence=0.6,
        )