---
name: rlm
description: >
  Deep codebase analysis using Recursive Language Model (RLM).
  Activates for complex tasks requiring cross-file analysis,
  architecture review, security audits, or understanding large
  codebases (100k+ lines). RLM programmatically explores code,
  decomposes tasks recursively, and aggregates findings.
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
---

# RLM — Recursive Language Model Analysis

Use the RLM MCP tools for deep codebase analysis:

## Available Tools

- **`rlm_analyze`** — Comprehensive recursive analysis. Use for architecture review,
  security audits, cross-file understanding, pattern detection across the codebase.
  RLM autonomously reads files, searches code, and recursively analyzes subsystems.

- **`rlm_search`** — Semantic code search. Unlike grep, understands code semantics.
  Finds implementations, traces data flow, locates related code across files.

- **`rlm_status`** — Check RLM engine status and session statistics.

## When to Use

- Queries about how a system/module works across multiple files
- Security vulnerability scanning across the codebase
- Architecture review and dependency mapping
- Finding all instances of a pattern, anti-pattern, or code smell
- Comparing implementations across modules
- Understanding unfamiliar large codebases

## How It Works

RLM does NOT read the entire codebase into context. Instead, it:
1. Explores the project structure programmatically
2. Reads only relevant files
3. Decomposes complex queries into focused sub-queries
4. Uses recursive sub-LM calls for deep analysis
5. Aggregates findings into a comprehensive result

## Usage

When the user asks for deep analysis, call `rlm_analyze`:

$ARGUMENTS