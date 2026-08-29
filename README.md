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

## Quick Start (Development)

Run the test suite and code linter in the development environment:

```bash
# Run unit tests
pytest

# Run code linter
ruff check .
```

For detailed development environment instructions, see the [Developer Guide](file:///workspaces/snippen-sms-service/DEV_README.md).
