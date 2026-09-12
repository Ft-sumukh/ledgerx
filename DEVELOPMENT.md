# Ledger-X Development Guidelines

## Engineering Standards

1. **Strict TypeScript**: Never use `any`. Explicitly type all function signatures, parameters, and domain outputs.
2. **Zero Floating-Point Math**:
   - Prohibited: `const total = amountA + amountB;`
   - Required: `const total = moneyA.add(moneyB);`
3. **Immutability of Ledger Data**:
   - Never issue `UPDATE` or `DELETE` queries against `ledger_entries` or posted transactions.
   - Corrections must be made by creating a reversal transaction with reference to the original ID.
4. **Tenant Isolation**:
   - Always verify `organization_id` on every query and mutation.
   - Never trust client-supplied tenant identifiers without session verification.
5. **Idempotency**:
   - All state-altering financial endpoints must accept and enforce an `Idempotency-Key` header.
6. **Error Handling**:
   - Use typed domain errors (`FinancialDomainError` subclasses) instead of generic strings.

---

## Commands

```bash
# Typecheck
npm run typecheck

# Production build
npm run build

# Development server
npm run dev
```
