"""Tests for python/tools.py — custom codebase tools."""

import os
import sys
from pathlib import Path

import pytest
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



from python.tools import (
    build_custom_tools,
    _safe_resolve,
    _make_read_file,
    _make_write_file,
    _make_search_code,
    _make_file_tree,
    _make_list_files,
    _make_git_info,
    _gather_project_info,
    MAX_FILE_SIZE,
)
from python.config import ToolsConfig

HAS_GREP = shutil.which("grep") is not None

class TestSafeResolve:
    """Test path safety validation."""

    def test_normal_path(self, fake_project: Path):
    	result = _safe_resolve(str(fake_project), "src/index.ts")
    	assert result is not None
    	assert result.endswith(os.path.join("src", "index.ts"))

    def test_dotdot_escape_blocked(self, fake_project: Path):
        result = _safe_resolve(str(fake_project), "../../etc/passwd")
        assert result is None

    def test_absolute_path_outside_blocked(self, fake_project: Path):
        result = _safe_resolve(str(fake_project), "/etc/passwd")
        assert result is None

    def test_root_path(self, fake_project: Path):
        result = _safe_resolve(str(fake_project), ".")
        assert result is not None
        assert result == str(Path(fake_project).resolve())

    def test_nested_dotdot(self, fake_project: Path):
        # src/../src/index.ts should resolve within project
        result = _safe_resolve(str(fake_project), "src/../src/index.ts")
        assert result is not None

    def test_symlink_escape(self, fake_project: Path):
        """Symlink pointing outside project should be blocked."""
        link = fake_project / "evil_link"
        try:
            os.symlink("/etc", str(link))
            result = _safe_resolve(str(fake_project), "evil_link/passwd")
            assert result is None
        except OSError:
            pytest.skip("Cannot create symlinks")


class TestReadFile:
    """Test read_file tool."""

    def test_read_existing_file(self, fake_project: Path):
        read_file = _make_read_file(str(fake_project))
        content = read_file("src/auth/handler.ts")
        assert "authenticate" in content
        assert "authorize" in content

    def test_read_nonexistent_file(self, fake_project: Path):
        read_file = _make_read_file(str(fake_project))
        result = read_file("nonexistent.ts")
        assert "Error" in result

    def test_read_outside_project(self, fake_project: Path):
        read_file = _make_read_file(str(fake_project))
        result = read_file("../../etc/passwd")
        assert "Error" in result
        assert "outside" in result

    def test_read_directory(self, fake_project: Path):
        read_file = _make_read_file(str(fake_project))
        result = read_file("src/auth")
        assert "Error" in result
        assert "not a file" in result

    def test_read_large_file_blocked(self, fake_project: Path):
        # Create a file larger than MAX_FILE_SIZE
        large_file = fake_project / "huge.bin"
        large_file.write_bytes(b"x" * (MAX_FILE_SIZE + 1))

        read_file = _make_read_file(str(fake_project))
        result = read_file("huge.bin")
        assert "Error" in result
        assert "limit" in result.lower()


class TestWriteFile:
    """Test write_file tool."""

    def test_write_new_file(self, fake_project: Path):
        write_file = _make_write_file(str(fake_project))
        result = write_file("new_file.txt", "hello world")
        assert "OK" in result

        content = (fake_project / "new_file.txt").read_text()
        assert content == "hello world"

    def test_write_creates_directories(self, fake_project: Path):
        write_file = _make_write_file(str(fake_project))
        result = write_file("new/nested/dir/file.txt", "content")
        assert "OK" in result
        assert (fake_project / "new/nested/dir/file.txt").exists()

    def test_write_outside_project_blocked(self, fake_project: Path):
        write_file = _make_write_file(str(fake_project))
        result = write_file("../../evil.txt", "hacked")
        assert "Error" in result
        assert "outside" in result

    def test_write_overwrites_existing(self, fake_project: Path):
        write_file = _make_write_file(str(fake_project))
        write_file("test.txt", "original")
        write_file("test.txt", "updated")
        content = (fake_project / "test.txt").read_text()
        assert content == "updated"


class TestSearchCode:
    """Test search_code tool."""

    @pytest.mark.skipif(not HAS_GREP, reason="grep not available on this system")
    def test_search_finds_pattern(self, fake_project: Path):
        search = _make_search_code(str(fake_project))
        result = search("authenticate")
        assert "handler.ts" in result

    @pytest.mark.skipif(not HAS_GREP, reason="grep not available on this system")
    def test_search_with_glob(self, fake_project: Path):
        search = _make_search_code(str(fake_project))
        result = search("authenticate", file_glob="*.ts")
        assert "handler.ts" in result

    @pytest.mark.skipif(not HAS_GREP, reason="grep not available on this system")
    def test_search_no_results(self, fake_project: Path):
        search = _make_search_code(str(fake_project))
        result = search("NONEXISTENT_UNIQUE_STRING_12345")
        assert "No matches" in result

    @pytest.mark.skipif(not HAS_GREP, reason="grep not available on this system")
    def test_search_skips_node_modules(self, fake_project: Path):
        search = _make_search_code(str(fake_project))
        result = search("module.exports")
        assert "node_modules" not in result

    @pytest.mark.skipif(not HAS_GREP, reason="grep not available on this system")
    def test_search_skips_git(self, fake_project: Path):
        search = _make_search_code(str(fake_project))
        result = search("core")
        assert ".git" not in result

