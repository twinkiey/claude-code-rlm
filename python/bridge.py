"""
claude-code-rlm: RLM Bridge (library)

Core logic for creating and managing RLM instances.
Used by mcp_server.py. Can also be used standalone.

This module is NOT a daemon — it's a library that
mcp_server.py and other entry points use.
"""

import json
import os
import traceback
from typing import Any

from rlm import RLM, TimeoutExceededError, CancellationError
from rlm.logger import RLMLogger

from .config import load_config, RLMConfig
from .classifier import RLMClassifier
from .tools import build_custom_tools
from .events import EventEmitter
from .prompts import build_cc_system_prompt


class RLMBridge:
    """
    Bridge between integration layer (MCP/hooks) and RLM library.
    Manages a persistent RLM instance.
    """

    def __init__(self):
        self._rlm: RLM | None = None
        self._config: RLMConfig | None = None
        self._classifier: RLMClassifier | None = None
        self._events = EventEmitter()
        self._initialized = False
        self._completion_count = 0

    @property
    def config(self) -> RLMConfig | None:
        return self._config

    @property
    def completion_count(self) -> int:
        return self._completion_count

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def init(self, config_overrides: dict | None = None) -> dict:
        """Initialize the RLM instance."""
        try:
            self._config = load_config(
                project_root=(
                    config_overrides.get("project_root")
                    if config_overrides
                    else None
                )
            )

            if config_overrides:
                for key, value in config_overrides.items():
                    if hasattr(self._config, key):
                        setattr(self._config, key, value)

            self._classifier = RLMClassifier(self._config.auto_trigger)

            custom_tools = build_custom_tools(
                project_root=self._config.project_root,
                tools_config=self._config.tools,
            )

            system_prompt = build_cc_system_prompt(
                custom_additions=self._config.custom_system_prompt,
            )

            callbacks = self._events.make_callbacks()

            logger = RLMLogger(
                log_dir=self._config.log_dir,
            ) if self._config.log_dir else RLMLogger()

            self._rlm = RLM(
                backend=self._config.backend,
                backend_kwargs=self._config.backend_kwargs,
                other_backends=self._config.other_backends,
                other_backend_kwargs=self._config.other_backend_kwargs,
                environment=self._config.environment,
                environment_kwargs=self._config.environment_kwargs,
                max_depth=self._config.max_depth,
                max_iterations=self._config.max_iterations,
                max_budget=self._config.max_budget,
                max_timeout=self._config.max_timeout,
                max_tokens=self._config.max_tokens,
                max_errors=self._config.max_errors,
                persistent=self._config.persistent,
                compaction=self._config.compaction,
                compaction_threshold_pct=self._config.compaction_threshold_pct,
                custom_system_prompt=system_prompt,
                custom_tools=custom_tools,
                logger=logger,
                verbose=self._config.verbose,
                **callbacks,
            )

            self._initialized = True

            return {
                "status": "ok",
                "config": {
                    "backend": self._config.backend,
                    "model": self._config.backend_kwargs.get("model_name"),
                    "max_depth": self._config.max_depth,
                    "project_root": self._config.project_root,
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

    def completion(
        self,
        query: str,
        context: Any = None,
        force: bool = False,
    ) -> dict:
        """Run an RLM completion."""
        if not self._initialized or not self._rlm:
            return {"status": "error", "error": "Not initialized"}

        # Consult classifier unless caller explicitly forces RLM usage.
        # This respects the auto_trigger config (enabled flag, bypass keywords,
        # trigger keywords, thresholds) so callers get correct routing.
        if not force and self._classifier is not None:
            decision = self._classifier.should_use_rlm(query, context=context)
            if not decision.use_rlm:
                return {
                    "status": "skipped",
                    "reason": decision.reason,
                    "confidence": decision.confidence,
                }

        prompt = context if context else query
        root_prompt = query if context else None

        try:
            result = self._rlm.completion(
                prompt=prompt,
                root_prompt=root_prompt,
            )

            self._completion_count += 1
            usage = result.usage_summary

            return {
                "status": "ok",
                "response": result.response,
                "execution_time": result.execution_time,
                "usage": {
                    "input_tokens": usage.total_input_tokens,
                    "output_tokens": usage.total_output_tokens,
                    "total_tokens": (
                        usage.total_input_tokens
                        + usage.total_output_tokens
                    ),
                    "cost": usage.total_cost,
                },
                "metadata": result.metadata,
            }

        except TimeoutExceededError as e:
            return {
                "status": "timeout",
                "partial_answer": e.partial_answer,
                "elapsed": e.elapsed,
            }
        except CancellationError as e:
            return {
                "status": "cancelled",
                "partial_answer": e.partial_answer,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

    def close(self):
        """Clean up."""
        if self._rlm:
            try:
                self._rlm.close()
            except Exception:
                pass
        self._initialized = False