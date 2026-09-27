# Python Testing & Quality Assurance Guidelines

Refer to [Python Testing & QA Standards](file:///.agents/python-agent-instructions/PYTHON_TESTING.md) for comprehensive testing patterns including:
- Unit and integration testing with `pytest`
- Async test patterns (`pytest-asyncio`)
- Test isolation and fixtures
- Static type checking

Also see [Common Quality Principles](file:///.agents/common-agent-instructions/TESTING.md) for overall testing and quality policies.

## Project-Specific Test & Lint Commands

Use `pytest` and `ruff` to run tests and linting:

```bash
# Run test suite
pytest

# Run BLE Web Config client contract tests
pytest tests/test_web_config_contract.py

# Linting and style checks (Ruff)
ruff check .
ruff format --check .

# Project-wide formatting (Python, Markdown, JSON, YAML, TOML)
python scripts/format.py

# PR validation (SemVer and CHANGELOG check)
python scripts/validate_pr.py
```

## Frontend / Web Config Testing

When developing exclusively on frontend/web assets (HTML, CSS, JavaScript in `tools/web-config/`):
- Running the full Python test suite (`pytest`) is NOT required during iterative development unless Python files are modified
- Run the targeted contract test when GATT characteristics or contract definitions change:
  ```bash
  pytest tests/test_web_config_contract.py
  ```

## Mandatory Rules
- Create unit or integration tests in `tests/` for all new functionality
- Update existing tests when modifying functionality
- Always run `ruff check .` and resolve all errors and warnings before completing a task
- Always run `python scripts/format.py` before committing to remove trailing whitespace, add single newline at file end, and remove duplicate newlines across all files

## Writing Tests
- Locate tests in `tests/`
- File names follow `test_*.py` format
- Test function names start with `test_*`
- Use `pytest` fixtures in `tests/conftest.py` for shared setups
