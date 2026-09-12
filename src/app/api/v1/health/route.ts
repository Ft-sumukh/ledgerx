import { NextResponse } from "next/server";
import { DEFAULT_CURRENCY } from "@/core/types/financial";
import { Money } from "@/core/math/money";

export async function GET() {
  // Verify core money math determinism inside healthcheck
  const testA = new Money("0.1");
  const testB = new Money("0.2");
  const testSum = testA.add(testB);
  const isDeterministic = testSum.equals("0.3");

  return NextResponse.json(
    {
      status: "ok",
      service: "ledger-x",
      version: "0.1.0",
      timestamp: new Date().toISOString(),
      environment: process.env.APP_ENV || "development",
      ledger: {
        defaultCurrency: DEFAULT_CURRENCY.code,
        internalPrecision: DEFAULT_CURRENCY.precision,
        mathEngine: "decimal.js (arbitrary-precision)",
        financialInvariantsCheck: isDeterministic ? "PASS" : "FAIL",
      },
    },
    { status: 200 }
  );
}
