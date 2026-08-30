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

    class MockSmsProvider {
        -sent_messages: list~SentRecord~
        -inbox: list~IncomingMessage~
        +open() async
        +close() async
        +send_sms(recipient: str, body: str) async SendResult
        +receive_sms() async list~IncomingMessage~
        +simulate_inbound(sender: str, body: str) IncomingMessage
        +simulate_incoming(sender: str, body: str) IncomingMessage
        +simulate_send_failure(should_fail: bool, error_message: str)
        +simulate_receive_failure(should_fail: bool, error_message: str)
        +add_auto_reply(trigger: str, reply: str)
        +clear()
    }

    class InMemorySmsProvider {
        +open() async
        +close() async
    }

    class FutureModemProvider {
        -serial_port: str
        -baud_rate: int
        +open() async
        +close() async
        +send_sms(recipient: str, body: str) async SendResult
        +receive_sms() async list~IncomingMessage~
    }

    SmsProvider <|-- MockSmsProvider
    MockSmsProvider <|-- InMemorySmsProvider
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

3. **`MockSmsProvider` & `InMemorySmsProvider`**:
   - High-fidelity mock/in-memory provider enabling offline development, CI/CD testing, simulated inbound/outbound scenarios, failure injection, and automated response rules without physical hardware.

4. **Provider Factory & Registry (`get_provider`, `register_provider`)**:
   - Facilitates dynamic instantiation and runtime swapping of providers via configuration or CLI arguments without changing gateway business logic.

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

## Message Outbox & Inbox Architecture

To provide high reliability and prevent message loss when communication or the SMS provider is temporarily unavailable, `snippen-sms-service` implements local transactional outbox and inbox patterns backed by SQLite storage.

```mermaid
flowchart TD
    subgraph Outbound Flow
        A1["Snippen Send Request"] -->|"enqueue_outbox()"| A2[("Outbox (SQLite: PENDING)")]
        A2 -->|"process_outbox()"| A3["SMS Provider"]
        A3 -->|Success| A4[("Outbox (SQLite: SENT)")]
        A3 -->|Failure / Error| A5[("Outbox (SQLite: FAILED)")]
    end

    subgraph Inbound Flow
        B1["SMS Provider (Modem/SIM)"] -->|"receive_sms()"| B2["Gateway Ingestion (process_inbox)"]
        B2 -->|"Deduplicate & save_message()"| B3[("Inbox (SQLite: RECEIVED)")]
        B3 -->|"get_unprocessed_inbox()"| B4["Snippen Application Ingestion"]
        B4 -->|"mark_inbox_processed()"| B5[("Inbox (SQLite: PROCESSED)")]
    end
```

### Outbox Processing
1. **Persistent Enqueueing**: Outgoing messages are enqueued to the local SQLite database as `PENDING` records via `MessageStorage.enqueue_outbox()` before any provider transmission is attempted.
2. **Batch / Polling Dispatch**: The gateway dispatches pending outbox records via `GatewayService.process_outbox()`. This runs during active sends and on every heartbeat tick of the gateway run loop.
3. **Failure Isolation & Non-Destructive Error Handling**: If provider delivery fails or network timeouts occur, the message status is updated to `FAILED` with detailed diagnostic error messages. Messages are never silently deleted or lost.
4. **Service Restart Resilience**: Any pending outbox messages persist across gateway restarts and will be processed once the service restarts and the SMS provider is available.

