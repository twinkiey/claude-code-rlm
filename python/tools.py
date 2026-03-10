"""
claude-code-rlm: Custom tools for codebase interaction

These tools are injected into the RLM REPL environment,
allowing the model to programmatically explore and analyze
the project's codebase.
"""

import os
import subprocess
from pathlib import Path
from typing import Any

from .config import ToolsConfig


# ── Safety limits ─────────────────────────────────────────

MAX_FILE_SIZE = 1_000_000        # 1MB max file read
MAX_COMMAND_TIMEOUT = 30         # seconds
MAX_TREE_DEPTH = 6
MAX_SEARCH_RESULTS = 500
MAX_GIT_LOG_ENTRIES = 50


# ── Tool implementations ─────────────────────────────────

def _make_read_file(project_root: str):
    """Create a read_file tool bound to project root."""

    def read_file(path: str) -> str:
        """Read file content by path (relative to project root)."""
        # Resolve and validate path
        full_path = _safe_resolve(project_root, path)
        if full_path is None:
            return f"Error: path '{path}' is outside project root"

        if not os.path.isfile(full_path):
            return f"Error: '{path}' is not a file or does not exist"

        size = os.path.getsize(full_path)
        if size > MAX_FILE_SIZE:
            return (
                f"Error: file '{path}' is {size:,} bytes "
                f"(limit: {MAX_FILE_SIZE:,}). "
                f"Use search_code() to find specific content."
            )

        try:
            with open(full_path, "r", errors="replace") as f:
                content = f.read()
            return content
        except Exception as e:
            return f"Error reading '{path}': {e}"

    return read_file


def _make_write_file(project_root: str):
    """Create a write_file tool bound to project root."""

    def write_file(path: str, content: str) -> str:
        """Write content to a file (relative to project root)."""
        full_path = _safe_resolve(project_root, path)
        if full_path is None:
            return f"Error: path '{path}' is outside project root"

        try:
            # Create parent directories if needed
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            return f"OK: written {len(content):,} chars to {path}"
        except Exception as e:
            return f"Error writing '{path}': {e}"

    return write_file


def _make_search_code(project_root: str):
    """Create a search_code tool bound to project root."""

    def search_code(
        pattern: str,
        file_glob: str = "",
        max_results: int = MAX_SEARCH_RESULTS,
    ) -> str:
        """
        Search for pattern across project files using grep.

        Args:
            pattern: regex pattern to search for
            file_glob: optional file filter (e.g. '*.py', '*.ts')
            max_results: max number of results to return

        Returns:
            Matching lines with file:line_number:content format
        """
        cmd = ["grep", "-rn", "--binary-files=without-match"]

        if file_glob:
            cmd.extend(["--include", file_glob])

        # Exclude common non-code directories
        for exclude in [
            ".git", "node_modules", "__pycache__", ".venv",
            "venv", "dist", "build", ".next", "coverage",
            ".mypy_cache", ".pytest_cache", ".ruff_cache",
        ]:
            cmd.extend(["--exclude-dir", exclude])

        cmd.extend([pattern, "."])

        try:
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=MAX_COMMAND_TIMEOUT,
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) > max_results:
                return (
                    "\n".join(lines[:max_results])
                    + f"\n\n... [{len(lines) - max_results} more results truncated]"
                )
            return result.stdout.strip() or "No matches found."
        except subprocess.TimeoutExpired:
            return f"Error: search timed out after {MAX_COMMAND_TIMEOUT}s"
        except Exception as e:
            return f"Error searching: {e}"

    return search_code


def _make_file_tree(project_root: str):
    """Create a file_tree tool bound to project root."""

    def file_tree(
        directory: str = ".",
        max_depth: int = 3,
        show_hidden: bool = False,
    ) -> str:
        """
        Get project file tree as a string.

        Args:
            directory: starting directory (relative to project root)
            max_depth: how deep to traverse (1-6)
            show_hidden: include hidden files/dirs
        """
        max_depth = min(max_depth, MAX_TREE_DEPTH)

        full_path = _safe_resolve(project_root, directory)
        if full_path is None:
            return f"Error: path '{directory}' is outside project root"

        if not os.path.isdir(full_path):
            return f"Error: '{directory}' is not a directory"

        # Directories to skip
        skip_dirs = {
            ".git", "node_modules", "__pycache__", ".venv",
            "venv", "dist", "build", ".next", ".mypy_cache",
            ".pytest_cache", ".ruff_cache", "coverage",
            ".tox", ".eggs", "*.egg-info",
        }

        lines = []
        _build_tree(full_path, "", max_depth, 0, show_hidden, skip_dirs, lines)

        if not lines:
            return "(empty directory)"

        return "\n".join(lines)

    return file_tree


