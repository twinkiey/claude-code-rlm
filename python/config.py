"""
claude-code-rlm: Configuration system

Loads and merges configuration from:
1. Built-in defaults
2. Global config: ~/.config/claude-rlm/config.yaml
3. Project config: .claude-rlm.yaml (in project root)
4. Environment variables (ANTHROPIC_API_KEY, etc.)

Project config overrides global, which overrides defaults.
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any


# ── Defaults ──────────────────────────────────────────────

DEFAULTS = {
    # Backend (Root LM)
    "backend": "anthropic",
    "backend_kwargs": {
        "model_name": "claude-sonnet-4-20250514",
    },

    # Worker LM (for sub-calls at depth=1)
    "other_backends": None,          # e.g. ["anthropic"]
    "other_backend_kwargs": None,    # e.g. [{"model_name": "claude-haiku-4-20250514"}]

    # Environment
    "environment": "local",
    "environment_kwargs": {},

    # Recursion & iteration limits
    "max_depth": 2,
    "max_iterations": 20,

    # Resource limits
    "max_budget": None,              # USD per completion, None = unlimited
    "max_timeout": 120.0,            # seconds per completion
    "max_tokens": None,              # total tokens, None = unlimited
    "max_errors": 3,                 # consecutive REPL errors before abort

    # Features
    "persistent": True,
    "compaction": True,
    "compaction_threshold_pct": 0.80,
    "verbose": False,

    # Auto-trigger settings
    "auto_trigger": {
        "enabled": True,
        "min_context_chars": 50_000,
        "min_file_lines": 5_000,
        "min_project_files": 50,
        "trigger_keywords": [
            "analyze", "refactor", "review all", "find all bugs",
            "compare", "migrate", "audit", "optimize all",
            "across all files", "entire codebase", "every file",
            "explain the architecture", "how does the system",
            "security vulnerabilities", "dead code",
        ],
        "bypass_keywords": [
            "create file", "rename", "delete", "run tests",
            "commit", "push", "install", "write a function",
            "implement", "add method", "create class",
        ],
    },

    # Logging
    "log_dir": None,                 # None = in-memory only

    # Custom system prompt (None = use built-in CC-optimized prompt)
    "custom_system_prompt": None,

    # Tools configuration
    "tools": {
        "read_file": True,
        "write_file": False,         # Disabled by default for safety
        "run_command": False,         # Disabled by default for safety
        "search_code": True,
        "git_info": True,
        "file_tree": True,
    },
}


# ── Paths ─────────────────────────────────────────────────

GLOBAL_CONFIG_DIR = Path.home() / ".config" / "claude-rlm"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.yaml"
PROJECT_CONFIG_FILE = ".claude-rlm.yaml"


# ── Config dataclass ──────────────────────────────────────

@dataclass
class AutoTriggerConfig:
    enabled: bool = True
    min_context_chars: int = 50_000
    min_file_lines: int = 5_000
    min_project_files: int = 50
    trigger_keywords: list[str] = field(default_factory=list)
    bypass_keywords: list[str] = field(default_factory=list)


@dataclass
class ToolsConfig:
    read_file: bool = True
    write_file: bool = False
    run_command: bool = False
    search_code: bool = True
    git_info: bool = True
    file_tree: bool = True


@dataclass
class RLMConfig:
    """Complete configuration for claude-code-rlm plugin."""

    # Backend
    backend: str = "anthropic"
    backend_kwargs: dict[str, Any] = field(default_factory=dict)
    other_backends: list[str] | None = None
    other_backend_kwargs: list[dict[str, Any]] | None = None

    # Environment
    environment: str = "local"
    environment_kwargs: dict[str, Any] = field(default_factory=dict)

    # Limits
    max_depth: int = 2
    max_iterations: int = 20
    max_budget: float | None = None
    max_timeout: float = 120.0
    max_tokens: int | None = None
    max_errors: int = 3

    # Features
    persistent: bool = True
    compaction: bool = True
    compaction_threshold_pct: float = 0.80
    verbose: bool = False

    # Auto-trigger
    auto_trigger: AutoTriggerConfig = field(default_factory=AutoTriggerConfig)

    # Logging
    log_dir: str | None = None

    # Prompts
    custom_system_prompt: str | None = None

    # Tools
    tools: ToolsConfig = field(default_factory=ToolsConfig)

    # Project root (set at runtime)
    project_root: str = field(default_factory=os.getcwd)


# ── Loading & merging ─────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge override into base.
    Override values take precedence.
    """
    result = base.copy()
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> dict:
    """Load YAML file, return empty dict if not found or invalid."""
    try:
        if path.exists():
            with open(path, "r") as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
    except (yaml.YAMLError, OSError) as e:
        print(f"[claude-code-rlm] Warning: failed to load {path}: {e}")
    return {}


