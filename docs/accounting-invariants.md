# LEDGER-ORBIT: Accounting Invariants Specification
# ====================================================
# Version: 1.0.0

## The Core Invariant

For every posted `LedgerTransaction`:

```
∑ entry.amount_minor × direction_sign = 0
```

Where:
- DEBIT entries have a positive sign
- CREDIT entries have a negative sign
- All entries share the same currency

Equivalently: **Total Debits = Total Credits**

---

## Money Representation

All monetary amounts are stored as **integer minor units** (the smallest indivisible unit of the currency):

| Currency | Minor Unit | Factor | Example |
|----------|-----------|--------|---------|
| INR | Paise | 100 | ₹100.50 → 10050 |
| USD | Cents | 100 | $100.50 → 10050 |
| EUR | Cents | 100 | €100.50 → 10050 |
| GBP | Pence | 100 | £100.50 → 10050 |

**Why integer minor units?**
IEEE-754 double-precision floating-point cannot exactly represent most decimal fractions.
`0.1 + 0.2 = 0.30000000000000004`. At financial scale with millions of transactions,
this causes systematic rounding errors that corrupt account balances.

---

## Rounding Policy

When multiplication produces a non-integer result (e.g. fee calculation):
- Use **ROUND_HALF_EVEN** (banker's rounding)
- Also known as "round half to even" or "unbiased rounding"
- Rounds 2.5 → 2, rounds 3.5 → 4 (rounds to nearest even digit)
- Eliminates systematic directional bias that ROUND_HALF_UP introduces

---

## Normal Balances

Each account type has a **normal balance** direction:

| Account Type | Normal Balance | Increases by | Decreases by |
|-------------|----------------|--------------|--------------|
| Asset | DEBIT | DEBIT | CREDIT |
| Liability | CREDIT | CREDIT | DEBIT |
| Equity | CREDIT | CREDIT | DEBIT |
| Revenue | CREDIT | CREDIT | DEBIT |
| Expense | DEBIT | DEBIT | CREDIT |

---

## Example: Payment of ₹100.00 with 5% Platform Fee

```
LedgerTransaction: {
  reference: "PMT-001"
  currency: INR
  entries: [
    { account: Customer-001,  direction: CREDIT, amount_minor: 10000 }  # -₹100.00 (funds leave customer)
    { account: Merchant-001,  direction: DEBIT,  amount_minor:  9500 }  # +₹95.00  (funds to merchant)
    { account: Platform-Fees, direction: DEBIT,  amount_minor:   500 }  # +₹5.00   (platform fee)
  ]
}

Verification: DEBIT total - CREDIT total = 9500 + 500 - 10000 = 0 ✓
```

---

## Example: Full Refund of ₹100.00

Compensating entries reverse the original:

```
LedgerTransaction: {
  reference: "REF-001"
  related_to: "PMT-001"
  entries: [
    { account: Customer-001,  direction: DEBIT,  amount_minor: 10000 }  # +₹100.00 (funds return to customer)
    { account: Merchant-001,  direction: CREDIT, amount_minor:  9500 }  # -₹95.00  (funds leave merchant)
    { account: Platform-Fees, direction: CREDIT, amount_minor:   500 }  # -₹5.00   (fee reversed)
  ]
}

Verification: 10000 - 9500 - 500 = 0 ✓
```

---

## Invariant Enforcement Layers

The double-entry invariant is enforced at multiple layers for defense in depth:

1. **Application Layer** (`packages/shared_types/money.py`):
   - `Money` rejects float inputs at construction time
   - `LedgerTransaction.validate()` checks sum = 0 before posting

2. **Database Layer** (Phase 2):
   - A `CHECK` constraint ensures the sum of entries equals zero within each transaction
   - This prevents direct database manipulation from bypassing application validation

3. **Test Layer** (property-based tests):
   - Hypothesis generates arbitrary valid and invalid transactions
   - Verifies the invariant holds for all valid inputs
   - Verifies the system rejects all unbalanced inputs

---

## Ledger Immutability

After a `LedgerTransaction` reaches status `POSTED`:

```
ALLOWED:    INSERT new compensating transactions
FORBIDDEN:  UPDATE ledger_entry.amount_minor
FORBIDDEN:  UPDATE ledger_entry.direction
FORBIDDEN:  DELETE ledger_entry
FORBIDDEN:  UPDATE ledger_transaction.status (except through explicit workflow)
```

This is enforced by:
- Application-layer validation (check status before any write)
- Database triggers (Phase 2) that RAISE EXCEPTION on UPDATE/DELETE of posted entries
- Audit logging of any attempt to modify posted records
