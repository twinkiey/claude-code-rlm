#!/usr/bin/env python3
"""
claude-code-rlm: MCP Server

Main integration point with Claude Code.
Runs as an MCP server (stdio transport), exposing RLM tools
that Claude can call natively.

CC starts this process automatically via .mcp.json config
and manages its lifecycle — no manual daemon needed.

Uses FastMCP (built into official mcp SDK) for clean tool definitions.
"""

import json
import os
import sys
import traceback
from typing import Annotated

# ── Path setup ────────────────────────────────────────────
# Ensure plugin root is in path for imports
PLUGIN_ROOT = os.environ.get(
    "RLM_PLUGIN_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
sys.path.insert(0, PLUGIN_ROOT)

# ── MCP SDK ───────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP

# ── Plugin imports ────────────────────────────────────────
from python.config import load_config, RLMConfig
from python.tools import build_custom_tools
from python.prompts import build_cc_system_prompt
from python.events import EventEmitter


# ── State ─────────────────────────────────────────────────
# Module-level state, initialized lazily on first tool call.
# MCP server process is long-running — state persists.

_rlm_instance = None
_rlm_config: RLMConfig | None = None
_completion_count = 0
_events = EventEmitter()
_session_analyses: list[dict] = []  # Track what RLM has analyzed


# ── Lazy initialization ──────────────────────────────────

def _get_or_create_rlm():
    """
    Lazily create RLM instance on first tool call.

    Why lazy:
    - MCP server starts when CC session begins
    - rlm + anthropic imports are heavy (~2-3 seconds)
    - User might never call RLM tools in this session
    - No point paying import cost upfront
    """
    global _rlm_instance, _rlm_config

    if _rlm_instance is not None:
        return _rlm_instance

    # Heavy imports — only when needed
    from rlm import RLM
    from rlm.logger import RLMLogger

    project_root = os.environ.get("RLM_PROJECT_ROOT", "")
    if not project_root or project_root.startswith("${"):
        project_root = os.getcwd()
    _rlm_config = load_config(project_root=project_root)

    custom_tools = build_custom_tools(
        project_root=_rlm_config.project_root,
        tools_config=_rlm_config.tools,
    )

    system_prompt = build_cc_system_prompt(
        custom_additions=_rlm_config.custom_system_prompt,
    )

    callbacks = _events.make_callbacks()

    logger = (
        RLMLogger(log_dir=_rlm_config.log_dir)
        if _rlm_config.log_dir
        else RLMLogger()
    )

    _rlm_instance = RLM(
        backend=_rlm_config.backend,
        backend_kwargs=_rlm_config.backend_kwargs,
        other_backends=_rlm_config.other_backends,
        other_backend_kwargs=_rlm_config.other_backend_kwargs,
        environment=_rlm_config.environment,
        environment_kwargs=_rlm_config.environment_kwargs,
        max_depth=_rlm_config.max_depth,
        max_iterations=_rlm_config.max_iterations,
        max_budget=_rlm_config.max_budget,
        max_timeout=_rlm_config.max_timeout,
        max_tokens=_rlm_config.max_tokens,
        max_errors=_rlm_config.max_errors,
        persistent=_rlm_config.persistent,
        compaction=_rlm_config.compaction,
        compaction_threshold_pct=_rlm_config.compaction_threshold_pct,
        custom_system_prompt=system_prompt,
        custom_tools=custom_tools,
        logger=logger,
        verbose=_rlm_config.verbose,
        **callbacks,
    )

    _events.session_start(config={
        "backend": _rlm_config.backend,
        "model": _rlm_config.backend_kwargs.get("model_name", "unknown"),
        "max_depth": _rlm_config.max_depth,
        "project_root": _rlm_config.project_root,
    })

    return _rlm_instance


def _format_usage(result) -> str:
    """Format usage statistics as readable string."""
    usage = result.usage_summary
    total_tokens = usage.total_input_tokens + usage.total_output_tokens

    parts = [f"⏱️ {result.execution_time:.1f}s"]
    parts.append(f"📊 {total_tokens:,} tokens")

    if usage.total_cost is not None:
        parts.append(f"💰 ${usage.total_cost:.4f}")

    # Per-model breakdown
    model_lines = []
    for model, summary in usage.model_usage_summaries.items():
        short_name = model.split("/")[-1] if "/" in model else model
        model_tokens = summary.total_input_tokens + summary.total_output_tokens
        model_lines.append(
            f"  {short_name}: {summary.total_calls} calls, "
            f"{model_tokens:,} tokens"
        )

    summary_line = " | ".join(parts)
    if model_lines:
        summary_line += "\n" + "\n".join(model_lines)

    return summary_line


def _record_analysis(query: str, result) -> None:
    """Record analysis for PreCompact state preservation."""
    global _session_analyses

    usage = result.usage_summary
    _session_analyses.append({
        "query": query,
        "time": result.execution_time,
        "tokens": usage.total_input_tokens + usage.total_output_tokens,
        "summary": result.response[:300],
    })

    # Save to session state file for PreCompact hook
    try:
        session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
        state_dir = os.path.join(
            os.path.expanduser("~"),
            ".config", "claude-rlm", "sessions",
        )
        os.makedirs(state_dir, exist_ok=True)
        state_file = os.path.join(state_dir, f"{session_id}.json")

        with open(state_file, "w") as f:
            json.dump({"analyses": _session_analyses}, f, default=str)
    except OSError:
        pass  # Non-critical


# ── MCP Server ────────────────────────────────────────────

mcp = FastMCP(
    "claude-code-rlm",
    instructions=(
        "RLM (Recursive Language Model) tools for deep codebase analysis. "
        "Use rlm_analyze for comprehensive code analysis that exceeds "
        "the context window. Use rlm_search for semantic code search."
    ),
)


@mcp.tool()
def rlm_analyze(
    query: Annotated[
        str,
        "The analysis query. Be specific about what to analyze. "
        "Examples: 'How does the authentication system work?', "
        "'Find all SQL injection vulnerabilities', "
        "'Map the dependency graph of the payment module'",
    ],
    focus_paths: Annotated[
        str,
        "Optional: comma-separated paths to focus on. "
        "If empty, RLM explores the entire project. "
        "Example: 'src/auth,src/middleware,lib/crypto'",
    ] = "",
) -> str:
    """
    Deep recursive analysis of a codebase using RLM.

    Programmatically explores, decomposes, and analyzes code
    that exceeds the context window. The RLM engine autonomously
    reads files, searches code, and recursively delegates sub-tasks
    to focused sub-LM calls.

    Best for: architecture review, security audit, cross-file analysis,
    understanding complex systems, finding patterns across many files.

    Takes 30-120+ seconds depending on codebase size and query complexity.
    """
    global _completion_count

    rlm = _get_or_create_rlm()

    # Build context
    project_root = _rlm_config.project_root
    context = {
        "project_root": project_root,
        "project_name": os.path.basename(project_root),
    }

    if focus_paths:
        context["focus_paths"] = [
            p.strip() for p in focus_paths.split(",") if p.strip()
        ]

    _events.rlm_start(query=query, context_size=None)

    try:
        from rlm import TimeoutExceededError, CancellationError

        try:
            result = rlm.completion(
                prompt=context,
                root_prompt=query,
            )
        except TimeoutExceededError as e:
            _events.rlm_error(f"Timeout: {e.elapsed:.1f}s")
            partial = e.partial_answer or "Analysis timed out."
            return (
                f"## RLM Analysis (partial — timed out after "
                f"{e.elapsed:.1f}s)\n\n{partial}"
            )
        except CancellationError as e:
            partial = e.partial_answer or "Analysis cancelled."
            return f"## RLM Analysis (cancelled)\n\n{partial}"

        _completion_count += 1

        usage = result.usage_summary
        total_tokens = usage.total_input_tokens + usage.total_output_tokens

        _events.rlm_complete(
            execution_time=result.execution_time,
            tokens=total_tokens,
            cost=usage.total_cost,
        )

        _record_analysis(query, result)

        usage_info = _format_usage(result)
        return (
            f"## RLM Deep Analysis\n\n"
            f"**Query:** {query}\n\n"
            f"---\n\n"
            f"{result.response}\n\n"
            f"---\n\n"
            f"*{usage_info}*"
        )

    except Exception as e:
        _events.rlm_error(str(e))
        return f"RLM Analysis Error: {e}\n\n{traceback.format_exc()}"


@mcp.tool()
def rlm_search(
    query: Annotated[
        str,
        "What to search for. Can be semantic — understands code meaning, "
        "not just text matching. Examples: "
        "'where is user authentication implemented?', "
        "'all places where database connections are opened', "
        "'error handling for payment failures'",
    ],
    file_pattern: Annotated[
        str,
        "Optional: glob pattern to filter files. "
        "Example: '*.py', '*.ts', 'src/**/*.java'",
    ] = "",
) -> str:
    """
    Semantic search across a large codebase using RLM.

    Unlike grep, this understands code semantics — finds implementations,
    usages, and related code even when naming differs. Uses recursive
    decomposition to efficiently search large codebases.

    Best for: finding where something is implemented, tracing data flow,
    locating all related code for a concept.

    Returns specific file paths, line numbers, and relevant code snippets.
    """
    rlm = _get_or_create_rlm()

    project_root = _rlm_config.project_root
    context = {
        "project_root": project_root,
        "search_mode": True,
    }

    if file_pattern:
        context["file_pattern"] = file_pattern

    search_prompt = (
        f"Search the codebase for: {query}\n\n"
        f"Strategy:\n"
        f"1. Use search_code() and file_tree() to locate relevant code\n"
        f"2. Read candidate files with read_file()\n"
        f"3. Use llm_query() to analyze if code matches semantically\n"
        f"4. Return specific file paths, line numbers, and code snippets\n"
    )

    if file_pattern:
        search_prompt += f"\nFocus on files matching: {file_pattern}"

    _events.rlm_start(query=query, context_size=None)

    try:
        from rlm import TimeoutExceededError

        try:
            result = rlm.completion(
                prompt=context,
                root_prompt=search_prompt,
            )
        except TimeoutExceededError as e:
            partial = e.partial_answer or "Search timed out."
            return f"## RLM Search (partial — timed out)\n\n{partial}"

        usage = result.usage_summary
        total_tokens = usage.total_input_tokens + usage.total_output_tokens

        _events.rlm_complete(
            execution_time=result.execution_time,
            tokens=total_tokens,
            cost=usage.total_cost,
        )

        _record_analysis(f"[search] {query}", result)

        usage_info = _format_usage(result)
        return (
            f"## RLM Search Results\n\n"
            f"**Query:** {query}\n\n"
            f"---\n\n"
            f"{result.response}\n\n"
            f"---\n\n"
            f"*{usage_info}*"
        )

    except Exception as e:
        _events.rlm_error(str(e))
        return f"RLM Search Error: {e}"


@mcp.tool()
def rlm_status() -> str:
    """
    Check RLM plugin status.

    Returns whether the RLM engine is initialized,
    configuration details, and usage statistics
    for the current session.
    """
    status = {
        "initialized": _rlm_instance is not None,
        "completions": _completion_count,
        "analyses_this_session": len(_session_analyses),
    }

    if _rlm_config:
        status["config"] = {
            "backend": _rlm_config.backend,
            "model": _rlm_config.backend_kwargs.get("model_name"),
            "worker_model": (
                _rlm_config.other_backend_kwargs[0].get("model_name")
                if _rlm_config.other_backend_kwargs
                else None
            ),
            "max_depth": _rlm_config.max_depth,
            "max_iterations": _rlm_config.max_iterations,
            "max_timeout": _rlm_config.max_timeout,
            "persistent": _rlm_config.persistent,
            "compaction": _rlm_config.compaction,
            "project_root": _rlm_config.project_root,
            "tools_enabled": [
                name for name, enabled
                in vars(_rlm_config.tools).items()
                if enabled is True
            ],
        }

    if _session_analyses:
        status["recent_analyses"] = [
            {
                "query": a["query"],
                "time": f"{a['time']:.1f}s",
                "tokens": f"{a['tokens']:,}",
            }
            for a in _session_analyses[-5:]  # Last 5
        ]

    return json.dumps(status, indent=2, default=str)


# ── Entry point ───────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()