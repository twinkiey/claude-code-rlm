#!/usr/bin/env python3
"""
claude-code-rlm: Quick classifier (runs without bridge)

Lightweight heuristic classification that runs in-process
to avoid the overhead of starting/connecting to the bridge
for queries that obviously don't need RLM.
"""

import re


# Keywords that suggest RLM is needed
TRIGGER_KEYWORDS = [
    # Analysis patterns
    r"\banalyz\w*\b",
    r"\breview\s+all\b",
    r"\baudit\b",
    r"\bfind\s+all\s+bugs?\b",
    r"\bsecurity\s+vulnerabilit\w*\b",
    r"\bdead\s+code\b",
    r"\bcode\s+smell\w*\b",
    r"\btechnical\s+debt\b",

    # Scope patterns
    r"\bentire\s+codebase\b",
    r"\bacross\s+all\s+files?\b",
    r"\bevery\s+file\b",
    r"\bwhole\s+project\b",
    r"\ball\s+modules?\b",
    r"\bfull\s+project\b",

    # Architecture patterns
    r"\barchitecture\b",
    r"\bsystem\s+design\b",
    r"\bhow\s+does\s+.+\s+work\b",
    r"\bexplain\s+the\s+.+\s+system\b",
    r"\bdependency\s+(graph|tree|chain)\b",
    r"\bcall\s+(graph|chain|flow)\b",

    # Refactoring patterns
    r"\brefactor\b",
    r"\bmigrat\w+\b",
    r"\boptimize\s+all\b",
    r"\brestructur\w+\b",

    # Comparison patterns
    r"\bcompare\s+(all|across|between)\b",
    r"\binconsistenc\w*\b",
    r"\bduplicate\s+code\b",

    # Computation patterns
    r"\bcount\s+(all|lines|files|functions|classes)\b",
    r"\bstatistics\b",
    r"\bbenchmark\b",
    r"\bmetrics?\b",
]

# Keywords that suggest RLM is NOT needed
BYPASS_KEYWORDS = [
    r"\bcreate\s+(a\s+)?file\b",
    r"\brename\b",
    r"\bdelete\b",
    r"\brun\s+tests?\b",
    r"\bcommit\b",
    r"\bpush\b",
    r"\binstall\b",
    r"\bwrite\s+(a\s+)?function\b",
    r"\bimplement\s+(a\s+)?\w+\b",
    r"\badd\s+(a\s+)?method\b",
    r"\bcreate\s+(a\s+)?class\b",
    r"\bboilerplate\b",
    r"\bgenerate\b",
    r"\bfix\s+this\b",
    r"\bupdate\s+this\b",
]

# Compile patterns once
_TRIGGER_PATTERNS = [re.compile(p, re.IGNORECASE) for p in TRIGGER_KEYWORDS]
_BYPASS_PATTERNS = [re.compile(p, re.IGNORECASE) for p in BYPASS_KEYWORDS]


def quick_classify(query: str) -> dict:
    """
    Quick heuristic classification without bridge.

    Returns:
        {"use_rlm": bool, "reason": str, "confidence": float}
    """
    if not query or len(query.strip()) < 10:
        return {
            "use_rlm": False,
            "reason": "query too short",
            "confidence": 0.9,
        }

    # Check bypass first
    for pattern in _BYPASS_PATTERNS:
        match = pattern.search(query)
        if match:
            return {
                "use_rlm": False,
                "reason": f"bypass pattern: '{match.group()}'",
                "confidence": 0.8,
            }

    # Check triggers
    matches = []
    for pattern in _TRIGGER_PATTERNS:
        match = pattern.search(query)
        if match:
            matches.append(match.group())

    if matches:
        # More matches = higher confidence
        confidence = min(0.6 + len(matches) * 0.1, 0.95)
        return {
            "use_rlm": True,
            "reason": f"trigger patterns: {matches[:5]}",
            "confidence": confidence,
        }

    # No triggers, no bypasses — default to not using RLM
    return {
        "use_rlm": False,
        "reason": "no triggers matched",
        "confidence": 0.5,
    }