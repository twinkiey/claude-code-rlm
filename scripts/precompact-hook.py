#!/usr/bin/env python3
"""
claude-code-rlm: PreCompact hook

When CC is about to compact (summarize) conversation history,
this hook injects a summary of RLM state so it survives compaction.

This ensures RLM analysis results aren't lost when CC
truncates conversation history.
"""

import json
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    # Check if we have any RLM state to preserve
    # The MCP server tracks completions internally,
    # but we should tell Claude what RLM has already analyzed
    # so it doesn't re-analyze after compaction

    state_file = _get_state_path()
    if not os.path.exists(state_file):
        sys.exit(0)

    try:
        with open(state_file) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    if not state.get("analyses"):
        sys.exit(0)

    # Build summary of what RLM has already done
    summaries = []
    for analysis in state["analyses"]:
        summaries.append(
            f"- **{analysis['query']}** ({analysis['time']:.0f}s, "
            f"{analysis['tokens']:,} tokens): {analysis['summary'][:200]}"
        )

    if summaries:
        output = {
            "additionalContext": (
                "## RLM Analysis History (preserved across compaction)\n\n"
                "The following analyses were already performed by RLM "
                "in this session. Do NOT re-run them unless explicitly "
                "asked:\n\n"
                + "\n".join(summaries)
            ),
        }
        print(json.dumps(output))

    sys.exit(0)


def _get_state_path() -> str:
    """Get path to RLM state file for current session."""
    session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
    state_dir = os.path.join(
        os.path.expanduser("~"),
        ".config", "claude-rlm", "sessions",
    )
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, f"{session_id}.json")


if __name__ == "__main__":
    main()