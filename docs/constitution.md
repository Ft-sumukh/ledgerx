# LEDGER-ORBIT Engineering Constitution
# ========================================
# Version: 1.0.0 | Established: Phase 0
#
# This document defines the non-negotiable engineering principles that govern
# ALL development on LEDGER-ORBIT. Every engineer, agent, and automated system
# working on this platform must comply with these rules.
#
# Violations of these principles are ALWAYS bugs, regardless of convenience.

---

## 1. The Fundamental Financial Invariant

**This invariant must never be violated, under any circumstances:**

```
∑ Debits = ∑ Credits
```

For every posted ledger transaction, the algebraic sum of all entry amounts must equal zero.

Example — a payment of ₹100 with a ₹5 fee:
```
Customer Account:       -10000  (CREDIT ₹100.00 in minor units)
Merchant Account:        +9500  (DEBIT  ₹95.00)
Platform Fee Account:     +500  (DEBIT  ₹5.00)
                        ------
SUM:                        0  ✓ BALANCED
```

Any code that creates a ledger transaction MUST validate this invariant before committing.
The database enforces this as a CHECK constraint at the storage layer.

**There are no exceptions.**

---

## 2. Zero Floating-Point Arithmetic for Money

**Financial amounts must NEVER be stored or calculated as floating-point numbers.**

Use integer minor units:
- ₹100.50 → 10050 paise
- $99.99  → 9999 cents

Why this matters: `0.1 + 0.2 = 0.30000000000000004` in IEEE-754 binary floating-point.
At financial scale, this causes systematic errors in balances, fees, and reconciliation.

Allowed:
```python
Money(amount_minor=10050, currency=Currency.USD)       # ✓ integer
Money.from_major(Decimal("100.50"), Currency.USD)      # ✓ Decimal → integer
money.multiply_by_factor(Decimal("0.025"))             # ✓ Decimal factor
```

Forbidden:
```python
Money(amount_minor=100.50, currency=Currency.USD)      # ✗ float input
price * 0.025                                          # ✗ float arithmetic
round(price, 2)                                        # ✗ float rounding
```

Rounding MUST use ROUND_HALF_EVEN (banker's rounding) to avoid systematic directional bias.

---

## 3. Ledger Immutability

**Posted ledger entries must never be modified or deleted.**

After a `LedgerTransaction` has status `POSTED`:
- No `UPDATE` on `ledger_entry` rows
- No `DELETE` on `ledger_entry` rows
- No `UPDATE` on `ledger_transaction` rows

Corrections use **compensating transactions**:
```
Original Transaction (POSTED, incorrect)
         ↓
Reversal Transaction (POSTED, negates original)
         ↓
Corrected Transaction (POSTED, correct amount)
```

All three transactions remain permanently in the ledger history.

**Rationale:** The ledger is the financial system of record. Modifying history destroys auditability
and violates accounting standards. Every correction must be explicit and traceable.

---

## 4. Atomic Financial Operations

**Financial state transitions must execute atomically in a single database transaction.**

The minimum atomic unit for a payment is:
```sql
BEGIN;
  INSERT INTO payment_intents ...
  INSERT INTO ledger_transactions ...
  INSERT INTO ledger_entries ...      -- all entries in one transaction
  INSERT INTO idempotency_records ...
  INSERT INTO outbox_events ...
COMMIT;
```

If any step fails → ROLLBACK.

**There must never be a state where:**
- A payment exists without corresponding ledger entries
- Ledger entries exist without a ledger transaction
- A financial state change occurs without an outbox event

---

## 5. Idempotency is Mandatory

**Every state-mutating API endpoint must require and honor an idempotency key.**

Rules:
1. First request with key `K` → execute operation, store result
2. Repeated request with same key `K` and same payload → return stored result (no re-execution)
3. Request with same key `K` and different payload → return HTTP 409 Conflict

Implementation MUST protect against concurrent duplicate requests (using database-level unique constraints or distributed locks).

**This prevents double-billing, double-posting, and duplicate settlement.**

---

## 6. Failure is Normal — Design for Recovery

Assume the following failures happen in production:

- Network requests fail 1-2% of the time
- Workers crash mid-job
- Message brokers become temporarily unavailable
- Database connections time out
- The same webhook is delivered 2-3 times
- The same queue message is delivered twice

The system must:
- Use the **Transactional Outbox Pattern** so events are not lost when brokers are unavailable
- Use idempotent event consumers so duplicate message delivery is safe
- Use exponential backoff with jitter for retries
- Route messages to a Dead-Letter Queue after `max_receive_count` failures
- Never silently swallow errors that corrupt financial state

---

## 7. Observability is Mandatory

Every significant operation must emit:
- A structured log line (JSON) with `correlation_id`, `request_id`, and relevant entity IDs
- A metric increment or histogram update
- An audit event for sensitive financial operations

The correlation ID must flow from the initial API request all the way through:
```
API Request → Payment → Ledger → Outbox → Queue → Worker → Webhook → Settlement → Audit
```

---

## 8. No Fabricated Results

**Never write code that returns fake performance numbers, fake success rates, or fake metrics.**

Forbidden:
```python
return {"throughput": 10000, "p99_latency_ms": 50}  # ✗ fabricated
```

Required:
```python
return bench.measure()  # ✓ actual measurement
```

All performance claims in documentation must reference actual benchmark runs with hardware, configuration, dataset size, concurrency, and duration recorded.

---

## 9. Security First

- Passwords hashed with bcrypt (minimum cost factor 12)
- JWT tokens with short expiry + refresh rotation
- All inputs validated at the API layer via Pydantic schemas
- SQL queries use parameterized statements only (SQLAlchemy ORM or Core with bound parameters)
- Webhook signatures must be verified before processing
- Secrets must never appear in source code, logs, or error messages
- API errors must never expose internal stack traces to clients

---

## 10. Test Before Ship

Every piece of production code must have:
- Unit tests covering the happy path and error cases
- At least one property-based test for financial invariants
- Integration tests for database interactions
- Tests run in CI before any merge

The test suite must be runnable without external dependencies (use SQLite + InMemoryQueue for unit/integration tests).

---

## Enforcement

These principles are enforced by:
1. Code review — every PR must be checked against this constitution
2. Automated tests — the test suite verifies financial invariants
3. Database constraints — the schema enforces structural invariants
4. CI/CD — tests must pass before merging

When in doubt: **correctness over convenience, auditability over performance, explicit over implicit.**