def _inject_env_vars(config: dict) -> dict:
    """Inject API keys from environment variables if not set in config."""

    bk = config.get("backend_kwargs", {})

    # Anthropic
    if config.get("backend") == "anthropic" and "api_key" not in bk:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            bk["api_key"] = api_key

    # OpenAI
    if config.get("backend") == "openai" and "api_key" not in bk:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            bk["api_key"] = api_key

    config["backend_kwargs"] = bk

    # Same for other_backend_kwargs
    obk_list = config.get("other_backend_kwargs")
    ob_list = config.get("other_backends")
    if obk_list and ob_list:
        for i, (backend, kwargs) in enumerate(zip(ob_list, obk_list)):
            if "api_key" not in kwargs:
                if backend == "anthropic":
                    key = os.getenv("ANTHROPIC_API_KEY")
                elif backend in ("openai", "vllm", "openrouter", "vercel"):
                    key = os.getenv("OPENAI_API_KEY")
                else:
                    key = None
                if key:
                    kwargs["api_key"] = key

    return config


def _dict_to_config(data: dict) -> RLMConfig:
    """Convert merged dict to RLMConfig dataclass."""

    # Handle nested dataclasses
    auto_trigger_data = data.pop("auto_trigger", {})
    tools_data = data.pop("tools", {})

    auto_trigger = AutoTriggerConfig(**{
        k: v for k, v in auto_trigger_data.items()
        if k in AutoTriggerConfig.__dataclass_fields__
    }) if auto_trigger_data else AutoTriggerConfig()

    tools = ToolsConfig(**{
        k: v for k, v in tools_data.items()
        if k in ToolsConfig.__dataclass_fields__
    }) if tools_data else ToolsConfig()

    # Filter to valid fields only
    valid_fields = set(RLMConfig.__dataclass_fields__.keys())
    filtered = {k: v for k, v in data.items() if k in valid_fields}

    return RLMConfig(
        **filtered,
        auto_trigger=auto_trigger,
        tools=tools,
    )


def load_config(project_root: str | None = None) -> RLMConfig:
    """
    Load configuration with priority:
    defaults < global config < project config < env vars

    Args:
        project_root: Path to project root. If None, uses cwd.

    Returns:
        Merged RLMConfig
    """
    root = Path(project_root) if project_root else Path.cwd()

    # 1. Start with defaults
    merged = DEFAULTS.copy()

    # 2. Merge global config
    global_config = _load_yaml(GLOBAL_CONFIG_FILE)
    if global_config:
        merged = _deep_merge(merged, global_config)

    # 3. Merge project config
    project_config_path = root / PROJECT_CONFIG_FILE
    project_config = _load_yaml(project_config_path)
    if project_config:
        merged = _deep_merge(merged, project_config)

    # 4. Inject environment variables
    merged = _inject_env_vars(merged)

    # 5. Set project root
    merged["project_root"] = str(root)

    # 6. Convert to dataclass
    return _dict_to_config(merged)


def create_default_config(path: Path | None = None, scope: str = "project") -> Path:
    """
    Create a default configuration file.
    """
    if path is None:
        if scope == "global":
            GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            path = GLOBAL_CONFIG_FILE
        else:
            path = Path.cwd() / PROJECT_CONFIG_FILE

    example = """# claude-code-rlm configuration
# See: https://github.com/yourname/claude-code-rlm

# -- Model Configuration --
backend: anthropic
backend_kwargs:
  model_name: claude-sonnet-4-20250514
  # api_key: sk-...  # Or set ANTHROPIC_API_KEY env var

# Worker model for sub-calls (optional, saves cost)
# other_backends:
#   - anthropic
# other_backend_kwargs:
#   - model_name: claude-haiku-4-20250514

# -- Limits --
max_depth: 2          # Recursion depth (1=no recursion, 2=one level, 3=two levels)
max_iterations: 20    # Max REPL iterations per completion
max_timeout: 120.0    # Seconds per completion
max_errors: 3         # Consecutive REPL errors before abort
# max_budget: 0.50    # USD per completion (requires cost-tracking backend)
# max_tokens: null    # Total token limit

# -- Features --
persistent: true      # Reuse REPL between queries (preserves variables)
compaction: true      # Auto-summarize history when context fills up
compaction_threshold_pct: 0.80
verbose: false        # Rich console output for debugging

# -- Auto-trigger --
# When to automatically use RLM instead of standard CC
auto_trigger:
  enabled: true
  min_context_chars: 50000   # Context larger than this -> RLM
  min_file_lines: 5000       # File with more lines than this -> RLM
  min_project_files: 50      # Projects with more files -> RLM
  trigger_keywords:
    - analyze
    - refactor
    - review all
    - find all bugs
    - entire codebase
    - security vulnerabilities
  bypass_keywords:
    - create file
    - rename
    - run tests
    - commit
    - write a function

# -- Tools --
# Which tools are available to RLM in the REPL
tools:
  read_file: true      # Read project files
  write_file: false     # Write files (disabled for safety)
  run_command: false    # Shell commands (disabled for safety)
  search_code: true     # Grep across codebase
  git_info: true        # Git log, diff, blame
  file_tree: true       # Project file tree

# -- Logging --
# log_dir: ~/.config/claude-rlm/logs  # Save trajectories for debugging
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(example)

    return path
