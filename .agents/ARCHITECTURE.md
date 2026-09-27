# Architecture & Coding Standards

## Tech Stack & Environment
- **Python**: 3.14+ (Dev Container virtualenv located at `/home/vscode/.venv` outside workspace)
- **Framework / Service**: Python Async SMS Service
- **Dependency & Package Management**: `pyproject.toml` (pip / uv / poetry)
- **Module Structure**: `src/snippen_sms/`

## Directory Structure

```
snippen-sms-service/
├── .devcontainer/                    # Dev Container configuration for Python 3.14
├── .agents/                          # Agent guidelines
│   ├── ARCHITECTURE.md               # This file - Python architecture overview
│   ├── TESTING.md                    # Project-specific testing & quality commands
│   ├── python-agent-instructions/    # Submodule: Python-specific standards
│   └── common-agent-instructions/    # Submodule: Common technology-agnostic standards
├── docs/                             # System documentation & architecture guides
├── firmware/                         # MicroPython standalone gateway firmware
├── scripts/                          # Development & formatting utilities
├── src/
│   └── snippen_sms/                  # Python application package
├── tests/                            # pytest test suite
├── tools/                            # Companion configuration and testing tools
├── pyproject.toml                    # Dependencies and tools configuration
├── README.md                         # User documentation
├── DEV_README.md                     # Developer documentation
├── CHANGELOG.md                      # Project history
└── Dockerfile                        # Production container image (Python 3.14-slim)
```

## Python-Specific Architectural Rules

Refer to [Python Architecture Standards](file:///.agents/python-agent-instructions/PYTHON_ARCHITECTURE.md) for:
- Asynchronous programming (`asyncio`) patterns
- `src/` layout conventions
- Modularity and decoupling principles
- Explicit interfaces and deterministic execution

Also see [Common Architecture Standards](file:///.agents/common-agent-instructions/ARCHITECTURE.md) for:
- Modularity principles
- Database timestamp requirements (`created_at`, `modified_at`)
