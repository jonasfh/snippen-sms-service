# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.1] - 2026-08-30

### Fixed
- Fixed Dev Container base image tag in `.devcontainer/devcontainer.json` to valid MCR tag `mcr.microsoft.com/devcontainers/python:3.14-bookworm` (`#24`).

## [0.10.0] - 2026-08-29

### Changed
- Upgraded project runtime, Dev Container, dependencies, CI workflows, and documentation from Python 3.12 to Python 3.14 (`#17`).
- Updated `pyproject.toml` with `requires-python = ">=3.14"` and `target-version = "py314"` for Ruff (`#17`).
- Updated GitHub Actions workflows (`pr-validator.yml` and `deploy.yml`) to set up Python 3.14 runtime (`#17`).
- Updated `.devcontainer/devcontainer.json` base image to Python 3.14 (`#17`).
- Updated developer documentation, architecture guides, and agent guidelines for Python 3.14 (`#17`).

## [0.9.0] - 2026-08-29

### Added
- Automated release packaging and checksum generation utility `scripts/build_release.py` (`#21`).
- Cryptographic SHA-256 integrity verification in `SoftwareUpdater.download_artifact()` against release `checksums.txt` (`#21`).
- Helper functions `calculate_sha256()` and `parse_checksums_file()` in `snippen_sms.updater` (`#21`).
- GitHub Actions deployment workflow (`.github/workflows/deploy.yml`) updated to build distributions and publish GitHub Releases with attached `.whl`, `.tar.gz`, and `checksums.txt` assets (`#21`).
- Comprehensive unit tests in `tests/test_build_release.py` and `tests/test_updater.py` (`#21`).
- Developer guide and architecture documentation updated with release build instructions and checksum verification flow (`#21`).

## [0.8.0] - 2026-08-29

### Added
- Automated GitHub release version checking and self-update facility with `SoftwareUpdater` in `snippen_sms.updater` (`#19`).
- `ReleaseInfo` and `UpdateCheckResult` domain dataclasses with SemVer comparison logic (`#19`).
- Configurable GitHub repository target (`github_repo` / `SNIPPEN_SMS_GITHUB_REPO`, defaulting to `jonasfh/snippen-sms-service`) (`#19`).
- Safe, non-looping startup version check and periodic background checks in `GatewayService` without blocking offline operation (`#19`).
- Release asset download (wheel `.whl` and tarball `.tar.gz`), pip upgrade execution, and post-upgrade SQLite database schema migrations (`#19`).
- CLI subcommands `snippen-sms check-update` and `snippen-sms update` for manual and automated maintenance (`#19`).
- Update availability reporting in `GatewayService.get_status()` (`#19`).
- Comprehensive unit and integration tests for GitHub release querying, version parsing, wheel installation, and CLI workflows (`#19`).
- System architecture and developer guides updated with release management and update sequence diagrams (`#19`).

## [0.7.0] - 2026-08-29

### Added
- Local transactional message outbox and inbox handling in `MessageStorage` and `GatewayService` (`#8`).
- Outbox persistence helper methods (`enqueue_outbox`, `get_pending_outbox`, `get_outbox`, `count_outbox`) in `MessageStorage` (`#8`).
- Inbox query and counting helpers (`get_inbox`, `count_inbox`) in `MessageStorage` (`#8`).
- Outbox batch processing (`process_outbox`) in `GatewayService` with sequential FIFO dispatch and reliable error handling without message loss (`#8`).
- Periodic outbox processing integrated into the `GatewayService.run()` execution loop alongside inbound polling (`#8`).
- Gateway status reporting for outbox and inbox metrics (`outbox_pending`, `outbox_total`, `inbox_total`) in `GatewayService.get_status()` (`#8`).
- Comprehensive unit and integration tests covering outbox enqueueing, batch dispatch, crash/error retention, service restart resilience, and inbox operations (`#8`).
- System architecture documentation updated with Outbox/Inbox patterns and sequence flow (`#8`).

## [0.6.0] - 2026-08-29

### Added
- Dedicated `MockSmsProvider` (and `MockSMSProvider` alias) in `snippen_sms.providers.mock` for hardware-free gateway development and testing (`#7`).
- Inbound SMS simulation utilities (`simulate_inbound`, `simulate_incoming`) and auto-reply trigger rules for interactive testing (`#7`).
- Configurable failure simulation for outbound message dispatch (`simulate_send_failure`) and inbound polling (`simulate_receive_failure`) (`#7`).
- Provider registry and factory `get_provider()` / `register_provider()` supporting dynamic provider instantiation (`#7`).
- Configurable SMS provider selection in `GatewayConfig` (`provider` field / `SNIPPEN_SMS_PROVIDER` env var) and `--provider` CLI argument in `main.py` (`#7`).
- Comprehensive unit and integration test suite in `tests/test_mock_provider.py` (`#7`).
- Updated system architecture and developer documentation with mock provider capabilities and configuration guides (`#7`).

