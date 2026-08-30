# Architecture & Coding Standards

## Tech Stack & Environment
- **Python**: 3.14+ (Dev Container virtualenv located at `/home/vscode/.venv` outside workspace)
- **Framework / Service**: FastAPI / Flask / Python Async SMS Service
- **Dependency & Package Management**: `pyproject.toml` (pip / uv / poetry)
- **Module Structure**: `src/snippen_sms/`

## Directory Structure

```
snippen-sms-service/
├── .devcontainer/            # Dev Container configuration for Python 3.14
├── .agents/                  # Modular agent instructions
├── src/
│   └── snippen_sms/          # Python application package
│       ├── __init__.py       # Version declaration
│       └── main.py           # Service entry point
├── tests/                    # pytest test suite
│   ├── conftest.py           # pytest fixtures
│   └── test_main.py          # Unit tests
├── pyproject.toml            # Dependencies and tools configuration
├── README.md                 # User documentation
├── DEV_README.md             # Developer documentation
└── CHANGELOG.md              # Project history
```

## Core Architectural Rules
- **Modular & Testable**: Keep application logic modular, decoupled from framework-specific handlers where practical.
- **Database Tables**: Always include `created_at` and `modified_at` timestamp columns on database models.
- **Type Annotations**: Use Python type hints (`typing`) across all new classes and functions.
- **Async & I/O**: Use async/await for network or SMS provider integrations where applicable.
