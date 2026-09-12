# Ledger-X

> **Enterprise Digital Ledger & Financial System of Record**

Ledger-X is a modern, secure, scalable, and auditable digital ledger and financial management platform designed as an authoritative financial system of record.

---

## Core Financial Invariants

Ledger-X is built upon non-negotiable financial and architectural principles:

1. **Double-Entry Balance Invariant**:
   $$\sum \text{Debits} = \sum \text{Credits}$$
   Every posted transaction must balance down to zero fractional error.
2. **Zero Floating-Point Math**:
   All monetary calculations use arbitrary-precision fixed decimals (`NUMERIC(19, 4)` and `decimal.js` with Banker's Rounding `ROUND_HALF_EVEN`).
3. **Transaction Immutability**:
   Posted financial transactions can never be modified or deleted. Corrections must occur via explicit reversal or adjustment transactions.
4. **Multi-Tenant Isolation**:
   Strict tenant boundaries enforced at the database and data-access layer. Zero cross-organization leakage.
5. **Atomic Operations**:
   Financial transactions either commit completely or abort entirely. No partial posting states.
6. **Append-Only Audit Trail**:
   Every state mutation logs who, what, when, why, before-state, and after-state snapshots.
7. **Idempotency Guarantees**:
   Mutating API endpoints require unique idempotency keys to protect against duplicate submissions.

---

## Project Structure

```
ledgerx/
├── src/
│   ├── app/                 # Next.js App Router (UI Pages & Versioned API Handlers)
│   │   ├── api/v1/          # Versioned REST endpoints (/api/v1/health, etc.)
│   │   ├── layout.tsx       # Root enterprise shell
│   │   ├── page.tsx         # Dashboard landing page
│   │   └── globals.css      # Design tokens and Tailwind directives
│   ├── core/                # Framework-agnostic Financial Domain Core
│   │   ├── types/           # AccountCategory, NormalBalance, TransactionStatus
│   │   ├── math/            # Money immutable value object & decimal math
│   │   └── errors/          # Domain financial exceptions
│   ├── server/              # Server infrastructure, DB clients, repositories
│   ├── components/          # Reusable design system & UI components
│   └── lib/                 # Shared utilities
├── docs/                    # Architecture, Database, Security specifications
├── ARCHITECTURE.md          # Architectural blueprint and modular design
├── DEVELOPMENT.md           # Engineering guidelines and coding standards
├── ROADMAP.md               # 14-part incremental development roadmap
├── package.json             # Tooling & dependencies
└── tsconfig.json            # Strict TypeScript configuration
```

---

## Getting Started

### Prerequisites
- **Node.js**: `v20.x` or `v22.x`
- **npm**: `v10.x` or `v11.x`
- **PostgreSQL**: `v15+` (for subsequent database phases)

### Installation
```bash
# Clone repository
git clone https://github.com/Ft-sumukh/ledgerx.git
cd ledgerx

# Install dependencies
npm install

# Copy environment template
cp .env.example .env.local

# Run type checking
npm run typecheck

# Start development server
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) to view the application shell or check the health API at [http://localhost:3000/api/v1/health](http://localhost:3000/api/v1/health).

---

## Roadmap

Ledger-X is built incrementally across 14 dedicated phases. See [ROADMAP.md](./ROADMAP.md) for detailed phase breakdowns.