### Inbox Ingestion & Handling
1. **Provider Polling**: The gateway periodically polls the SMS provider (`SmsProvider.receive_sms()`) via `GatewayService.poll_incoming_messages()` (or `process_inbox()`).
2. **Deduplication**: Incoming messages are deduplicated against existing database records via `provider_message_id` / `modem_message_id` to prevent ingesting or processing duplicate deliveries.
3. **Local Persistence**: Each unique inbound SMS is immediately persisted into the local SQLite database with `direction=inbound`, `status=received`, timestamp, and provider identifiers.
4. **Unprocessed Message Distinction**: Downstream systems can query unhandled incoming messages via `GatewayService.get_unprocessed_inbox()` (or `MessageStorage.get_unprocessed_inbox()`) and transition them to `PROCESSED` using `mark_inbox_processed(message_id)`.
5. **Fault Isolation**: Transient failures during receive polling or database storage do not result in dropped incoming messages or aborted service loops.

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
        string external_id
        string booking_id
        int conversation_id
        string error_message
        string created_at
        string modified_at
    }
    conversation_contexts {
        int id PK
        string phone_number
        string active_booking_id
        string pending_booking_ids
        int pending_message_id
        string state
        string last_activity_at
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
- **External & Booking Tracking**: The `external_id` column indexes external identifiers assigned by Snippen Booking, while `booking_id` and `conversation_id` associate messages with reservation lifecycles and ongoing dialogue threads.
- **Conversation State Tracking (`conversation_contexts`)**: Tracks active booking context, pending booking selections, and state transitions for each customer phone number.
- **Migration Management (`MigrationRunner`)**: Sequential SQL migration scripts managed atomically with `schema_migrations` tracking, SHA-256 checksum verification, `PRAGMA user_version` synchronization, and automatic execution upon service initialization.

---

## Booking Context Resolution & Conversation Management

When guests reply or send inquiries via SMS, `snippen-sms-service` dynamically identifies the applicable Snippen booking without requiring users to type complicated reference codes or IDs:

```mermaid
sequenceDiagram
    autonumber
    participant Guest as Customer / Guest
    participant GW as SMS Gateway / ContextResolver
    participant DB as SQLite Storage
    participant API as Snippen Booking API

    alt Case 1: Single Active Booking (Unambiguous)
        Guest->>GW: "Hva er koden til døra?"
        GW->>API: GET /wp-json/snippen/v1/sms/bookings?phone=+479...
        API-->>GW: [{id: "105", resource: "Badstue", start_time: "..."}]
        GW->>DB: Save message with booking_id="105", state=RESOLVED
    else Case 2: Multiple Active Bookings (Ambiguous Selection Flow)
        Guest->>GW: "Ehh, jeg trenger noen bord. Er det mulig å få utvask?"
        GW->>API: GET /wp-json/snippen/v1/sms/bookings?phone=+479...
        API-->>GW: [{id: "105", 15.12.2026}, {id: "109", 05.01.2027}]
        GW->>DB: Set state=AWAITING_SELECTION, pending_ids=["105", "109"]
        GW->>Guest: "Du har flere reservasjoner:\n1. 15.12.2026 16:00 (Badstue)\n2. 05.01.2027 11:00 (Felleslokale)\nSvar med tall (1 el 2)..."
        Guest->>GW: "1"
        GW->>DB: Update pending & reply messages with booking_id="105", state=RESOLVED
    end
```

### Context Resolution Capabilities
1. **Zero Booking ID Friction**: Users do not need to memorize or write booking IDs. Context is derived from customer phone numbers and existing reservation schedules.
2. **Automatic Association**: If the user has a single active booking, incoming messages are immediately associated with it.
3. **Interactive Multi-Booking Disambiguation**: When multiple reservations exist, the gateway sends a clear, natural-language prompt listing candidate bookings and lets the user reply with the option number (`1`, `2`, `Nr 1`, `første`).
4. **Active Session Continuation**: Once resolved, subsequent messages within a configurable session window (default 2 hours) automatically inherit the active booking context.
5. **Two-Way Synchronization**: Resolved `booking_id` and `conversation_id` are reported directly to the Snippen Booking backend during inbox sync.

---

## Snippen API Synchronization Architecture

To support deployments behind NAT, mobile cellular modems, and edge firewalls without open inbound ports or dynamic DNS, **all HTTP communication is initiated by the SMS Gateway / Raspberry Pi**.

```mermaid
sequenceDiagram
    autonumber
    participant GW as Gateway / SyncService
    participant DB as SQLite Storage
    participant API as Snippen Booking API (WP)
    participant Provider as SMS Provider (Modem)

    Note over GW,API: Outbox Synchronization (Poll & Dispatch)
    GW->>API: GET /wp-json/snippen/v1/sms/outbox (Bearer Auth)
    API-->>GW: 200 OK: [{id: "101", recipient: "+479...", body: "Hello"}]
    GW->>DB: Enqueue to outbox (deduplicating by external_id)
    GW->>Provider: send_sms()
    Provider-->>GW: SendResult(success=True)
    GW->>DB: Update status to SENT
    GW->>API: POST /wp-json/snippen/v1/sms/outbox/status [{external_id: "101", status: "sent"}]
    API-->>GW: 200 OK
    GW->>DB: Transition status to DELIVERED

    Note over GW,API: Inbound Synchronization (Ingest & Acknowledge)
    Provider-->>GW: Inbound SMS received
    GW->>DB: Save to inbox (status=RECEIVED)
    GW->>API: POST /wp-json/snippen/v1/sms/inbox [{gateway_id: 15, sender: "+47...", body: "JA"}]
    API-->>GW: 200 OK: {processed_ids: [15]}
    GW->>DB: Mark message as PROCESSED
```

### Key Synchronization Capabilities
1. **Pull-Based Communication**: The gateway periodically queries `GET /wp-json/snippen/v1/sms/outbox` for messages scheduled for delivery.
2. **Push-Based Inbound Reporting**: Unprocessed inbound SMS messages are batched and pushed to `POST /wp-json/snippen/v1/sms/inbox`. Upon acknowledgement from Snippen, local messages transition to `PROCESSED`.
3. **Delivery Status Feedback**: Outbound transmission outcomes (success or error diagnostics) are reported via `POST /wp-json/snippen/v1/sms/outbox/status`, allowing Snippen Booking to update reservation logs.
4. **Idempotency & Deduplication**: Outbound items are deduplicated against local SQLite records via `external_id`. If network interruptions prevent immediate acknowledgement, retried sync requests do not produce duplicate SMS transmissions.
5. **Fault Isolation & Zero Data Loss**: If the Snippen application is temporarily down or unreachable, inbound SMS messages remain safely queued in SQLite as `RECEIVED`, and outbound polling retries automatically on subsequent sync ticks.
6. **Authentication**: All HTTP requests are authenticated using `Authorization: Bearer <token>` and `X-API-Key: <token>` headers.
7. **WordPress Plugin Specification**: Complete API endpoints, schema specifications, and developer tasks are documented in [Snippen Booking WordPress API Spec](file:///workspaces/snippen-sms-service/docs/snippen_booking_api_spec.md).

---

## Software Version Checking & Self-Update Architecture

The gateway features built-in release tracking against the official GitHub Releases API to keep field deployments up-to-date.

```mermaid
sequenceDiagram
    autonumber
    participant GW as Gateway / CLI
    participant GH as GitHub Releases API
    participant Pip as Environment / pip
    participant DB as SQLite Migrations

    GW->>GH: GET /repos/{repo}/releases/latest
    GH-->>GW: JSON Release Payload (tag_name, assets)
    GW->>GW: Compare SemVer against current package version
    alt Update Available & Upgrade Requested
        GW->>GH: Download wheel / distribution artifact
        GW->>Pip: pip install --upgrade --no-cache-dir <artifact>
        GW->>DB: MigrationRunner.run_migrations()
        GW-->>GW: Ready for process restart (e.g. systemctl restart)
    else Up to date / Check Only
        GW-->>GW: Update diagnostic status report
    end
```

### Key Update Capabilities
1. **Zero-Dependency Release Checking**: Uses Python's standard `urllib` to query GitHub API with configurable repository defaults (`jonasfh/snippen-sms-service`) and environment overrides (`SNIPPEN_SMS_GITHUB_REPO`).
2. **Safe, Non-Looping Startup Check**: Checks for updates at startup (and periodically in background) without forcing restarts, avoiding reboot crash loops if network conditions or package dependencies encounter issues.
3. **Cryptographic Checksum Verification**: Automatically fetches `checksums.txt` attached to the release and validates SHA-256 integrity of the downloaded package before installation.
4. **Artifact-Based Upgrade**: Discovers and downloads wheel (`.whl`) or tarball distributions, installs via `pip`, and automatically executes any new SQLite schema migrations.
5. **CLI Management**: Direct command-line access via `snippen-sms check-update` and `snippen-sms update`.

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
