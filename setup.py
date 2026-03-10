from setuptools import setup, find_packages

setup(
    name="claude-code-rlm",
    version="0.1.0",
    description=(
        "RLM plugin for Claude Code — "
        "recursive reasoning for large codebases"
    ),
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Your Name",
    url="https://github.com/yourname/claude-code-rlm",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "rlms>=0.1.0",
        "pyyaml>=6.0",
        "anthropic>=0.30.0",
        "mcp[cli]>=1.0.0",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)