## [0.5.0] - 2026-08-29

### Added
- SMS provider abstraction layer with `SmsProvider` abstract base class, `SendResult`, and `IncomingMessage` data structures (`#6`).
- Hardware-agnostic `InMemorySmsProvider` implementation for automated testing, simulation, and offline operation (`#6`).
- Provider integration in `GatewayService` with `send_sms()` dispatch, `poll_incoming_messages()` ingestion, and lifecycle hooks (`#6`).
- Polling of incoming SMS integrated into the `GatewayService.run()` main execution loop (`#6`).
- Provider health/type diagnostics reported in `GatewayService.get_status()` (`#6`).
- Comprehensive unit test suite in `tests/test_providers.py` and extended gateway tests in `tests/test_gateway.py` (`#6`).
- Updated system architecture documentation and diagrams detailing provider decoupling and flow (`#6`).

## [0.4.0] - 2026-08-29

### Added
- Database migration management system for embedded SQLite (`#13`).
- Lightweight, zero-dependency `MigrationRunner` and `Migration` dataclass in `snippen_sms.migrations` with atomic transactions, SHA-256 checksum tracking, and rollback on failure (`#13`).
- Persistent `schema_migrations` tracking table and `PRAGMA user_version` synchronization (`#13`).
- Initial migration script `0001_initial_messages_schema.sql` for creating `messages` table and performance indexes (`#13`).
- Automatic schema migration hook on `MessageStorage` and `GatewayService` initialization with baseline support for existing databases (`#13`).
- CLI subcommands `snippen-sms migrate` and `snippen-sms migrate-status` with target-version and custom database path flags (`#13`).
- Comprehensive unit and integration tests covering migration parsing, execution, error rollback, idempotency, baseline migration, and CLI workflows (`#13`).

## [0.3.0] - 2026-08-29

### Added
- Local SQLite message persistence with `MessageStorage` repository (`#5`).
- Domain models `Message`, `MessageDirection`, and `MessageStatus` with UTC timestamp tracking (`created_at`, `modified_at`) (`#5`).
- Persistent storage integration in `GatewayService` and configurable database path in `GatewayConfig` (`#5`).
- Comprehensive unit and integration test suite in `tests/test_storage.py` covering persistence, CRUD operations, filtering, pagination, and service restarts (`#5`).
- System architecture documentation and Mermaid data schema diagram for local message storage (`#5`).

## [0.2.0] - 2026-08-29

### Added
- Gateway application skeleton with `GatewayService` lifecycle management and run loop (`#4`).
- Configuration dataclass `GatewayConfig` supporting environment variable parsing (`#4`).
- CLI runner in `src/snippen_sms/main.py` and `snippen-sms` script entry point with graceful OS signal handling (`SIGINT`, `SIGTERM`) (`#4`).
- Comprehensive unit test suite for `GatewayService` lifecycle and configuration (`#4`).

## [0.1.0] - 2026-08-29

### Added
- Initial Python 3.12 project structure and Dev Container setup (`#1`).
- Package layout under `src/snippen_sms/` with main module and version declaration.
- `pyproject.toml` setup with pytest and ruff dev dependencies.
- Pytest unit testing suite and test configuration.
- Agent guidelines (`AGENTS.md` and `.agents/` docs) updated for Python ecosystem with continuous self-improvement protocols and mandatory documentation synchronization.
- High-level architecture documentation under `docs/architecture.md` and documentation hub in `docs/README.md` (`#3`).
- Updated `README.md` and `DEV_README.md` with system topology, project purpose, and documentation links (`#3`).
- Project-wide formatting utility (`scripts/format.py`) and agent instructions to enforce trailing whitespace removal and single EOF newline hygiene across all code, markdown, and text files.
- Semantic versioning configuration using standard setuptools dynamic package versioning (`#10`).
- PR Validator GitHub Actions workflow (`.github/workflows/pr-validator.yml`) and validation utility (`scripts/validate_pr.py`) to enforce valid SemVer bump, changelog presence, linting, and tests (`#10`).
- Deploy & Release Tagging GitHub Actions workflow (`.github/workflows/deploy.yml`) to automatically tag releases upon merging to main (`#10`).
