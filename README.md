# claude-code-rlm

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin that integrates
[Recursive Language Models](https://arxiv.org/abs/2512.24601) for deep analysis
of large codebases.

<!-- TODO: replace with actual demo GIF when available -->
<!-- ![demo](assets/demo.gif) -->

### Quick start

```bash
git clone https://github.com/twinkiey/claude-code-rlm.git
cd claude-code-rlm && pip install -e .
claude --plugin-dir ./claude-code-rlm
```

Then just ask Claude a complex question about your codebase — RLM activates automatically.
Or trigger manually: `/rlm analyze the authentication system`

---

## What it does

Standard Claude Code reads files into its context window. For large projects (100k+ lines),
this hits limits — context overflows, details get lost, analysis becomes shallow.

**claude-code-rlm** changes the approach: instead of stuffing code into the prompt,
it gives the model a Python REPL environment where it can *programmatically* explore
the codebase — read files, search, decompose tasks, and recursively call sub-LMs
on focused code fragments. Each individual call sees only 2-3k tokens, but the system
can process codebases of virtually unlimited size.

```
Without RLM:
  User query → [entire codebase crammed into context] → shallow answer

With RLM:
  User query → model writes code to explore project → reads relevant files →
  decomposes into sub-tasks → sub-LMs analyze fragments → aggregates → deep answer
```

## How is this different from...

| Approach | How it handles large code | Limitation |
|----------|--------------------------|------------|
| **Vanilla Claude Code** | Reads files into context window | Overflows on large projects |
| **RAG / embeddings** | Retrieves chunks by similarity | Retrieves blindly — misses context |
| **Aider / Cursor** | Whole-file or repo-map context | Still limited by context window |
| **Tree-sitter parsing** | Structural code understanding | Structure only, no semantics |
| **claude-code-rlm** | Model *programs* its own exploration | Recursive, semantic, unlimited scale |

Key difference: RLM doesn't just *retrieve* code — the model **decides** what to read,
**writes code** to process it, and **recursively delegates** sub-tasks to focused sub-LM calls.
The model acts as a programmer analyzing code, not a search engine returning chunks.

## How it works

1. You ask Claude Code a complex question about your codebase
2. A lightweight hook classifies the query using fast regex heuristics (< 1 second, no API calls)
3. If deep analysis is needed, Claude is told to use RLM tools
4. The RLM MCP server runs recursive analysis autonomously
5. Claude receives the analysis and presents the result

The plugin uses three CC extension points:
- **Hook** (`UserPromptSubmit`) — fast rule-based classification, no LLM call
- **MCP Server** — exposes `rlm_analyze` and `rlm_search` tools
- **Skill** — `/rlm` slash command for manual activation

### Architecture

```
User: "Find all security vulnerabilities"
  │
  ▼
UserPromptSubmit hook (< 1 sec)
  │ regex classification, no API call
  │
  ├── Not RLM → Claude Code as usual
  │
  └── RLM needed → inject: "use rlm_analyze tool"
        │
        ▼
  Claude calls rlm_analyze (MCP tool)
        │
        ▼
  MCP Server (python/mcp_server.py)
  ┌─────────────────────────────┐
  │ RLM.completion()            │
  │  ├── file_tree()            │ ← explore project structure
  │  ├── search_code("auth")    │ ← find relevant files
  │  ├── read_file("handler.py")│ ← read specific code
  │  ├── llm_query("analyze..") │ ← sub-LM on fragment
  │  ├── rlm_query("trace..")   │ ← recursive child RLM
  │  └── FINAL_VAR("result")    │ ← return analysis
  └─────────────────────────────┘
        │
        ▼
  Claude presents comprehensive result
```

## Installation

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) with plugin support
- Python 3.10+
- An API key for your chosen LLM provider

### Install

```bash
git clone https://github.com/twinkiey/claude-code-rlm.git
cd claude-code-rlm
pip install -e .
```

Test with Claude Code (local plugin mode):

```bash
claude --plugin-dir ./claude-code-rlm
```

### Configuration

Copy the example config to your project root:

```bash
cp .claude-rlm.example.yaml /path/to/your/project/.claude-rlm.yaml
```

At minimum, set your API key:

```yaml
backend: anthropic
backend_kwargs:
  model_name: claude-sonnet-4-20250514
  # api_key: sk-...  # Or set ANTHROPIC_API_KEY env var
```

Or just set the environment variable:

```bash
export ANTHROPIC_API_KEY=sk-...
```

### Optional: worker model

Use a cheaper model for recursive sub-calls to reduce cost:

```yaml
other_backends:
  - anthropic
other_backend_kwargs:
  - model_name: claude-haiku-4-20250514
```

## Usage

### Automatic

Just ask complex questions. The plugin auto-activates for queries like:

- *"Analyze the authentication system"*
- *"Find all security vulnerabilities"*
- *"How does the payment processing work across all modules?"*
- *"Review the entire codebase for code smells"*

Simple queries (create file, run tests, write a function) pass through
to standard Claude Code — no overhead.

### Manual

Prefix your query with `/rlm`:

```
/rlm explain the dependency graph of the auth module
```

### Configuration options

See [`.claude-rlm.example.yaml`](.claude-rlm.example.yaml) for all options.

Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `max_depth` | `2` | Recursion depth (1=flat, 2=one level, 3=deep) |
| `max_iterations` | `20` | Max REPL iterations per analysis |
| `max_timeout` | `120.0` | Seconds per analysis |
| `max_errors` | `3` | Consecutive errors before abort |
| `persistent` | `true` | Keep REPL state between queries |
| `compaction` | `true` | Auto-summarize when context fills |

