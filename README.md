# Snippen SMS Service (`snippen-sms-service`)

A lightweight, dedicated two-way SMS gateway service designed for the **Snippen** booking and management platform.

---

## Purpose

`snippen-sms-service` provides a cost-effective, self-hosted SMS messaging gateway connecting the Snippen booking application to physical cellular SMS modem hardware. By utilizing local SIM card subscriptions instead of commercial third-party SaaS messaging aggregators, the service achieves:

- **Cost Efficiency**: Predictable, minimal per-message operational costs for both high-volume notifications and conversational SMS.
- **Two-Way Messaging**: Reliable dispatching of outbound notifications (booking confirmations, access codes, reminders) and ingestion of inbound guest replies.
- **Hardware Isolation**: Complete abstraction of SMS modem control (AT commands, serial ports, SIM status, connection drops) from business booking logic.

---

## System Topology Overview

```
[ Snippen Booking App ] <---> [ Snippen SMS Gateway ] <---> [ SMS Modem / SIM ] <---> [ Cellular Network ] <---> [ End User ]
```

- **Snippen Booking Platform**: Manages business rules, booking schedules, guest records, and decides what messages to send or actions to take.
- **Snippen SMS Gateway**: Handles message queuing, rate limiting, modem hardware interfacing, inbound message polling, and health monitoring.

---

## Documentation

- 📚 **[Documentation Overview](file:///workspaces/snippen-sms-service/docs/README.md)**: Index of all documentation resources.
- 📐 **[System Architecture & Design](file:///workspaces/snippen-sms-service/docs/architecture.md)**: High-level architectural design, system boundaries, sequence diagrams, and design principles.
- 🔌 **[Snippen Booking WordPress API Spec](file:///workspaces/snippen-sms-service/docs/snippen_booking_api_spec.md)**: WordPress REST API routes, Bearer token authorization, and plugin implementation tasks.
- 🛠️ **[Developer Guide](file:///workspaces/snippen-sms-service/DEV_README.md)**: Setup instructions, Dev Container configuration, testing, and linting.
- 🤖 **[Agent Guidelines](file:///workspaces/snippen-sms-service/AGENTS.md)**: Project workflows and conventions for automated agents.

---

## Configuration

The gateway service can be configured via CLI flags or environment variables:

| Setting | Environment Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| Service Name | `SNIPPEN_SMS_SERVICE_NAME` | `snippen-sms-service` | Name of the service instance |
| Log Level | `SNIPPEN_SMS_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| Poll Interval | `SNIPPEN_SMS_POLL_INTERVAL` | `2.0` | Polling loop tick interval in seconds |
| Database Path | `SNIPPEN_SMS_DATABASE_PATH` | `data/sms_gateway.db` | Path to SQLite database file (or `:memory:`) |
| Provider | `SNIPPEN_SMS_PROVIDER` | `mock` | SMS provider backend (`mock`, `memory`) |
| Snippen API URL | `SNIPPEN_SMS_API_URL` | *(None)* | Snippen WordPress REST API base URL |
| Snippen API Token | `SNIPPEN_SMS_API_TOKEN` | *(None)* | Shared Bearer/API token for Snippen authentication |
| Sync Interval | `SNIPPEN_SMS_SYNC_INTERVAL` | `5.0` | Synchronization interval in seconds |
| Sync Timeout | `SNIPPEN_SMS_SYNC_TIMEOUT` | `10.0` | HTTP request timeout in seconds |
| Sync Enabled | `SNIPPEN_SMS_SYNC_ENABLED` | `true` | Enable/disable automatic Snippen synchronization |
| Booking Resolution | `SNIPPEN_SMS_BOOKING_RESOLUTION_ENABLED` | `true` | Enable automatic booking context resolution for incoming SMS |
| Conversation TTL | `SNIPPEN_SMS_CONVERSATION_TTL_SECONDS` | `7200.0` | Active dialogue session window in seconds (2 hours) |
| GitHub Repo | `SNIPPEN_SMS_GITHUB_REPO` | `jonasfh/snippen-sms-service` | Target repository for software updates |
| Startup Update Check | `SNIPPEN_SMS_CHECK_UPDATES_ON_STARTUP` | `true` | Check GitHub Releases on service start |
| Auto Update Check | `SNIPPEN_SMS_AUTO_UPDATE_CHECK` | `true` | Enable periodic background update checks |
| Update Interval | `SNIPPEN_SMS_UPDATE_CHECK_INTERVAL` | `86400.0` | Interval in seconds between update checks |

---

## Quick Start (Development)

Start the long-running SMS gateway service:

```bash
# Start gateway service using default mock provider
python -m snippen_sms.main

# Or run with custom provider, poll interval, log level, and database path
python -m snippen_sms.main --provider mock --poll-interval 1.0 --log-level DEBUG
```

Check for software updates and upgrade:

```bash
# Check if a new version is available on GitHub Releases
snippen-sms check-update

# Download release artifact and perform software upgrade
snippen-sms update
```

Manage database migrations:

```bash
# Apply pending schema migrations
snippen-sms migrate

# Check migration status and current schema version
snippen-sms migrate-status
```

Trigger manual Snippen API synchronization:

```bash
# Execute a one-time synchronization cycle with Snippen
snippen-sms sync --api-url https://vestreholmensameie.no/wp-json/snippen/v1/sms --api-token <token>
```


Run the test suite, code linter, and formatting tool in the development environment:

```bash
# Run unit tests
pytest

# Run code linter
ruff check .

# Run project formatter
python scripts/format.py
```

For detailed development environment instructions, see the [Developer Guide](file:///workspaces/snippen-sms-service/DEV_README.md).
