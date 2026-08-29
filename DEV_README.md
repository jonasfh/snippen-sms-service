# Developer Documentation - Snippen SMS Service

## Architecture Overview

`snippen-sms-service` is a Python service designed to handle SMS communications for `snippen-booking`.

### Directory Layout

```
snippen-sms-service/
├── .devcontainer/            # Dev Container configuration (Python 3.12)
├── .agents/                  # Agent guidelines (Architecture, Workflow, Testing, Docs)
├── docs/                     # System documentation & architecture guides
│   ├── README.md             # Documentation overview
│   └── architecture.md       # High-level architecture & communication flows
├── scripts/                  # Development & formatting utilities
│   ├── format.py             # Whitespace & file formatting tool
│   └── validate_pr.py        # PR SemVer & changelog validation tool
├── src/
│   └── snippen_sms/          # Application package
│       ├── __init__.py       # Package version & exports
│       ├── config.py         # Gateway configuration settings
│       ├── gateway.py        # GatewayService lifecycle & run loop
│       ├── main.py           # Entry point & CLI runner
│       ├── models.py         # Message domain models and enums
│       └── storage.py        # SQLite persistent storage repository
├── tests/
│   ├── conftest.py           # Pytest fixtures
│   ├── test_format.py        # Formatter tests
│   ├── test_gateway.py       # GatewayService lifecycle tests
│   ├── test_main.py          # Unit tests
│   ├── test_storage.py       # SQLite message storage unit & integration tests
│   └── test_validate_pr.py   # PR validation tests
├── pyproject.toml            # Python packaging and dependency config
├── README.md                 # User documentation
├── DEV_README.md             # Developer documentation
└── CHANGELOG.md              # Project history

```

For high-level system architecture, communication flows, and boundaries, see [docs/architecture.md](file:///workspaces/snippen-sms-service/docs/architecture.md).

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
3. **Testing, Linting, Formatting & PR Validation**:
   ```bash
   # Run test suite
   pytest

   # Run lint checks
   ruff check .

   # Format files & cleanup whitespace / newlines
   python scripts/format.py

   # Validate PR version bump and changelog
   python scripts/validate_pr.py --base origin/main
   ```

## CI/CD Workflows

- **PR Validator (`.github/workflows/pr-validator.yml`)**:
  - Triggers on pull requests targeting `main`.
  - Runs formatting check (`python scripts/format.py`), ruff linting, and pytest test suite.
  - Verifies that package version conforms to Semantic Versioning and is strictly greater than the latest release git tag.
  - Verifies that `CHANGELOG.md` contains an entry for the version.
- **Deploy & Release Tagging (`.github/workflows/deploy.yml`)**:
  - Triggers on push to `main` (merges).
  - Automatically tags release with `v<version>` if the tag does not already exist.
  - Skips tag creation cleanly if the tag is already present.
