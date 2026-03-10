"""
claude-code-rlm: RLM plugin for Claude Code

Enhances Claude Code with Recursive Language Model capabilities
for analyzing large codebases and complex tasks.
"""

__version__ = "0.1.0"

# Lazy imports — heavy dependencies (rlm, anthropic, mcp)
# are only imported when actually used, not at package load time.
# This allows tests and lightweight scripts to import
# config, classifier, tools, events, prompts without
# requiring rlm/anthropic/mcp to be installed.


def __getattr__(name):
    """Lazy import for heavy modules."""
    if name == "RLMBridge":
        from .bridge import RLMBridge
        return RLMBridge
    if name == "bridge_main":
        from .bridge import RLMBridge
        return RLMBridge
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# These imports are safe — no heavy dependencies
from .config import load_config, create_default_config, RLMConfig
from .classifier import RLMClassifier, RLMDecision
from .tools import build_custom_tools
from .events import EventEmitter, EventType
from .prompts import build_cc_system_prompt

__all__ = [
    "RLMBridge",
    "load_config",
    "create_default_config",
    "RLMConfig",
    "RLMClassifier",
    "RLMDecision",
    "build_custom_tools",
    "EventEmitter",
    "EventType",
    "build_cc_system_prompt",
]