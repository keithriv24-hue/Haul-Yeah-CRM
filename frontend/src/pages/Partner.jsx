import React, { useEffect } from "react";
import { Handshake } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { InstructionBanner, PageTitle, KpiCard } from "@/components/Bits";
import { LF, PF, IF, SF, f } from "@/lib/fields";
import { fmtMoney } from "@/lib/format";

const num = (v) => Number(v) || 0;

export default function Partner() {
  const { loadTable, records } = useApp();
  useEffect(() => {
    ["leads", "projects", "invoices", "subscriptions"].forEach((t) => loadTable(t));
  }, [loadTable]);

  const leads = records("leads");
  const projects = records("projects").filter((p) => f(p, PF.status) !== "Cancelled");
  const invoices = records("invoices");
  const subs = records("subscriptions");

  const booked = projects.reduce((s, p) => s + (num(f(p, PF.finalRevenue)) || num(f(p, PF.quote))), 0);
  const collected = invoices.filter((i) => f(i, IF.status) === "Paid").reduce((s, i) => s + num(f(i, IF.amount)), 0);
  const receivables = invoices.filter((i) => ["Sent", "Overdue"].includes(f(i, IF.status))).reduce((s, i) => s + num(f(i, IF.amount)), 0);
  const opex = subs.filter((s) => f(s, SF.status) === "Active").reduce((sum, s) => sum + num(f(s, SF.monthlyCost)), 0);
  const pipeline = leads
    .filter((l) => !["Lost", "Booked", "Cold"].includes(f(l, LF.status)))
    .reduce((s, l) => s + num(f(l, LF.quote)), 0);
  const avgJob = projects.length ? Math.round(booked / projects.length) : 0;

  return (
    <div data-testid="partner-page">
      <PageTitle title="Partner View" subtitle="The money picture, nothing personal." />
      <InstructionBanner>A money summary you can share with our capital partner. No customer names or lead details show here.</InstructionBanner>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        <KpiCard testId="partner-booked" label="Booked revenue" value={fmtMoney(booked)} sub="Jobs on the books" />
        <KpiCard testId="partner-collected" label="Collected" value={fmtMoney(collected)} sub="Paid invoices" />
        <KpiCard testId="partner-receivables" label="Receivables" value={fmtMoney(receivables)} sub="Billed, not yet paid" />
        <KpiCard testId="partner-opex" label="Monthly opex" value={fmtMoney(opex)} sub="Active subscriptions" />
        <KpiCard testId="partner-pipeline" label="Pipeline" value={fmtMoney(pipeline)} sub="Open quotes" />
        <KpiCard testId="partner-avg-job" label="Average job value" value={fmtMoney(avgJob)} sub={`${projects.length} active jobs`} />
      </div>

      <div className="border border-primary/15 bg-surface rounded-lg p-6 flex items-start gap-3">
        <Handshake className="w-6 h-6 text-accent-ink shrink-0" />
        <div className="text-sm text-ink-2">
          <p className="font-semibold text-primary mb-1">How to read this page</p>
          <p>
            Booked revenue is work we've won. Collected is cash in hand. Receivables is money on the way.
            Pipeline is what we're still chasing. This page is read-only — nothing here can change the books.
          </p>
        </div>
      </div>
    </div>
  );
}
