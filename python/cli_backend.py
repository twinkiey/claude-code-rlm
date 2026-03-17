"""
claude-code-rlm: Claude CLI Backend

Implements BaseLM using 'claude -p' subprocess,
allowing RLM to work with a Claude Pro subscription without an API key.

Prompt is passed via stdin for safety and to support long inputs
(avoids shell argument length limits and special character issues).
"""

import asyncio
import subprocess
from typing import Any

from rlm.clients.base_lm import BaseLM

# Import usage types — fall back to simple dataclasses if the internal
# path changes between rlms versions.
try:
    from rlm.utils.types import UsageSummary, ModelUsageSummary
except ImportError:
    from dataclasses import dataclass, field

    @dataclass
    class ModelUsageSummary:  # type: ignore[no-redef]
        model: str = "claude-cli"
        input_tokens: int = 0
        output_tokens: int = 0
        cost: float = 0.0

    @dataclass
    class UsageSummary:  # type: ignore[no-redef]
        total_input_tokens: int = 0
        total_output_tokens: int = 0
        total_cost: float = 0.0


class ClaudeCliLM(BaseLM):
    """
    LM backend that delegates to the installed 'claude' CLI binary.

    Auth is handled by Claude Code itself — no API key required.
    Compatible with Claude Pro and Max subscriptions.

    Config example (.claude-rlm.yaml):
        backend: claude-cli
        backend_kwargs:
          timeout: 120        # seconds per call (default 120)
          extra_args: []      # additional CLI flags, e.g. ["--yes"]
    """

    def __init__(
        self,
        model_name: str = "claude-cli",
        timeout: int = 120,
        extra_args: list[str] | None = None,
        **kwargs: Any,  # absorb unknown backend_kwargs gracefully
    ):
        self.model_name = model_name
        self.timeout = timeout
        self.extra_args = extra_args or []

    # ── Prompt conversion ────────────────────────────────────

    def _prompt_to_str(self, prompt: str | list[dict]) -> str:
        """Convert prompt (str or message history) to a plain string for CLI."""
        if isinstance(prompt, str):
            return prompt

        parts = []
        for msg in prompt:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Handle structured content blocks (Anthropic message format)
            if isinstance(content, list):
                text_parts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                content = "\n".join(text_parts)

            if role == "system":
                parts.append(f"[System]\n{content}")
            elif role == "assistant":
                parts.append(f"[Assistant]\n{content}")
            else:
                parts.append(f"[User]\n{content}")

        return "\n\n".join(parts)

    # ── CLI call ─────────────────────────────────────────────

    def _run_cli(self, prompt_str: str) -> str:
        """Run 'claude -p' with prompt on stdin, return stdout."""
        cmd = ["claude", "-p", "--output-format", "text"] + self.extra_args
        try:
            result = subprocess.run(
                cmd,
                input=prompt_str,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"claude CLI timed out after {self.timeout}s"
            ) from e
        except FileNotFoundError as e:
            raise RuntimeError(
                "claude CLI not found in PATH. "
                "Make sure Claude Code is installed: npm install -g @anthropic-ai/claude-code"
            ) from e

        if result.returncode != 0:
            err = result.stderr.strip() or "unknown error"
            raise RuntimeError(f"claude CLI exited {result.returncode}: {err}")

        output = result.stdout.strip()
        import sys
        print(f"[claude-cli] prompt_len={len(prompt_str)} output_len={len(output)} output_preview={output[:200]!r}", file=sys.stderr)
        return output

    # ── BaseLM interface ─────────────────────────────────────

    def completion(self, prompt: str | dict[str, Any]) -> str:
        return self._run_cli(self._prompt_to_str(prompt))

    async def acompletion(self, prompt: str | dict[str, Any]) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.completion, prompt)

    def get_usage_summary(self) -> UsageSummary:
        # CLI doesn't report token counts; return zeros so rlms doesn't crash.
        return UsageSummary(
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost=0.0,
        )

    def get_last_usage(self) -> ModelUsageSummary:
        return ModelUsageSummary(
            model=self.model_name,
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
        )
