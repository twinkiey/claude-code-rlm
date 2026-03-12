"""Tests for python/config.py — configuration loading and merging."""

import os
import json
from pathlib import Path

import pytest
import yaml

# Import after path setup
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python.config import (
    load_config,
    create_default_config,
    RLMConfig,
    AutoTriggerConfig,
    ToolsConfig,
    DEFAULTS,
    _deep_merge,
    _inject_env_vars,
    _load_yaml,
)


class TestDeepMerge:
    """Test the recursive dict merge function."""

    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 99, "z": 100}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 99, "z": 100}, "b": 3}

    def test_override_replaces_non_dict(self):
        base = {"a": {"x": 1}}
        override = {"a": "string_value"}
        result = _deep_merge(base, override)
        assert result == {"a": "string_value"}

    def test_empty_override(self):
        base = {"a": 1, "b": 2}
        result = _deep_merge(base, {})
        assert result == base

    def test_empty_base(self):
        override = {"a": 1}
        result = _deep_merge({}, override)
        assert result == override

    def test_original_not_mutated(self):
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        _deep_merge(base, override)
        assert base == {"a": {"x": 1}}


class TestLoadYaml:
    """Test YAML file loading."""

    def test_load_valid_yaml(self, tmp_dir: Path):
        f = tmp_dir / "test.yaml"
        f.write_text("key: value\nnested:\n  a: 1\n")
        result = _load_yaml(f)
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_load_nonexistent(self, tmp_dir: Path):
        result = _load_yaml(tmp_dir / "nonexistent.yaml")
        assert result == {}

    def test_load_empty_file(self, tmp_dir: Path):
        f = tmp_dir / "empty.yaml"
        f.write_text("")
        result = _load_yaml(f)
        assert result == {}

    def test_load_invalid_yaml(self, tmp_dir: Path):
        f = tmp_dir / "bad.yaml"
        f.write_text("{{invalid yaml::")
        result = _load_yaml(f)
        assert result == {}

    def test_load_non_dict_yaml(self, tmp_dir: Path):
        f = tmp_dir / "list.yaml"
        f.write_text("- item1\n- item2\n")
        result = _load_yaml(f)
        assert result == {}


