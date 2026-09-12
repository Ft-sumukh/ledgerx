import { Decimal } from "decimal.js";
import { DEFAULT_CURRENCY, CurrencyUnit } from "../types/financial";

// Configure Decimal for deterministic financial precision using Banker's Rounding (ROUND_HALF_EVEN)
const FinancialDecimal = Decimal.clone({
  precision: 28,
  rounding: Decimal.ROUND_HALF_EVEN,
  toExpNeg: -9,
  toExpPos: 28,
});

/**
 * Immutable Money value object.
 * Guarantees zero floating-point arithmetic anomalies.
 */
export class Money {
  private readonly _amount: Decimal;
  private readonly _currency: CurrencyUnit;

  constructor(amount: string | number | Decimal | Money, currency: CurrencyUnit = DEFAULT_CURRENCY) {
    if (amount instanceof Money) {
      this._amount = amount._amount;
      this._currency = amount._currency;
      return;
    }

    if (amount instanceof Decimal) {
      if (!amount.isFinite()) {
        throw new Error("Money amount must be finite");
      }
      this._amount = amount;
    } else {
      const parsed = new FinancialDecimal(amount);
      if (!parsed.isFinite()) {
        throw new Error("Money amount must be finite and non-NaN");
      }
      this._amount = parsed;
    }

    this._currency = currency;
  }

  public static zero(currency: CurrencyUnit = DEFAULT_CURRENCY): Money {
    return new Money(0, currency);
  }

  public static from(amount: string | number | Decimal | Money, currency: CurrencyUnit = DEFAULT_CURRENCY): Money {
    return new Money(amount, currency);
  }

  public get amount(): Decimal {
    return this._amount;
  }

  public get currency(): CurrencyUnit {
    return this._currency;
  }

  public add(other: Money | string | number | Decimal): Money {
    const addend = other instanceof Money ? other._amount : new FinancialDecimal(other);
    return new Money(this._amount.plus(addend), this._currency);
  }

  public subtract(other: Money | string | number | Decimal): Money {
    const subtrahend = other instanceof Money ? other._amount : new FinancialDecimal(other);
    return new Money(this._amount.minus(subtrahend), this._currency);
  }

  public multiply(factor: string | number | Decimal): Money {
    const multiplier = new FinancialDecimal(factor);
    return new Money(this._amount.times(multiplier), this._currency);
  }

  public abs(): Money {
    return new Money(this._amount.abs(), this._currency);
  }

  public negate(): Money {
    return new Money(this._amount.negated(), this._currency);
  }

  public equals(other: Money | string | number | Decimal): boolean {
    const val = other instanceof Money ? other._amount : new FinancialDecimal(other);
    return this._amount.equals(val);
  }

  public greaterThan(other: Money | string | number | Decimal): boolean {
    const val = other instanceof Money ? other._amount : new FinancialDecimal(other);
    return this._amount.greaterThan(val);
  }

  public lessThan(other: Money | string | number | Decimal): boolean {
    const val = other instanceof Money ? other._amount : new FinancialDecimal(other);
    return this._amount.lessThan(val);
  }

  public isZero(): boolean {
    return this._amount.isZero();
  }

  public isPositive(): boolean {
    return this._amount.isPositive() && !this._amount.isZero();
  }

  public isNegative(): boolean {
    return this._amount.isNegative();
  }

  /**
   * Returns a fixed-point decimal string matching PostgreSQL NUMERIC(19, 4)
   */
  public toDecimalString(decimals: number = 4): string {
    return this._amount.toFixed(decimals);
  }

  /**
   * Formatted string with currency symbol for display (e.g. "$1,250.00")
   */
  public format(displayDecimals: number = 2): string {
    const formattedNum = Number(this._amount.toFixed(displayDecimals)).toLocaleString("en-US", {
      minimumFractionDigits: displayDecimals,
      maximumFractionDigits: displayDecimals,
    });
    return `${this._currency.symbol}${formattedNum}`;
  }

  public toString(): string {
    return `${this.toDecimalString()} ${this._currency.code}`;
  }
}