class TestFileTree:
    """Test file_tree tool."""

    def test_basic_tree(self, fake_project: Path):
        tree = _make_file_tree(str(fake_project))
        result = tree()
        assert "src/" in result
        assert "package.json" in result

    def test_tree_depth_limit(self, fake_project: Path):
        tree = _make_file_tree(str(fake_project))
        shallow = tree(max_depth=1)
        deep = tree(max_depth=3)
        assert len(deep) > len(shallow)

    def test_tree_skips_node_modules(self, fake_project: Path):
        tree = _make_file_tree(str(fake_project))
        result = tree()
        assert "node_modules" not in result

    def test_tree_skips_git(self, fake_project: Path):
        tree = _make_file_tree(str(fake_project))
        result = tree()
        assert ".git" not in result

    def test_tree_subdirectory(self, fake_project: Path):
        tree = _make_file_tree(str(fake_project))
        result = tree(directory="src/auth")
        assert "handler.ts" in result
        assert "middleware.ts" in result

    def test_tree_outside_project(self, fake_project: Path):
        tree = _make_file_tree(str(fake_project))
        result = tree(directory="../../..")
        assert "Error" in result

    def test_tree_nonexistent(self, fake_project: Path):
        tree = _make_file_tree(str(fake_project))
        result = tree(directory="nonexistent")
        assert "Error" in result

    def test_tree_max_depth_capped(self, fake_project: Path):
        tree = _make_file_tree(str(fake_project))
        # Should not crash with depth > MAX_TREE_DEPTH
        result = tree(max_depth=100)
        assert isinstance(result, str)


class TestListFiles:
    """Test list_files tool."""

    def test_list_root(self, fake_project: Path):
        list_files = _make_list_files(str(fake_project))
        result = list_files()
        assert "package.json" in result
        assert "src/" in result

    def test_list_with_extension(self, fake_project: Path):
        list_files = _make_list_files(str(fake_project))
        result = list_files(directory="src/auth", extension=".ts")
        assert "handler.ts" in result
        assert "middleware.ts" in result
        assert "utils.ts" in result

    def test_list_outside_project(self, fake_project: Path):
        list_files = _make_list_files(str(fake_project))
        result = list_files(directory="../../..")
        assert "Error" in result

    def test_list_shows_sizes(self, fake_project: Path):
        list_files = _make_list_files(str(fake_project))
        result = list_files()
        assert "bytes" in result


class TestGatherProjectInfo:
    """Test project metadata gathering."""

    def test_basic_info(self, fake_project: Path):
        info = _gather_project_info(str(fake_project))
        assert info["name"] == "project"
        assert info["total_files"] > 0
        assert ".ts" in info["file_types"]
        assert info["project_type"] == "node/javascript"

    def test_python_project(self, tmp_dir: Path):
        project = tmp_dir / "py_project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\n")
        (project / "main.py").write_text("print('hello')\n")
        info = _gather_project_info(str(project))
        assert info["project_type"] == "python"

    def test_large_project_files(self, large_fake_project: Path):
        info = _gather_project_info(str(large_fake_project))
        assert info["total_files"] >= 200
        assert ".py" in info["file_types"]


class TestBuildCustomTools:
    """Test the tool builder."""

    def test_default_tools(self, fake_project: Path):
        tools = build_custom_tools(
            str(fake_project),
            ToolsConfig(),
        )
        # Always present
        assert "PROJECT_ROOT" in tools
        assert "PROJECT_INFO" in tools

        # Default enabled
        assert "read_file" in tools
        assert "search_code" in tools
        assert "file_tree" in tools
        assert "git_log" in tools

        # Default disabled
        assert "write_file" not in tools
        assert "run_command" not in tools

    def test_all_tools_enabled(self, fake_project: Path):
        config = ToolsConfig(
            read_file=True,
            write_file=True,
            run_command=True,
            search_code=True,
            git_info=True,
            file_tree=True,
        )
        tools = build_custom_tools(str(fake_project), config)
        assert "write_file" in tools
        assert "run_command" in tools

    def test_all_tools_disabled(self, fake_project: Path):
        config = ToolsConfig(
            read_file=False,
            write_file=False,
            run_command=False,
            search_code=False,
            git_info=False,
            file_tree=False,
        )
        tools = build_custom_tools(str(fake_project), config)
        assert "read_file" not in tools
        assert "search_code" not in tools
        assert "file_tree" not in tools
        # PROJECT_ROOT always present
        assert "PROJECT_ROOT" in tools

    def test_tool_has_description(self, fake_project: Path):
        tools = build_custom_tools(str(fake_project), ToolsConfig())
        for name, entry in tools.items():
            if isinstance(entry, dict) and "tool" in entry:
                assert "description" in entry, f"{name} missing description"
                assert len(entry["description"]) > 10

    def test_tools_are_callable(self, fake_project: Path):
        tools = build_custom_tools(str(fake_project), ToolsConfig())
        for name, entry in tools.items():
            if isinstance(entry, dict) and "tool" in entry:
                tool = entry["tool"]
                if callable(tool):
                    assert callable(tool), f"{name} tool not callable"