class TestInjectEnvVars:
    """Test API key injection from environment variables."""

    def test_inject_anthropic_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        config = {"backend": "anthropic", "backend_kwargs": {}}
        result = _inject_env_vars(config)
        assert result["backend_kwargs"]["api_key"] == "sk-ant-test"

    def test_inject_openai_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
        config = {"backend": "openai", "backend_kwargs": {}}
        result = _inject_env_vars(config)
        assert result["backend_kwargs"]["api_key"] == "sk-oai-test"

    def test_no_override_existing_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
        config = {
            "backend": "anthropic",
            "backend_kwargs": {"api_key": "sk-explicit"},
        }
        result = _inject_env_vars(config)
        assert result["backend_kwargs"]["api_key"] == "sk-explicit"

    def test_no_env_var(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = {"backend": "anthropic", "backend_kwargs": {}}
        result = _inject_env_vars(config)
        assert "api_key" not in result["backend_kwargs"]

    def test_inject_other_backend_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
        config = {
            "backend": "anthropic",
            "backend_kwargs": {"api_key": "sk-ant"},
            "other_backends": ["openai"],
            "other_backend_kwargs": [{"model_name": "gpt-4o-mini"}],
        }
        result = _inject_env_vars(config)
        assert result["other_backend_kwargs"][0]["api_key"] == "sk-oai"


class TestLoadConfig:
    """Test full configuration loading pipeline."""

    def test_defaults_loaded(self, tmp_dir: Path, global_config_dir):
        """Config loads with sane defaults when no files exist."""
        config = load_config(project_root=str(tmp_dir))
        assert config.backend == "anthropic"
        assert config.max_depth == 2
        assert config.max_iterations == 20
        assert config.persistent is True
        assert config.compaction is True
        assert config.auto_trigger.enabled is True

    def test_project_config_overrides(
        self, sample_config_yaml, global_config_dir
    ):
        """Project config overrides defaults."""
        project_dir = sample_config_yaml.parent
        config = load_config(project_root=str(project_dir))
        assert config.max_depth == 3
        assert config.max_iterations == 10
        assert config.max_timeout == 60.0
        assert config.tools.write_file is True
        assert config.tools.run_command is False

    def test_global_config(self, tmp_dir: Path, global_config_dir: Path):
        """Global config loaded when no project config."""
        global_file = global_config_dir / "config.yaml"
        global_file.write_text("max_depth: 5\nverbose: true\n")

        config = load_config(project_root=str(tmp_dir))
        assert config.max_depth == 5
        assert config.verbose is True

    def test_project_overrides_global(
        self, tmp_dir: Path, global_config_dir: Path
    ):
        """Project config takes priority over global."""
        global_file = global_config_dir / "config.yaml"
        global_file.write_text("max_depth: 5\nmax_iterations: 50\n")

        project_config = tmp_dir / ".claude-rlm.yaml"
        project_config.write_text("max_depth: 2\n")

        config = load_config(project_root=str(tmp_dir))
        assert config.max_depth == 2        # project wins
        assert config.max_iterations == 50  # global still applies

    def test_project_root_set(self, tmp_dir: Path, global_config_dir):
        config = load_config(project_root=str(tmp_dir))
        assert config.project_root == str(tmp_dir)

    def test_auto_trigger_config(self, tmp_dir: Path, global_config_dir):
        (tmp_dir / ".claude-rlm.yaml").write_text("""
auto_trigger:
  enabled: false
  min_context_chars: 100000
""")
        config = load_config(project_root=str(tmp_dir))
        assert config.auto_trigger.enabled is False
        assert config.auto_trigger.min_context_chars == 100000

    def test_tools_config(self, tmp_dir: Path, global_config_dir):
        (tmp_dir / ".claude-rlm.yaml").write_text("""
tools:
  write_file: true
  run_command: true
""")
        config = load_config(project_root=str(tmp_dir))
        assert config.tools.write_file is True
        assert config.tools.run_command is True
        assert config.tools.read_file is True  # default


class TestCreateDefaultConfig:
    """Test default config file creation."""

    def test_create_project_config(self, tmp_dir: Path):
        path = create_default_config(
            path=tmp_dir / ".claude-rlm.yaml",
            scope="project",
        )
        assert path.exists()
        content = path.read_text()
        assert "backend:" in content
        assert "max_depth:" in content
        assert "auto_trigger:" in content

    def test_created_config_is_valid_yaml(self, tmp_dir: Path):
        path = create_default_config(path=tmp_dir / "test.yaml")
        data = yaml.safe_load(path.read_text())
        assert isinstance(data, dict)


class TestInjectEnvVarsLengthMismatch:
    """Test that mismatched other_backends / other_backend_kwargs warns."""

    def test_mismatched_lengths_warn(self, monkeypatch, capsys):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
        config = {
            "backend": "anthropic",
            "backend_kwargs": {},
            "other_backends": ["openai", "openai"],  # 2 backends
            "other_backend_kwargs": [{"model_name": "gpt-4o"}],  # 1 kwargs
        }
        _inject_env_vars(config)
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "other_backends" in captured.out

    def test_matching_lengths_no_warn(self, monkeypatch, capsys):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
        config = {
            "backend": "anthropic",
            "backend_kwargs": {},
            "other_backends": ["openai"],
            "other_backend_kwargs": [{"model_name": "gpt-4o"}],
        }
        _inject_env_vars(config)
        captured = capsys.readouterr()
        assert "Warning" not in captured.out


class TestDictToConfigNoMutation:
    """Test that _dict_to_config does not mutate its input."""

    def test_input_not_mutated(self):
        from python.config import _dict_to_config, DEFAULTS
        import copy

        data = copy.deepcopy(DEFAULTS)
        data["project_root"] = "/tmp/test"
        original_keys = set(data.keys())

        _dict_to_config(data)

        # Original dict should be unchanged
        assert set(data.keys()) == original_keys
        assert "auto_trigger" in data
        assert "tools" in data


class TestRLMConfig:
    """Test RLMConfig dataclass."""

    def test_default_values(self):
        config = RLMConfig()
        assert config.backend == "anthropic"
        assert config.max_depth == 2
        assert config.other_backends is None
        assert config.max_budget is None
        assert isinstance(config.auto_trigger, AutoTriggerConfig)
        assert isinstance(config.tools, ToolsConfig)

    def test_tools_defaults(self):
        tools = ToolsConfig()
        assert tools.read_file is True
        assert tools.write_file is False  # safety
        assert tools.run_command is False  # safety
        assert tools.search_code is True
        assert tools.git_info is True
        assert tools.file_tree is True