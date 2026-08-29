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

---

## Quick Start (Development)

Start the long-running SMS gateway service:

```bash
# Start gateway service
python -m snippen_sms.main

# Or run with custom poll interval, log level, and database path
python -m snippen_sms.main --poll-interval 1.0 --log-level DEBUG
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
