# Architecture & System Design

## Overview & Purpose

The **Snippen SMS Gateway** is a dedicated service designed to provide a reliable, cost-effective two-way SMS communication channel for the **Snippen** booking and management platform.

Rather than relying on costly third-party cloud messaging aggregators for ongoing high-volume SMS operations, the gateway connects to an SMS provider abstraction (such as a local cellular SMS modem with a standard SIM subscription). This provides Snippen with direct control over its messaging infrastructure while significantly reducing per-message operational costs.

```mermaid
flowchart LR
    A["Snippen Booking App"] <-->|"SMS Requests & Events"| B["Snippen SMS Gateway"]
    B <-->|"Provider Interface"| C["SMS Provider (Modem / Mock)"]
    C <-->|"Cellular Radio (GSM/LTE)"| D["Mobile Network"]
    D <-->|"SMS"| E["End User / Guest"]
```

---

## Relationship to Snippen

The SMS Gateway operates as an independent subsystem with a clear separation of concerns from the main Snippen booking application:

- **Snippen Booking Platform**:
  - Contains core domain logic, booking lifecycles, customer data, and messaging triggers (e.g., reservation confirmations, check-in instructions, reminders).
  - Decides *when* and *to whom* messages are sent, and *how* incoming customer responses affect bookings.
  - Remains entirely agnostic of hardware details, AT commands, serial ports, and cellular transmission logistics.

- **Snippen SMS Gateway**:
  - Acts as the dedicated bridge between Snippen and the SMS provider backend.
  - Manages outbound message queueing, transmission timing, delivery status tracking, and error recovery.
  - Ingests inbound messages from the SMS provider and exposes them for Snippen to consume.
  - Monitors provider health, signal quality, and cellular connection status.

---

## SMS Provider Abstraction Layer

To ensure the gateway remains completely decoupled from physical hardware (such as specific modem chipsets or serial AT commands) or external vendors, all message transmission and ingestion operations are mediated by the `SmsProvider` abstraction layer:

```mermaid
classDiagram
    class SmsProvider {
        <<abstract>>
        +open() async
        +close() async
        +send_sms(recipient: str, body: str) async SendResult*
        +receive_sms() async list~IncomingMessage~*
    }

    class InMemorySmsProvider {
        -sent_messages: list~SentRecord~
        -inbox: list~IncomingMessage~
        +open() async
        +close() async
        +send_sms(recipient: str, body: str) async SendResult
        +receive_sms() async list~IncomingMessage~
        +simulate_inbound(sender: str, body: str) IncomingMessage
        +simulate_send_failure(should_fail: bool, error_message: str)
        +clear()
    }

    class FutureModemProvider {
        -serial_port: str
        -baud_rate: int
        +open() async
        +close() async
        +send_sms(recipient: str, body: str) async SendResult
        +receive_sms() async list~IncomingMessage~
    }

    SmsProvider <|-- InMemorySmsProvider
    SmsProvider <|-- FutureModemProvider
```

### Abstraction Components

1. **`SmsProvider` (Abstract Base Class)**:
   - `send_sms(recipient, body)`: Asynchronously dispatches an SMS message, returning a `SendResult`.
   - `receive_sms()`: Asynchronously fetches and drains unread incoming SMS messages from the provider/modem, returning a list of `IncomingMessage` instances.
   - `open()` / `close()`: Manages hardware and connection lifecycle hooks.

2. **`SendResult` & `IncomingMessage` (Data Transfer Objects)**:
   - `SendResult(success, message_id, error_message)` encapsulates transmission outcomes and hardware identifiers.
   - `IncomingMessage(sender, body, received_at, provider_message_id)` represents inbound cellular messages in a standardized UTC format.

3. **`InMemorySmsProvider`**:
   - High-fidelity in-memory provider enabling offline development, CI/CD testing, and simulated inbound/outbound scenarios without physical hardware.

---

## Communication Flow

The gateway facilitates two-way communication between Snippen and end users over the mobile network:

### 1. Outbound Message Flow (Notifications & Inquiries)

```mermaid
sequenceDiagram
    autonumber
    participant App as Snippen App
    participant GW as SMS Gateway
    participant Provider as SMS Provider
    participant Carrier as Mobile Network
    participant User as End User

    App->>GW: Request SMS send (recipient, message)
    GW->>GW: Validate & persist pending message
    GW->>Provider: send_sms(recipient, body)
    Provider->>Carrier: Transmit over mobile network
    Carrier->>User: Deliver SMS to handset
    Provider-->>GW: Return SendResult (status, provider_id)
    GW->>GW: Update message status (SENT/FAILED)
    GW-->>App: Report transmission status
```

