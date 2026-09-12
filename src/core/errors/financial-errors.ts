/**
 * Domain-specific errors for Ledger-X financial engine.
 */

export abstract class FinancialDomainError extends Error {
  public abstract readonly code: string;
  public readonly statusCode: number;

  constructor(message: string, statusCode: number = 400) {
    super(message);
    this.name = this.constructor.name;
    this.statusCode = statusCode;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class UnbalancedTransactionError extends FinancialDomainError {
  public readonly code = "UNBALANCED_TRANSACTION";

  constructor(totalDebits: string, totalCredits: string) {
    super(
      `Financial invariant violation: Total Debits (${totalDebits}) does not equal Total Credits (${totalCredits}).`,
      422
    );
  }
}

export class ImmutableTransactionError extends FinancialDomainError {
  public readonly code = "TRANSACTION_IMMUTABLE";

  constructor(transactionId: string, status: string) {
    super(
      `Transaction '${transactionId}' is in status '${status}' and cannot be modified or deleted. Create an adjustment or reversal transaction instead.`,
      403
    );
  }
}

export class InvalidAccountCategoryError extends FinancialDomainError {
  public readonly code = "INVALID_ACCOUNT_CATEGORY";

  constructor(category: string) {
    super(`Invalid account category: '${category}'. Must be ASSET, LIABILITY, EQUITY, REVENUE, or EXPENSE.`, 400);
  }
}

export class TenantIsolationError extends FinancialDomainError {
  public readonly code = "TENANT_ACCESS_DENIED";

  constructor(targetOrgId: string) {
    super(`Access violation: Attempted cross-tenant operation on organization '${targetOrgId}'.`, 403);
  }
}

export class IdempotencyConflictError extends FinancialDomainError {
  public readonly code = "IDEMPOTENCY_CONFLICT";

  constructor(key: string) {
    super(`A request with idempotency key '${key}' is currently being processed or has completed with different parameters.`, 409);
  }
}
