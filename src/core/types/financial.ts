/**
 * Ledger-X Core Financial Types & Domain Models
 *
 * Strict invariants:
 * - Every account belongs to one of 5 fundamental categories.
 * - Transactions must enforce Total Debits === Total Credits.
 * - Posted transactions are immutable.
 */

export const AccountCategory = {
  ASSET: "ASSET",
  LIABILITY: "LIABILITY",
  EQUITY: "EQUITY",
  REVENUE: "REVENUE",
  EXPENSE: "EXPENSE",
} as const;

export type AccountCategory = (typeof AccountCategory)[keyof typeof AccountCategory];

export const NormalBalance = {
  DEBIT: "DEBIT",
  CREDIT: "CREDIT",
} as const;

export type NormalBalance = (typeof NormalBalance)[keyof typeof NormalBalance];

export const EntryDirection = {
  DEBIT: "DEBIT",
  CREDIT: "CREDIT",
} as const;

export type EntryDirection = (typeof EntryDirection)[keyof typeof EntryDirection];

export const TransactionStatus = {
  DRAFT: "DRAFT",
  PENDING: "PENDING",
  POSTED: "POSTED",
  REVERSED: "REVERSED",
  REJECTED: "REJECTED",
} as const;

export type TransactionStatus = (typeof TransactionStatus)[keyof typeof TransactionStatus];

/**
 * Returns the normal balance for an account category according to double-entry accounting rules:
 * - Assets & Expenses increase with Debits (Normal Balance = DEBIT)
 * - Liabilities, Equity & Revenues increase with Credits (Normal Balance = CREDIT)
 */
export function getNormalBalance(category: AccountCategory): NormalBalance {
  switch (category) {
    case AccountCategory.ASSET:
    case AccountCategory.EXPENSE:
      return NormalBalance.DEBIT;
    case AccountCategory.LIABILITY:
    case AccountCategory.EQUITY:
    case AccountCategory.REVENUE:
      return NormalBalance.CREDIT;
  }
}

/**
 * Fundamental Currency Representation
 */
export interface CurrencyUnit {
  code: string; // e.g. "USD", "EUR", "GBP"
  symbol: string; // e.g. "$", "€", "£"
  precision: number; // e.g. 2 for standard fiat, 4 for internal ledger precision
}

export const DEFAULT_CURRENCY: CurrencyUnit = {
  code: "USD",
  symbol: "$",
  precision: 4,
};