## Key features explained

### Persistent REPL

With `persistent: true` (default), the REPL environment stays alive between
your queries. This means:

- Files read in query 1 are still in memory for query 2
- Variables, analysis results, and computed data persist
- Second query about the same module is faster and cheaper
- The model can say "as we found in the previous analysis..."

### Compaction

With `compaction: true` (default), when the RLM's own conversation history
fills up (lots of iterations), it automatically:

1. Asks the LLM to summarize progress so far
2. Compresses the history to `[system prompt + summary + continue]`
3. Saves full history as a `history` variable in the REPL

The model can access `history` to recover any details lost during compression.
This enables very long analysis sessions without hitting context limits — the
RLM manages its own context, so you don't have to.

### Auto-trigger classifier

The hook classifier is purely **rule-based** — regex pattern matching on the
query text. No LLM call, no API cost, no latency. It checks:

1. Bypass patterns first (create file, run tests → skip RLM)
2. Trigger patterns (analyze, refactor, entire codebase → use RLM)
3. Default: standard Claude Code

You can tune the keywords in `.claude-rlm.yaml` under `auto_trigger`.

## Security considerations

RLM executes model-generated Python code via `exec()` in the host process.
The model has **read access to your filesystem** within the project directory
(and potentially beyond, since `__import__` is available).

### Mitigations built in

- **Path validation**: `read_file()` and `write_file()` tools resolve paths
  and reject anything outside the project root
- **write_file disabled by default**: must be explicitly enabled in config
- **run_command disabled by default**: shell access requires opt-in
- **Max iterations**: prevents runaway loops between iterations
- **Max timeout**: hard time limit per analysis
- **Max budget**: optional cost cap per analysis
- **Dangerous builtins removed**: `eval`, `exec`, `compile`, `input` are
  set to `None` in the REPL sandbox

### What is NOT mitigated

- `__import__` is available — model can import `os`, `subprocess`, etc.
- `exec()` has no per-execution timeout — an infinite loop in model-generated
  code will hang until `max_timeout` is checked between iterations
- The REPL runs in the same process — no container isolation by default

### Recommendation

This plugin is designed for **local development use** on your own machine
with your own code. Do not use it:

- On production servers
- With untrusted user inputs
- On machines with sensitive data outside the project directory

For sandboxed execution, the underlying `rlms` library supports Docker,
Modal, and other isolated environments — see the
[rlms documentation](https://github.com/alexzhang13/rlm).

## Project structure

```
claude-code-rlm/
├── .claude-plugin/plugin.json   # CC plugin manifest
├── .mcp.json                    # MCP server config
├── hooks/hooks.json             # Hook definitions
├── skills/rlm/SKILL.md          # /rlm skill
├── scripts/                     # Hook handlers
│   ├── classify-hook.py         # UserPromptSubmit (fast, <1s)
│   ├── quick_classifier.py      # Regex heuristics
│   └── precompact-hook.py       # Save RLM state on compaction
├── python/                      # Core logic
│   ├── mcp_server.py            # MCP server (main integration)
│   ├── bridge.py                # RLM instance wrapper
│   ├── config.py                # Configuration loading/merging
│   ├── classifier.py            # Full heuristic classifier
│   ├── tools.py                 # Codebase tools (read, search, git)
│   ├── events.py                # Event/callback system
│   └── prompts.py               # System prompts for code analysis
├── tests/                       # Unit tests (no API needed)
└── .claude-rlm.example.yaml     # Example configuration
```

## Limitations

- **Latency**: RLM analysis takes 30-120+ seconds (multiple LLM API calls
  under the hood). Not suitable for quick questions.
- **Cost**: Recursive calls consume additional tokens. Each analysis may use
  thousands of tokens across multiple API calls. Use a cheaper worker model
  (`other_backends`) to reduce cost.
- **Code fragility**: RLM relies on the model writing syntactically correct
  Python. A bug in generated code wastes an iteration. The system retries,
  but complex tasks may hit `max_iterations`.
- **Error propagation**: A hallucination in a leaf sub-call can propagate
  up through the recursion tree. Unlike attention, each discrete sub-call
  returns a hard decision.

## Credits

This project is built on top of the **Recursive Language Models** research
and library by **Alex Zhang** (MIT CSAIL / MIT OASYS Lab):

- **Paper**: [Recursive Language Models](https://arxiv.org/abs/2512.24601)
  — Alex L. Zhang, Tim Kraska, Omar Khattab (2025)
- **Blog post**: [RLM Blogpost](https://alexzhang13.github.io/blog/2025/rlm/)
- **Python library**: [`rlms` on PyPI](https://pypi.org/project/rlms/) —
  [GitHub](https://github.com/alexzhang13/rlm)

The core inference engine, REPL environment, recursive decomposition logic,
and all RLM algorithms are entirely the work of Alex Zhang and contributors.
This plugin is a thin integration layer that connects the `rlms` library
to Claude Code's plugin system (hooks, MCP server, skills).

```bibtex
@misc{zhang2026recursivelanguagemodels,
      title={Recursive Language Models},
      author={Alex L. Zhang and Tim Kraska and Omar Khattab},
      year={2026},
      eprint={2512.24601},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2512.24601},
}
```

## Status

🚧 **Alpha** — core logic implemented, integration tested with unit tests.
End-to-end testing with Claude Code in progress. Contributions welcome.

## License

[MIT](LICENSE)
