# LEDGER-ORBIT: Architecture Documentation
# ==========================================
# Version: 1.0.0 | Phase 1

## High-Level Architecture

```text
                         CLIENTS
                            │
                            ▼
                       API GATEWAY
                      (FastAPI + CORS)
                            │
             ┌──────────────┼──────────────┐
             │              │              │
             ▼              ▼              ▼
      Correlation ID   Rate Limiter   Auth Middleware
             │
             ▼
       Payment Service
             │
      ┌──────┴──────┐
      │             │
      ▼             ▼
 Ledger Service  Payment State
      │             │
      ▼             ▼
  PostgreSQL    Event Publisher
                    │
                    ▼
             Outbox Poller
                    │
                    ▼
            Message Broker
           (InMemory/Redis/SQS)
                    │
       ┌────────────┼────────────┐
       │            │            │
       ▼            ▼            ▼
   Worker 1     Worker 2     Worker N
       │            │            │
       └────────────┼────────────┘
                    │
            ┌───────┴───────┐
            │               │
            ▼               ▼
     Reconciliation    Job Results
            │
            ▼
    Audit / Analytics
```

## Monorepo Structure

```text
ledger-orbit/
├── apps/
│   ├── api/               FastAPI application
│   └── web/               Next.js dashboard
├── packages/
│   ├── shared_types/      Financial domain primitives
│   ├── configuration/     Settings management
│   ├── logging/           Structured logging
│   ├── database/          SQLAlchemy 2.0 + base models
│   ├── queue/             Queue abstraction
│   └── events/            Domain events
├── services/              Domain service modules
├── infrastructure/        Docker + Terraform
└── tests/                 Test suites
```

## Package Dependency Graph

```text
                    shared_types
                    /           \
             configuration    events
                    |            |
                  logging      queue
                    |
                 database
                    |
              apps/api/main.py
```

No circular dependencies are permitted.

## Technology Decisions

### Python + FastAPI

FastAPI was selected over Flask/Django because:
- Native async/await support (critical for high-throughput financial APIs)
- Pydantic v2 validation with zero-overhead model generation
- Automatic OpenAPI documentation generation
- Dependency injection system for service composition
- Starlette ASGI middleware compatibility

### SQLAlchemy 2.0 Async

The async SQLAlchemy API allows financial transaction coroutines to share event loop
threads with API handlers, avoiding the thread-pool overhead of synchronous ORM patterns.
The 2.0 API uses explicit `select()` statements rather than implicit lazy loading,
making N+1 queries impossible to introduce accidentally.

### InMemoryQueue → Abstract Broker

The `Queue` abstract base class decouples all business logic from the specific
message broker. The same worker code runs against:
- `InMemoryQueue` (development, unit tests — zero dependencies)
- `RedisQueue` (staging — single dependency)
- `SQSQueue` (production — managed, durable)
- `KafkaQueue` (high-throughput future extension)

### Transactional Outbox

The outbox pattern solves the dual-write problem:
> "How do I update the database AND publish an event atomically?"

Without outbox:
```
1. UPDATE payment_intents SET status='SUCCEEDED'   ← DB commit
2. publish(PaymentSucceeded)                       ← Broker publish
   ↑ If step 2 fails, payment is succeeded but no event was published
```

With outbox:
```
BEGIN;
  1. UPDATE payment_intents SET status='SUCCEEDED'
  2. INSERT INTO outbox_events (event_type='PaymentSucceeded', status='PENDING')
COMMIT;
                    ↑ Atomic: both succeed or both fail

3. Outbox poller reads PENDING events and publishes to broker
4. If publish succeeds → mark PUBLISHED
5. If publish fails → retry (outbox event still PENDING)
```

This guarantees at-least-once event delivery with no financial state lost.

## Correlation ID Flow

Every request creates a `correlation_id` that flows through the entire system:

```
HTTP Request
  X-Correlation-ID: abc123
          │
          ▼
CorrelationIdMiddleware
  bind_correlation_id("abc123")
          │
          ▼
Payment Service
  logger.info(..., correlation_id="abc123")
  LedgerTransaction.correlation_id = "abc123"
          │
          ▼
OutboxEvent
  event.correlation_id = "abc123"
          │
          ▼
QueueMessage
  body.correlation_id = "abc123"
          │
          ▼
Worker
  logger.info(..., correlation_id="abc123")
          │
          ▼
Audit Event
  audit.correlation_id = "abc123"
```

A single `correlation_id` query in a log aggregator returns the complete
lifecycle of one payment across all services and workers.
