# Developer Documentation - Snippen SMS Service

## Architecture Overview

`snippen-sms-service` is a Python service designed to handle SMS communications for `snippen-booking`.

### Directory Layout

```
snippen-sms-service/
├── .devcontainer/            # Dev Container configuration (Python 3.12)
├── .agents/                  # Agent guidelines (Architecture, Workflow, Testing, Docs)
├── src/
│   └── snippen_sms/          # Application package
│       ├── __init__.py       # Package version
│       └── main.py           # Entry point
├── tests/
│   ├── conftest.py           # Pytest fixtures
│   └── test_main.py          # Unit tests
├── pyproject.toml            # Python packaging and dependency config
├── README.md                 # User documentation
├── DEV_README.md             # Developer documentation
└── CHANGELOG.md              # Project history
```

## Setup & Local Development

1. **Dev Container**: Open project in VS Code with Dev Containers extension to spin up Python 3.12 environment automatically.
2. **Virtual Environment & Dependencies**:
   - In **Dev Container**, the virtual environment is automatically set up at `/home/vscode/.venv` (outside the workspace root) to prevent collisions with host OS environments.
   - For local CLI development outside container:
     ```bash
     python -m venv ~/.venv
     source ~/.venv/bin/activate
     pip install -e ".[dev]"
     ```
3. **Testing & Linting**:
   ```bash
   pytest
   ruff check .
   ```
