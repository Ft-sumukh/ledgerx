import { ShieldCheck, Scale, History, KeyRound, Cpu, Layers } from "lucide-react";

export default function Home() {
  const invariants = [
    {
      icon: Scale,
      title: "Double-Entry Invariant",
      desc: "Total Debits = Total Credits. Every financial transaction posted must strictly balance to zero fractional error.",
    },
    {
      icon: History,
      title: "Immutable History",
      desc: "Posted transactions cannot be modified or deleted. Corrections are recorded via explicit reversal entries.",
    },
    {
      icon: KeyRound,
      title: "Deterministic Precision",
      desc: "Zero floating-point arithmetic. Stored and calculated with arbitrary-precision fixed-point math.",
    },
    {
      icon: ShieldCheck,
      title: "Multi-Tenant Isolation",
      desc: "Strict tenant isolation enforced at the database and data-access layer. Zero cross-organization leakage.",
    },
    {
      icon: Cpu,
      title: "Idempotent Operations",
      desc: "Financial mutation APIs require idempotency keys to guarantee duplicate requests never double-post entries.",
    },
    {
      icon: Layers,
      title: "Append-Only Audit Trail",
      desc: "Every critical system mutation records who, what, when, why, before-state, and after-state forever.",
    },
  ];

  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-8 md:p-16">
      <div className="z-10 w-full max-w-6xl items-center justify-between text-sm">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-6 mb-12">
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-lg bg-gradient-to-tr from-brand-600 to-emerald-500 flex items-center justify-center font-bold text-white shadow-lg shadow-brand-500/20">
              LX
            </div>
            <span className="text-xl font-bold tracking-tight text-white">
              LEDGER<span className="text-brand-400">-X</span>
            </span>
          </div>
          <div className="flex items-center space-x-4">
            <span className="inline-flex items-center rounded-md bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400 ring-1 ring-inset ring-emerald-500/20">
              ● System Active • Part 1 Foundation
            </span>
            <a
              href="/api/v1/health"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-slate-400 hover:text-white transition-colors underline underline-offset-4"
            >
              API Healthcheck
            </a>
          </div>
        </div>

        {/* Hero */}
        <div className="mb-16 max-w-3xl">
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-white mb-4">
            Enterprise Digital Ledger & Financial System of Record
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            Engineered for deterministic financial correctness, double-entry integrity, multi-tenant security,
            and comprehensive auditability.
          </p>
        </div>

        {/* Invariant Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-16">
          {invariants.map((item, index) => {
            const Icon = item.icon;
            return (
              <div
                key={index}
                className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur transition-all hover:border-slate-700 hover:bg-slate-900/80"
              >
                <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800 text-brand-400 ring-1 ring-slate-700">
                  <Icon className="h-5 w-5" />
                </div>
                <h2 className="text-lg font-semibold text-white mb-2">{item.title}</h2>
                <p className="text-sm text-slate-400 leading-relaxed">{item.desc}</p>
              </div>
            );
          })}
        </div>

        {/* Architecture Status Footer */}
        <div className="rounded-xl border border-slate-800/80 bg-slate-950/50 p-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-200">Phase 1: Project Foundation Ready</h3>
            <p className="text-xs text-slate-400">TypeScript strict mode, Next.js App Router, Decimal.js financial core, and git remote origin configured.</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-slate-400 bg-slate-900 px-3 py-1.5 rounded border border-slate-800">
              Branch: main
            </span>
          </div>
        </div>
      </div>
    </main>
  );
}
