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
        """
        Run 'claude -p <prompt>' and return the response.

        Strategy:
        - Short prompts (≤8000 chars): pass as direct CLI argument.
          Avoids all stdin/TTY issues; confirmed working on Windows.
        - Long prompts: write to temp file and use cmd.exe input
          redirection ('claude -p < file'). cmd.exe opens the file
          as a real file handle (not a Python pipe), which sidesteps
          the Windows TTY-detection issue that causes claude to produce
          no stdout when stdin is a Python subprocess PIPE.
        """
        import os
        import sys
        import tempfile

        # Windows command-line limit is ~8191 chars via cmd.exe; stay safe
        _ARG_LIMIT = 8000

        tmp_path = None
        stdin_src = None
        try:
            # MCP server's stdin is the MCP protocol pipe from Claude Code.
            # Any subprocess that inherits it will read MCP JSON instead of
            # our prompt and hang. We must always override stdin explicitly.
            if len(prompt_str) <= _ARG_LIMIT:
                cmd = ["claude", "-p", prompt_str] + self.extra_args
                stdin_src = subprocess.DEVNULL
            else:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".txt",
                    delete=False,
                    encoding="utf-8",
                ) as f:
                    f.write(prompt_str)
                    tmp_path = f.name
                cmd = ["claude", "-p"] + self.extra_args
                stdin_src = open(tmp_path, "r", encoding="utf-8")

            try:
                result = subprocess.run(
                    cmd,
                    stdin=stdin_src,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self.timeout,
                    encoding="utf-8",
                    errors="replace",
                )
            except subprocess.TimeoutExpired as e:
                raise RuntimeError(
                    f"claude CLI timed out after {self.timeout}s"
                ) from e
            except FileNotFoundError as e:
                raise RuntimeError(
                    "claude CLI not found in PATH. "
                    "Make sure Claude Code is installed: "
                    "npm install -g @anthropic-ai/claude-code"
                ) from e

            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()

            if result.returncode != 0:
                raise RuntimeError(
                    f"claude CLI exited {result.returncode}: {stderr or 'unknown error'}"
                )

            if not stdout:
                raise RuntimeError(
                    f"claude CLI produced no output "
                    f"(returncode={result.returncode}, stderr={stderr!r})"
                )

            return stdout

        finally:
            if isinstance(stdin_src, object) and hasattr(stdin_src, "close"):
                try:
                    stdin_src.close()
                except Exception:
                    pass
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

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
