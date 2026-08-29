# Snippen SMS Service Documentation

Welcome to the documentation for **Snippen SMS Service** (`snippen-sms-service`), the dedicated SMS gateway subsystem for the Snippen booking and management platform.

---

## Documentation Index

- **[System Architecture & Design](file:///workspaces/snippen-sms-service/docs/architecture.md)**: High-level architectural overview, system boundaries, two-way communication flows (inbound and outbound), and core design principles.
- **[Developer Guide](file:///workspaces/snippen-sms-service/DEV_README.md)**: Local development environment setup, Dev Container usage, testing with `pytest`, and linting rules.
- **[User & Operational Overview](file:///workspaces/snippen-sms-service/README.md)**: High-level project purpose, operational goals, and repository information.
- **[Agent Guidelines](file:///workspaces/snippen-sms-service/AGENTS.md)**: Automated engineering guidelines, issue workflows, and coding standards.

---

## Structure & Contributing Documentation

As new features, hardware drivers, APIs, and data models are introduced, documentation is expanded across the following categories:

- `docs/architecture.md`: High-level system design, topology, and cross-cutting architectural decisions.
- `README.md`: High-level service overview and user-facing operational instructions.
- `DEV_README.md`: Development environment, tools, and testing procedures.
- `CHANGELOG.md`: Chronological log of changes and releases adhering to semantic versioning.

> [!NOTE]
> When implementing new features, endpoints, or data models, always update the relevant documentation files and diagrams to keep them in sync with the codebase.