def _build_tree(
    path: str,
    prefix: str,
    max_depth: int,
    current_depth: int,
    show_hidden: bool,
    skip_dirs: set[str],
    lines: list[str],
):
    """Recursively build a file tree string."""
    if current_depth >= max_depth:
        return

    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        lines.append(f"{prefix}[permission denied]")
        return

    # Filter hidden files
    if not show_hidden:
        entries = [e for e in entries if not e.startswith(".")]

    # Filter skip directories
    entries = [e for e in entries if e not in skip_dirs]

    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        child_prefix = "    " if is_last else "│   "

        full_entry = os.path.join(path, entry)

        if os.path.isdir(full_entry):
            lines.append(f"{prefix}{connector}{entry}/")
            _build_tree(
                full_entry,
                prefix + child_prefix,
                max_depth,
                current_depth + 1,
                show_hidden,
                skip_dirs,
                lines,
            )
        else:
            lines.append(f"{prefix}{connector}{entry}")


def _make_run_command(project_root: str):
    """Create a run_command tool bound to project root."""

    def run_command(cmd: str) -> str:
        """
        Run a shell command in the project root directory.

        Args:
            cmd: shell command string

        Returns:
            stdout + stderr output
        """
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=MAX_COMMAND_TIMEOUT,
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {MAX_COMMAND_TIMEOUT}s"
        except Exception as e:
            return f"Error running command: {e}"

    return run_command


def _make_git_info(project_root: str):
    """Create git info tools bound to project root."""

    def git_log(n: int = 20) -> str:
        """Get recent git commits. Args: n = number of commits."""
        n = min(n, MAX_GIT_LOG_ENTRIES)
        return _run_git(project_root, f"log --oneline -n {n}")

    def git_diff(staged: bool = False) -> str:
        """Get current git diff. Args: staged = show staged changes."""
        cmd = "diff --staged" if staged else "diff"
        return _run_git(project_root, cmd)

    def git_blame(path: str, start: int = 1, end: int | None = None) -> str:
        """
        Git blame for a file.
        Args: path, start line, end line (None = entire file).
        """
        full_path = _safe_resolve(project_root, path)
        if full_path is None:
            return f"Error: path '{path}' is outside project root"

        cmd = f"blame {path}"
        if end:
            cmd += f" -L {start},{end}"
        return _run_git(project_root, cmd)

    def git_branch() -> str:
        """Get current branch and list of branches."""
        current = _run_git(project_root, "branch --show-current")
        all_branches = _run_git(project_root, "branch -a")
        return f"Current: {current}\n\nAll branches:\n{all_branches}"

    return {
        "git_log": git_log,
        "git_diff": git_diff,
        "git_blame": git_blame,
        "git_branch": git_branch,
    }


def _make_list_files(project_root: str):
    """Create a list_files tool bound to project root."""

    def list_files(
        directory: str = ".",
        extension: str = "",
    ) -> str:
        """
        List files in a directory.

        Args:
            directory: relative path from project root
            extension: filter by extension (e.g. '.py', '.ts')
        """
        full_path = _safe_resolve(project_root, directory)
        if full_path is None:
            return f"Error: path '{directory}' is outside project root"

        if not os.path.isdir(full_path):
            return f"Error: '{directory}' is not a directory"

        try:
            entries = sorted(os.listdir(full_path))
            if extension:
                entries = [e for e in entries if e.endswith(extension)]

            result = []
            for e in entries:
                ep = os.path.join(full_path, e)
                if os.path.isdir(ep):
                    result.append(f"  [dir]  {e}/")
                else:
                    size = os.path.getsize(ep)
                    result.append(f"  [file] {e} ({size:,} bytes)")

            return "\n".join(result) or "(empty)"
        except Exception as e:
            return f"Error listing '{directory}': {e}"

    return list_files


# ── Path safety ───────────────────────────────────────────

def _safe_resolve(project_root: str, relative_path: str) -> str | None:
    """
    Resolve a path and verify it's within project root.
    Returns full path or None if outside project root.
    """
    try:
        root = os.path.realpath(project_root)
        full = os.path.realpath(os.path.join(root, relative_path))

        # Security check: resolved path must be within project root
        if not full.startswith(root + os.sep) and full != root:
            return None

        return full
    except (ValueError, OSError):
        return None


def _run_git(project_root: str, cmd: str) -> str:
    """Run a git command in project root."""
    try:
        result = subprocess.run(
            f"git {cmd}",
            shell=True,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=MAX_COMMAND_TIMEOUT,
        )
        if result.returncode != 0 and result.stderr:
            return f"Error: {result.stderr.strip()}"
        return result.stdout.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: git command timed out"
    except Exception as e:
        return f"Error: {e}"


