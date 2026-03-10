#!/usr/bin/env python3
"""
claude-code-rlm: UserPromptSubmit hook

FAST classifier (< 1 second). Does NOT run RLM.
Only decides if Claude should be told to use RLM tools.

If RLM is needed:
  → Injects additionalContext telling Claude to use rlm_* MCP tools
  → Claude then calls rlm_analyze/rlm_search (no timeout issues)

If RLM is not needed:
  → Empty exit 0, Claude proceeds normally
"""

import json
import os
import sys

# Add plugin root for imports
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)

from scripts.quick_classifier import quick_classify


def main():
    # ── Read hook input ──────────────────────────────────
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    # Extract prompt
    query = None
    for field in ["prompt", "query", "message", "content"]:
        if field in hook_input and isinstance(hook_input[field], str):
            query = hook_input[field].strip()
            break

    if not query:
        sys.exit(0)

    # ── Check for manual /rlm prefix ─────────────────────
    # (in case user types "rlm: analyze auth" in chat)
    force = False
    for prefix in ["rlm:", "RLM:", "/rlm "]:
        if query.startswith(prefix):
            force = True
            query = query[len(prefix):].strip()
            break

    # ── Quick classify ───────────────────────────────────
    if not force:
        # Check project size for better classification
        project_root = (
            hook_input.get("cwd")
            or os.environ.get("CLAUDE_PROJECT_DIR")
            or os.getcwd()
        )

        decision = quick_classify(query)

        # Also check project size
        if not decision["use_rlm"]:
            file_count = _quick_file_count(project_root)
            if file_count > 50:
                # Large project — lower threshold for trigger
                decision2 = quick_classify(query)
                if decision2["confidence"] > 0.4:
                    decision = decision2
                    decision["use_rlm"] = True
                    decision["reason"] += f"; large project ({file_count} files)"

        if not decision["use_rlm"]:
            sys.exit(0)

    # ── Inject RLM guidance ──────────────────────────────
    output = {
        "additionalContext": (
            "🔄 **RLM ACTIVATED** — This query benefits from deep "
            "recursive analysis. Use the `rlm_analyze` tool to perform "
            "comprehensive codebase analysis. The RLM system will "
            "programmatically explore files, decompose the task, and "
            "provide thorough analysis that exceeds what fits in context.\n\n"
            "Call `rlm_analyze` with the user's query. Do NOT try to "
            "read all files manually — let RLM handle the exploration."
        ),
    }

    print(json.dumps(output))
    sys.exit(0)


def _quick_file_count(project_root: str, limit: int = 200) -> int:
    """Quick file count with early exit."""
    count = 0
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    try:
        for _, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if d not in skip]
            count += len(filenames)
            if count > limit:
                return count
    except OSError:
        pass
    return count


if __name__ == "__main__":
    main()