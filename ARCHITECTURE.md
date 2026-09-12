# Ledger-X System Architecture

## Architectural Philosophy

Ledger-X is engineered as a **Modular Monolith**. It unites the development velocity and operational simplicity of a unified codebase while enforcing strict decoupling between domain logic, data persistence, and HTTP/presentation layers.

---

## High-Level Topology

```
                       ┌─────────────────────────────────────┐
                       │          Next.js App Router         │
                       │     (React 19 / Tailwind CSS)       │
                       └──────────────────┬──────────────────┘
                                          │
                       ┌──────────────────▼──────────────────┐
                       │           API Gateway Layer         │
                       │          (/api/v1/ Route Handlers)  │
                       └──────────────────┬──────────────────┘
                                          │
               ┌──────────────────────────┴──────────────────────────┐
               │                                                     │
 ┌─────────────▼─────────────┐                         ┌─────────────▼─────────────┐
 │    Security & Tenancy     │                         │        Audit Trail        │
 │  (Auth, RBAC, Org Guard)  │                         │   (Append-Only Events)    │
 └─────────────┬─────────────┘                         └─────────────▲─────────────┘
               │                                                     │
               └──────────────────────────┬──────────────────────────┘
                                          │
                       ┌──────────────────▼──────────────────┐
                       │          Domain Services            │
                       │ (Accounts, Transactions, Reporting) │
                       └──────────────────┬──────────────────┘
                                          │
                       ┌──────────────────▼──────────────────┐
                       │          Ledger Core Engine         │
                       │   (Double-Entry, Immutability,      │
                       │      Money Value Object Math)       │
                       └──────────────────┬──────────────────┘
                                          │
                       ┌──────────────────▼──────────────────┐
                       │          PostgreSQL Database        │
                       │   (ACID, Constraints, Row Locks)    │
                       └─────────────────────────────────────┘
```

---

## Domain Boundary Isolation

All business logic resides in `src/core/` and must never import from `src/app/` or `src/components/`.

```
src/core/
├── types/         # Foundational financial types (AccountCategory, NormalBalance, etc.)
├── math/          # Money value object & arbitrary-precision decimal operations
└── errors/        # Typed domain exceptions (UnbalancedTransactionError, etc.)
```

### Invariant Enforcement
1. **Double-Entry Invariant**: Every posted transaction must verify $\sum \text{Debits} = \sum \text{Credits}$.
2. **Numeric Precision**: JavaScript `number` type is prohibited for money amounts. `Money` wrapping `decimal.js` with Banker's Rounding (`ROUND_HALF_EVEN`) is used universally.
3. **Database Constraints**: Financial invariants are enforced in code *and* defended in the database via foreign keys, unique constraints, and check constraints.
