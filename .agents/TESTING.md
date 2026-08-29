# Testing & Quality Assurance Guidelines

## Test Commands

Use `pytest` and `ruff` (or Docker container) to run linting and tests:

```bash
# Run tests directly
pytest

# Run fast / specific unit tests
pytest tests/test_main.py

# Linting and style checks (Ruff)
ruff check .
ruff format --check .
```

## Mandatory Rules
- **Create tests**: Create unit or integration tests in `tests/` for all new functionality.
- **Update tests**: Update existing tests when modifying functionality.
- **Linting check**: Always run `ruff check .` (or flake8) and resolve all errors and warnings before completing a task.

## Writing Tests
- Locate tests in `tests/`.
- File names follow `test_*.py` format.
- Test function names start with `test_*`.
- Use `pytest` fixtures in `tests/conftest.py` for shared setups.
