"""
Shared test fixtures for claude-code-rlm.

All tests run WITHOUT API keys, WITHOUT Claude Code,
WITHOUT the rlm library. Pure logic testing.
"""

import os
import json
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def tmp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory, clean up after test."""
    d = Path(tempfile.mkdtemp(prefix="cc_rlm_test_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def fake_project(tmp_dir: Path) -> Path:
    """
    Create a fake project structure for testing.

    Structure:
        project/
        ├── package.json
        ├── src/
        │   ├── index.ts
        │   ├── auth/
        │   │   ├── handler.ts
        │   │   ├── middleware.ts
        │   │   └── utils.ts
        │   ├── api/
        │   │   ├── routes.ts
        │   │   └── controllers.ts
        │   └── db/
        │       ├── connection.ts
        │       └── models.ts
        ├── tests/
        │   ├── auth.test.ts
        │   └── api.test.ts
        ├── .git/
        │   └── config
        ├── node_modules/
        │   └── express/
        │       └── index.js
        └── README.md
    """
    project = tmp_dir / "project"
    project.mkdir()

    # package.json
    (project / "package.json").write_text(json.dumps({
        "name": "test-project",
        "version": "1.0.0",
        "dependencies": {"express": "^4.18.0"},
    }))

    # Source files
    src = project / "src"
    src.mkdir()
    (src / "index.ts").write_text(
        'import { startServer } from "./api/routes";\n'
        'startServer(3000);\n'
    )

    auth = src / "auth"
    auth.mkdir()
    (auth / "handler.ts").write_text(
        'export function authenticate(token: string): boolean {\n'
        '  // TODO: implement proper JWT validation\n'
        '  return token.length > 0;\n'
        '}\n'
        '\n'
        'export function authorize(user: User, role: string): boolean {\n'
        '  return user.roles.includes(role);\n'
        '}\n'
    )
    (auth / "middleware.ts").write_text(
        'import { authenticate } from "./handler";\n'
        '\n'
        'export function authMiddleware(req, res, next) {\n'
        '  const token = req.headers.authorization;\n'
        '  if (!authenticate(token)) {\n'
        '    return res.status(401).json({ error: "Unauthorized" });\n'
        '  }\n'
        '  next();\n'
        '}\n'
    )
    (auth / "utils.ts").write_text(
        'export function hashPassword(password: string): string {\n'
        '  // SECURITY: using MD5 is insecure!\n'
        '  return md5(password);\n'
        '}\n'
    )

    api = src / "api"
    api.mkdir()
    (api / "routes.ts").write_text(
        'import express from "express";\n'
        'import { authMiddleware } from "../auth/middleware";\n'
        '\n'
        'export function startServer(port: number) {\n'
        '  const app = express();\n'
        '  app.use("/api", authMiddleware);\n'
        '  app.listen(port);\n'
        '}\n'
    )
    (api / "controllers.ts").write_text(
        'export class UserController {\n'
        '  async getUser(id: string) {\n'
        '    return db.query(`SELECT * FROM users WHERE id = ${id}`);\n'
        '  }\n'
        '}\n'
    )

    db = src / "db"
    db.mkdir()
    (db / "connection.ts").write_text(
        'export const pool = createPool({\n'
        '  host: "localhost",\n'
        '  database: "myapp",\n'
        '});\n'
    )
    (db / "models.ts").write_text(
        'export interface User {\n'
        '  id: string;\n'
        '  email: string;\n'
        '  roles: string[];\n'
        '}\n'
    )

    # Tests
    tests = project / "tests"
    tests.mkdir()
    (tests / "auth.test.ts").write_text('test("auth works", () => {});\n')
    (tests / "api.test.ts").write_text('test("api works", () => {});\n')

    # .git (should be skipped in scans)
    git = project / ".git"
    git.mkdir()
    (git / "config").write_text("[core]\n")

    # node_modules (should be skipped in scans)
    nm = project / "node_modules" / "express"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = {};\n")

    # README
    (project / "README.md").write_text("# Test Project\n")

    return project


@pytest.fixture
def large_fake_project(tmp_dir: Path) -> Path:
    """
    Create a large fake project (200+ files) for testing
    auto-trigger thresholds.
    """
    project = tmp_dir / "large_project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "big"\n')

    # Create 200 Python files across 20 directories
    for i in range(20):
        pkg = project / f"pkg_{i:02d}"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        for j in range(10):
            (pkg / f"module_{j:02d}.py").write_text(
                f"# Module {i}.{j}\n"
                f"def func_{j}():\n"
                f"    pass\n"
                * 50  # ~150 lines per file
            )

    return project


@pytest.fixture
def sample_config_yaml(tmp_dir: Path) -> Path:
    """Create a sample .claude-rlm.yaml file."""
    config_file = tmp_dir / ".claude-rlm.yaml"
    config_file.write_text("""
backend: anthropic
backend_kwargs:
  model_name: claude-sonnet-4-20250514
  api_key: sk-test-key-12345

max_depth: 3
max_iterations: 10
max_timeout: 60.0

auto_trigger:
  enabled: true
  min_context_chars: 30000

tools:
  read_file: true
  write_file: true
  run_command: false
""")
    return config_file


@pytest.fixture
def global_config_dir(tmp_dir: Path, monkeypatch) -> Path:
    """Create a fake global config directory."""
    config_dir = tmp_dir / "global_config"
    config_dir.mkdir()
    monkeypatch.setattr(
        "python.config.GLOBAL_CONFIG_DIR", config_dir,
    )
    monkeypatch.setattr(
        "python.config.GLOBAL_CONFIG_FILE", config_dir / "config.yaml",
    )
    return config_dir