# ── Tool builder ──────────────────────────────────────────

def build_custom_tools(
    project_root: str,
    tools_config: ToolsConfig,
) -> dict[str, Any]:
    """
    Build the custom_tools dict for RLM based on configuration.

    Args:
        project_root: absolute path to project root
        tools_config: which tools are enabled

    Returns:
        dict compatible with RLM(custom_tools=...)
    """
    tools: dict[str, Any] = {}

    # Always inject project metadata as non-callable (→ locals)
    tools["PROJECT_ROOT"] = project_root

    project_info = _gather_project_info(project_root)
    tools["PROJECT_INFO"] = {
        "tool": project_info,
        "description": (
            "Project metadata: languages, file count, "
            "total lines, entry points, etc."
        ),
    }

    if tools_config.read_file:
        tools["read_file"] = {
            "tool": _make_read_file(project_root),
            "description": (
                "Read file content by relative path. "
                "Args: path (str). Returns file content or error."
            ),
        }

    if tools_config.write_file:
        tools["write_file"] = {
            "tool": _make_write_file(project_root),
            "description": (
                "Write content to a file by relative path. "
                "Args: path (str), content (str). Returns status."
            ),
        }

    if tools_config.search_code:
        tools["search_code"] = {
            "tool": _make_search_code(project_root),
            "description": (
                "Search for regex pattern across project files. "
                "Args: pattern (str), file_glob (str, optional, e.g. '*.py'), "
                "max_results (int, optional, default 500). "
                "Returns file:line:content matches."
            ),
        }

        tools["list_files"] = {
            "tool": _make_list_files(project_root),
            "description": (
                "List files in directory. "
                "Args: directory (str, default '.'), "
                "extension (str, optional, e.g. '.py'). "
                "Returns list with sizes."
            ),
        }

    if tools_config.file_tree:
        tools["file_tree"] = {
            "tool": _make_file_tree(project_root),
            "description": (
                "Get project file tree. "
                "Args: directory (str, default '.'), "
                "max_depth (int, 1-6, default 3), "
                "show_hidden (bool, default False)."
            ),
        }

    if tools_config.run_command:
        tools["run_command"] = {
            "tool": _make_run_command(project_root),
            "description": (
                "Run shell command in project root. "
                "Args: cmd (str). Returns stdout+stderr. "
                f"Timeout: {MAX_COMMAND_TIMEOUT}s."
            ),
        }

    if tools_config.git_info:
        git_tools = _make_git_info(project_root)
        tools["git_log"] = {
            "tool": git_tools["git_log"],
            "description": (
                "Get recent git commits. "
                "Args: n (int, default 20). Returns oneline log."
            ),
        }
        tools["git_diff"] = {
            "tool": git_tools["git_diff"],
            "description": (
                "Get current git diff. "
                "Args: staged (bool, default False)."
            ),
        }
        tools["git_blame"] = {
            "tool": git_tools["git_blame"],
            "description": (
                "Git blame for a file. "
                "Args: path (str), start (int), end (int|None)."
            ),
        }
        tools["git_branch"] = {
            "tool": git_tools["git_branch"],
            "description": "Get current and all git branches.",
        }

    return tools


def _gather_project_info(project_root: str) -> dict:
    """Gather basic project metadata."""
    info = {
        "root": project_root,
        "name": os.path.basename(project_root),
    }

    # Count files by extension
    ext_counts: dict[str, int] = {}
    total_files = 0

    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv",
        "venv", "dist", "build", ".next",
    }

    for dirpath, dirnames, filenames in os.walk(project_root):
        # Skip excluded directories
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        for f in filenames:
            total_files += 1
            ext = os.path.splitext(f)[1].lower()
            if ext:
                ext_counts[ext] = ext_counts.get(ext, 0) + 1

    info["total_files"] = total_files
    info["file_types"] = dict(
        sorted(ext_counts.items(), key=lambda x: -x[1])[:20]
    )

    # Detect project type
    root_files = set(os.listdir(project_root))
    if "package.json" in root_files:
        info["project_type"] = "node/javascript"
    elif "pyproject.toml" in root_files or "setup.py" in root_files:
        info["project_type"] = "python"
    elif "Cargo.toml" in root_files:
        info["project_type"] = "rust"
    elif "go.mod" in root_files:
        info["project_type"] = "go"
    elif "pom.xml" in root_files or "build.gradle" in root_files:
        info["project_type"] = "java"
    else:
        info["project_type"] = "unknown"

    return info