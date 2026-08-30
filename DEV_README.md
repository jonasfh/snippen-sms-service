# Developer Documentation - Snippen SMS Service

## Architecture Overview

`snippen-sms-service` is a Python service designed to handle SMS communications for `snippen-booking`.

### Directory Layout

```
snippen-sms-service/
├── .devcontainer/            # Dev Container configuration (Python 3.14)
├── .agents/                  # Agent guidelines (Architecture, Testing, common-agent-instructions submodule)
├── docs/                     # System documentation & architecture guides
│   ├── README.md             # Documentation overview
│   ├── architecture.md       # High-level architecture, provider abstraction & flows
│   └── snippen_booking_api_spec.md # WordPress REST API spec & implementation tasks
├── scripts/                  # Development & formatting utilities
│   ├── format.py             # Whitespace & file formatting tool
│   └── validate_pr.py        # PR SemVer & changelog validation tool
├── src/
│   └── snippen_sms/          # Application package
│       ├── __init__.py       # Package version & exports
│       ├── client.py         # Snippen API HTTP client & error handling
│       ├── config.py         # Gateway configuration settings
│       ├── context.py        # Booking context resolution & conversational session management
│       ├── gateway.py        # GatewayService lifecycle, send/receive orchestration & run loop
│       ├── main.py           # Entry point & CLI runner
│       ├── migrations/       # SQLite database migration system
│       │   ├── __init__.py   # Migration exports
│       │   ├── runner.py     # MigrationRunner & Migration class
│       │   └── sql/          # Sequential SQL migration files
│       ├── models.py         # Message domain models and enums
│       ├── providers/        # SMS provider abstraction layer
│       │   ├── __init__.py   # Provider exports & factory registry
│       │   ├── base.py       # SmsProvider ABC, SendResult, IncomingMessage
│       │   ├── memory.py     # InMemorySmsProvider for testing & simulation
│       │   └── mock.py       # MockSmsProvider for mock messaging & auto-replies
│       ├── storage.py        # SQLite persistent storage repository
│       ├── sync.py           # Two-way sync engine coordinating storage & Snippen API
│       └── updater.py        # GitHub release checking and self-update management
├── tests/
│   ├── conftest.py           # Pytest fixtures
│   ├── test_build_release.py # Release build & checksum calculation tests
│   ├── test_client.py        # SnippenClient HTTP client tests
│   ├── test_context.py       # Booking context resolution & dialogue session tests
│   ├── test_format.py        # Formatter tests
│   ├── test_gateway.py       # GatewayService lifecycle & provider integration tests
│   ├── test_main.py          # Unit tests
│   ├── test_migrations.py    # Database migration unit & integration tests
│   ├── test_mock_provider.py # Mock SMS provider and factory tests
│   ├── test_providers.py     # SMS provider abstraction unit tests
│   ├── test_storage.py       # SQLite message storage unit & integration tests
│   ├── test_sync.py          # SyncService coordination & retry tests
│   ├── test_updater.py       # GitHub release version checking & updater unit tests
│   └── test_validate_pr.py   # PR validation tests
├── pyproject.toml            # Python packaging and dependency config
├── README.md                 # User documentation
├── DEV_README.md             # Developer documentation
└── CHANGELOG.md              # Project history
```

For high-level system architecture, communication flows, and boundaries, see [docs/architecture.md](file:///workspaces/snippen-sms-service/docs/architecture.md).

## Development Setup

1. **Prerequisites**: Python 3.14+ and `pip`.
2. **Environment & Dependencies**:
   - In **Dev Container**, the virtual environment is automatically set up at `/home/vscode/.venv` (outside the workspace root) to prevent collisions with host OS environments.
   - For local CLI development outside container:
     ```bash
     python -m venv ~/.venv
     source ~/.venv/bin/activate
     pip install -e ".[dev]"
     ```
3. **Testing, Linting, Formatting, Building & PR Validation**:
   ```bash
   # Run test suite
   pytest

   # Run lint checks
   ruff check .

   # Format files & cleanup whitespace / newlines
   python scripts/format.py

   # Build distribution packages and generate SHA-256 checksums
   python scripts/build_release.py

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
  - Builds `.whl` and `.tar.gz` distributions with `python scripts/build_release.py` and calculates `checksums.txt`.
  - Publishes a formal GitHub Release attaching all build distributions and checksums.
