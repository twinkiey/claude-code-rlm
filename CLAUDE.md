# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install in development mode
pip install -e .

# Run all tests (no API keys required)
pytest tests/

# Run a single test file
pytest tests/test_classifier.py

# Run a single test by name
pytest tests/test_classifier.py::TestRLMClassifier::test_bypass_keywords

# Run the plugin (from parent directory)
claude --plugin-dir ./claude-code-rlm
```

## Architecture

**claude-code-rlm** is a Claude Code plugin that integrates Recursive Language Models (RLM) for deep analysis of large codebases. Instead of loading entire codebases into context, it gives Claude a Python REPL where it can programmatically explore code and recursively delegate sub-analysis to focused sub-LM calls.

### Three integration points with Claude Code

1. **`UserPromptSubmit` hook** (`scripts/classify-hook.py`) — Fast (<1s) regex-based classification with no API calls. If the query needs deep analysis, injects `additionalContext` telling Claude to use `rlm_analyze`. Uses `scripts/quick_classifier.py` for heuristics.

2. **MCP Server** (`python/mcp_server.py`) — Long-lived process started via `.mcp.json`. Exposes three tools: `rlm_analyze(query, focus_paths)`, `rlm_search(query, file_pattern)`, `rlm_status()`. Uses lazy initialization — heavy dependencies only load on first tool call.

3. **Skill** (`skills/rlm/SKILL.md`) — `/rlm` slash command for manual activation.

### Request flow

```
User query
  → UserPromptSubmit hook (classify-hook.py → quick_classifier.py)
      → RLM needed? inject additionalContext → Claude calls rlm_analyze
          → MCP Server (mcp_server.py)
              → RLM.completion() runs Python REPL
                  → custom tools: read_file, search_code, file_tree, git_*
                  → recursive sub-LM calls via llm_query / rlm_query
              → returns analysis to Claude
```

### Key modules

| File | Purpose |
|------|---------|
| `python/mcp_server.py` | MCP tool definitions + RLM lifecycle management |
| `python/bridge.py` | `RLMBridge` — wraps the `rlms` library, manages RLM instance |
| `python/config.py` | Config loading: defaults → `~/.config/claude-rlm/config.yaml` → `.claude-rlm.yaml` → env vars |
| `python/classifier.py` | `RLMClassifier` — heuristic routing decisions (bypass vs. trigger keywords, context size) |
| `python/tools.py` | Custom tools injected into RLM's REPL (read_file, search_code, git_info, file_tree, etc.) |
| `python/prompts.py` | System prompts optimized for code analysis |
| `python/events.py` | JSON event emission for state tracking |

### Configuration

Config is loaded in priority order (lowest → highest): built-in defaults, global `~/.config/claude-rlm/config.yaml`, project `.claude-rlm.yaml`, environment variables.

Key settings: `backend`, `backend_kwargs.model_name`, `max_depth` (recursion depth, default 2), `max_iterations` (REPL iterations, default 20), `max_timeout` (seconds, default 120), `persistent` (keep REPL alive, default true), `auto_trigger` (classification settings).

See `.claude-rlm.example.yaml` for the full example config.

### Auto-trigger classifier decision order

1. `/rlm` prefix → force RLM
2. Auto-trigger disabled → standard CC
3. Bypass keywords match (create file, run tests, commit…) → skip RLM
4. Trigger keywords match (analyze, refactor, security, entire codebase…) → use RLM
5. Context size thresholds exceeded → use RLM
6. Default → standard CC

### REPL security model

`read_file` and `write_file` are sandboxed to project root. `write_file` and `run_command` are **disabled by default** (opt-in via config). Dangerous builtins (`eval`, `exec`, `compile`, `input`) are removed. However, `__import__` remains available, so there is no full isolation — intended for local development only.
