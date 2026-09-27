# AGENTS.md

## Purpose
Guide AI agents working in this repository.

## Project-Specific Configuration

- **Python Version**: Python 3.14+
- **Source Code**: `src/snippen_sms/`
- **Dev Container Virtual Environment**: `/home/vscode/.venv` (outside workspace to prevent collisions)
- **SMS Provider Backends**: `mock`, `memory`, `fake` (HTTP-based), and `http`
- **Frontend Testing**: `tools/web-config/` (optional; run `pytest tests/test_web_config_contract.py` when BLE contract changes)

## Self-Improvement & Environment Adaptation

Whenever an agent experiences friction or environment errors (e.g., sandbox network issues for `gh` CLI, missing tools, unusual log locations, git ref locks), update `AGENTS.md` and `.agents/` modular guidelines with workarounds so subsequent sessions execute cleanly.

## Modular Sub-guidelines

### Common (Technology-Agnostic) Submodule Guidelines
- 🔄 **[Workflow Guidelines](file:///.agents/common-agent-instructions/WORKFLOW.md)**: GitHub issue-driven workflow, branching, commit conventions, PR merge rules, SemVer, and CHANGELOG maintenance.
- 📝 **[Documentation Standards & Diagrams](file:///.agents/common-agent-instructions/DOCUMENTATION.md)**: Documentation synchronization, README/DEV_README maintenance, and Mermaid syntax rules.
- 🧪 **[Quality & Testing Principles](file:///.agents/common-agent-instructions/TESTING.md)**: Automated test requirements, zero-linting policy, and formatting hygiene.
- 📐 **[Common Architecture](file:///.agents/common-agent-instructions/ARCHITECTURE.md)**: Modularity, decoupling, and universal database timestamp rules.

### Python-Specific Submodule Guidelines
- 🛠️ **[Python Environment & Tooling](file:///.agents/python-agent-instructions/PYTHON_ENVIRONMENT_AND_TOOLING.md)**: Virtual environment management (`uv`, `poetry`, `venv`), dependency locking via `pyproject.toml`, and code formatting with `ruff`.
- 🏷️ **[Python Typing & Style](file:///.agents/python-agent-instructions/PYTHON_TYPING_AND_STYLE.md)**: Strict type hints (PEP 484/585/604), Pydantic v2 & dataclasses, zero dynamic `Any`.
- 🧪 **[Python Testing & QA](file:///.agents/python-agent-instructions/PYTHON_TESTING.md)**: Unit/integration testing with `pytest`, async patterns (`pytest-asyncio`), test isolation, and static type checking.
- 📐 **[Python Architecture](file:///.agents/python-agent-instructions/PYTHON_ARCHITECTURE.md)**: Async programming (`asyncio`), `src/` layout, modularity, explicit interfaces, and deterministic execution.
- 📝 **[Python Documentation](file:///.agents/python-agent-instructions/PYTHON_DOCUMENTATION.md)**: Google-style docstrings (PEP 257), type hints as documentation, and sync rules.

### Project-Specific Guidelines
- 🐍 **[Project Architecture & Tech Stack](file:///.agents/ARCHITECTURE.md)**: Python tech stack, directory structure, module layout, and async I/O.
- 🧪 **[Python Testing & Quality Commands](file:///.agents/TESTING.md)**: Running `pytest`, `ruff`, formatting (`scripts/format.py`), and PR validation (`scripts/validate_pr.py`).

## Versioning & Changelog
- **Version Bump**: Update version in `pyproject.toml` or `src/snippen_sms/__init__.py` on functional changes.
- **CHANGELOG.md**: Add an entry under `## [X.Y.Z] - YYYY-MM-DD` for every version bump.