1. **Send Request**: Snippen submits an outbound message with recipient phone number and content.
2. **Queueing & Persistence**: The gateway records the pending message locally in SQLite.
3. **Provider Dispatch**: The gateway instructs the `SmsProvider` to transmit the payload.
4. **Network Delivery**: The provider delivers the message over the mobile network to the end user.
5. **Status Reporting**: The gateway records transmission results (success, failure, or retry) and makes status available to Snippen.

---

### 2. Inbound Message Flow (Guest Replies & Inbound Requests)

```mermaid
sequenceDiagram
    autonumber
    participant User as End User
    participant Carrier as Mobile Network
    participant Provider as SMS Provider
    participant GW as SMS Gateway
    participant App as Snippen App

    User->>Carrier: Send SMS reply
    Carrier->>Provider: Cellular delivery to SIM
    GW->>Provider: receive_sms() (poll tick)
    Provider-->>GW: Return list of IncomingMessage
    GW->>GW: Persist inbound message to SQLite
    GW->>App: Forward / Notify inbound message
    App->>App: Process booking reply or command
```

1. **Message Arrival**: The end user replies via SMS; the carrier delivers the SMS to the provider.
2. **Ingress & Ingestion**: The gateway polls unread messages from `SmsProvider.receive_sms()`.
3. **Storage & Ack**: The gateway securely records the incoming message in SQLite.
4. **Notification / Forwarding**: The gateway makes the inbound message available to Snippen for business processing and conversational handling.

---

## Key Responsibilities & System Boundaries

| Responsibility | Handled By SMS Gateway | Handled By Snippen |
| :--- | :---: | :---: |
| Booking logic & customer state | ❌ | ✅ |
| Determining recipient phone number & message text | ❌ | ✅ |
| Interpreting message intent / customer replies | ❌ | ✅ |
| Provider & modem communication abstraction | ✅ | ❌ |
| Outbound dispatch queueing & rate limiting | ✅ | ❌ |
| Cellular signal & SIM status monitoring | ✅ | ❌ |
| Inbound message detection & retrieval | ✅ | ❌ |
| Hardware fault detection & provider reconnection | ✅ | ❌ |

---

## Local Message Persistence

To ensure zero message loss during network interruptions or service restarts, the SMS Gateway employs a lightweight, embedded SQLite database backend. Messages are persisted locally before and after transmission or ingestion.

### Data Model & Schema

```mermaid
erDiagram
    messages {
        int id PK
        string direction
        string sender
        string recipient
        string body
        string status
        string modem_message_id
        string error_message
        string created_at
        string modified_at
    }
    schema_migrations {
        int version PK
        string name
        string applied_at
        string checksum
    }
```

- **Persistence Layer (`MessageStorage`)**: Built on Python standard library `sqlite3` using Write-Ahead Logging (`WAL`) mode for robust, concurrent reads and writes without external database server dependencies.
- **Timestamp Tracking**: Every record maintains ISO-8601 UTC `created_at` and `modified_at` timestamps for auditing, synchronization, and retry workflows.
- **Migration Management (`MigrationRunner`)**: Sequential SQL migration scripts managed atomically with `schema_migrations` tracking, SHA-256 checksum verification, `PRAGMA user_version` synchronization, and automatic execution upon service initialization.

---

## Architectural Principles

1. **Hardware Isolation**:
   Physical modem communication (e.g., serial connections, AT commands, USB disconnections) is fully encapsulated within the provider abstraction so changes to modem hardware do not affect the gateway or the main Snippen platform.

2. **Fault Tolerance & Resilience**:
   Cellular networks and physical modems can experience temporary dropouts, signal loss, or power cycles. The gateway is designed to safely queue messages, retry on transient failures, and recover connectivity gracefully.

3. **Loose Coupling**:
   Communication between Snippen and the SMS Gateway is kept clean, lightweight, and decoupled, allowing either service to be updated, restarted, or tested independently.

4. **Extensibility**:
   While designed for physical SMS modems, the high-level architecture accommodates mock modems for local testing, multiple SIM cards, or backup cloud providers in the future without altering the core messaging contracts.
