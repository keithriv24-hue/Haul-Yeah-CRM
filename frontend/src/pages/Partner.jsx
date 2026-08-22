import React, { useEffect, useState } from "react";
import { Handshake } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { InstructionBanner, PageTitle, KpiCard } from "@/components/Bits";
import { LF, SF, f } from "@/lib/fields";
import { fmtMoney } from "@/lib/format";
import { moneySummaryApi } from "@/lib/api";

const num = (v) => Number(v) || 0;

export default function Partner() {
  const { loadTable, records, tableState } = useApp();
  const [money, setMoney] = useState(null);
  useEffect(() => {
    ["leads", "subscriptions"].forEach((t) => loadTable(t));
    moneySummaryApi()
      .then(setMoney)
      .catch(() => setMoney({ booked_total: 0, collected_total: 0, outstanding_total: 0, jobs_count: 0 }));
  }, [loadTable]);

  const leads = records("leads");
  const subs = records("subscriptions");
  const subsLoading = tableState("subscriptions").loading && !subs.length;

  const opex = subs.filter((s) => f(s, SF.status) === "Active").reduce((sum, s) => sum + num(f(s, SF.monthlyCost)), 0);
  const pipeline = leads
    .filter((l) => !["Lost", "Booked", "Cold"].includes(f(l, LF.status)))
    .reduce((s, l) => s + num(f(l, LF.quote)), 0);
  const avgJob = money?.jobs_count ? Math.round(money.booked_total / money.jobs_count) : 0;
  const m = (v) => (money ? fmtMoney(v || 0) : "—");

  return (
    <div data-testid="partner-page">
      <PageTitle title="Partner View" subtitle="The money picture, nothing personal." />
      <InstructionBanner>A money summary you can share with our capital partner. Every dollar comes straight from Square — the same numbers the owner dashboard shows.</InstructionBanner>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        <KpiCard testId="partner-booked" label="Booked revenue" value={m(money?.booked_total)} sub="Deposit-backed jobs (Square)" />
        <KpiCard testId="partner-collected" label="Collected" value={m(money?.collected_total)} sub="Paid Square invoices" />
        <KpiCard testId="partner-receivables" label="Receivables" value={m(money?.outstanding_total)} sub="Balances still due (Square)" />
        <KpiCard testId="partner-opex" label="Monthly opex" value={subsLoading ? "—" : fmtMoney(opex)} sub="Active subscriptions" />
        <KpiCard testId="partner-pipeline" label="Pipeline" value={fmtMoney(pipeline)} sub="Open quotes" />
        <KpiCard testId="partner-avg-job" label="Average job value" value={money ? fmtMoney(avgJob) : "—"} sub={`${money?.jobs_count || 0} booked jobs`} />
      </div>

      <div className="border border-primary/15 bg-surface rounded-lg p-6 flex items-start gap-3">
        <Handshake className="w-6 h-6 text-accent-ink shrink-0" />
        <div className="text-sm text-ink-2">
          <p className="font-semibold text-primary mb-1">How to read this page</p>
          <p>
            Booked revenue is deposit-backed work we've won. Collected is cash that actually landed in Square.
            Receivables is money still on the way. Pipeline is what we're still chasing.
            This page is read-only — nothing here can change the books.
          </p>
        </div>
      </div>
    </div>
  );
}
