import React, { useEffect } from "react";
import { Link } from "react-router-dom";
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from "recharts";
import { Truck, AlertTriangle } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { InstructionBanner, KpiCard, PageTitle, Private, Money, Pill, EmptyState, Pill as StatusPill } from "@/components/Bits";
import { LF, PF, TF, IF, SF, f, LEAD_STATUS_COLORS, LEAD_STATUSES } from "@/lib/fields";
import { fmtMoney, fmtDate, minutesSince, ageLabel, todayISO, isOverdue } from "@/lib/format";

const num = (v) => Number(v) || 0;

export default function Dashboard() {
  const { loadTable, records } = useApp();
  useEffect(() => {
    ["leads", "projects", "tasks", "invoices", "subscriptions"].forEach((t) => loadTable(t));
  }, [loadTable]);

  const leads = records("leads");
  const projects = records("projects");
  const tasks = records("tasks");
  const invoices = records("invoices");
  const subs = records("subscriptions");

  const newLeads = leads.filter((l) => f(l, LF.status) === "New");
  const oldestNewMins = newLeads.length ? Math.max(...newLeads.map((l) => minutesSince(l.createdTime))) : 0;
  const newAlert = newLeads.length > 0 && oldestNewMins > 5;
  const openLeads = leads.filter((l) => !["Lost", "Cold", "Booked"].includes(f(l, LF.status)));
  const pipeline = openLeads.reduce((s, l) => s + num(f(l, LF.quote)), 0);
  const activeProjects = projects.filter((p) => f(p, PF.status) !== "Cancelled");
  const booked = activeProjects.reduce((s, p) => s + (num(f(p, PF.finalRevenue)) || num(f(p, PF.quote))), 0);
  const collected = invoices.filter((i) => f(i, IF.status) === "Paid").reduce((s, i) => s + num(f(i, IF.amount)), 0);
  const outstanding = invoices.filter((i) => ["Sent", "Overdue"].includes(f(i, IF.status))).reduce((s, i) => s + num(f(i, IF.amount)), 0);
  const burn = subs.filter((s) => f(s, SF.status) === "Active").reduce((sum, s) => sum + num(f(s, SF.monthlyCost)), 0);

  const statusData = LEAD_STATUSES.map((st) => ({
    name: st,
    value: leads.filter((l) => f(l, LF.status) === st).length,
  })).filter((d) => d.value > 0);

  const moneyData = [
    { name: "Pipeline", value: pipeline },
    { name: "Booked", value: booked },
    { name: "Collected", value: collected },
    { name: "Owed to us", value: outstanding },
    { name: "Monthly burn", value: burn },
  ];

  const upcoming = projects
    .filter((p) => !["Completed", "Cancelled"].includes(f(p, PF.status)) && (f(p, PF.jobDate) || "") >= todayISO())
    .sort((a, b) => (f(a, PF.jobDate) || "").localeCompare(f(b, PF.jobDate) || ""))
    .slice(0, 5);

  const hotTasks = tasks
    .filter((t) => f(t, TF.priority) === "High" && f(t, TF.status) !== "Done")
    .slice(0, 5);

  return (
    <div data-testid="dashboard-page">
      <PageTitle title="Dashboard" subtitle="Weekend moves, flat price, no surprises." />
      <InstructionBanner>Here's today at a glance. Call any New lead before the timer turns red.</InstructionBanner>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-8">
        <KpiCard
          testId="kpi-new-leads"
          label="New leads to call"
          value={String(newLeads.length)}
          isPrivate={false}
          alert={newAlert}
          sub={newLeads.length ? `Oldest has waited ${ageLabel(oldestNewMins)}` : "All caught up"}
        />
        <KpiCard testId="kpi-open-leads" label="Open leads" value={String(openLeads.length)} isPrivate={false} sub="Still in play" />
        <KpiCard testId="kpi-pipeline" label="Pipeline value" value={fmtMoney(pipeline)} sub="Quotes still open" />
        <KpiCard testId="kpi-booked" label="Booked revenue" value={fmtMoney(booked)} sub="Jobs on the books" />
        <KpiCard testId="kpi-collected" label="Collected" value={fmtMoney(collected)} sub="Paid invoices" />
        <KpiCard testId="kpi-outstanding" label="Owed to us" value={fmtMoney(outstanding)} sub="Sent + overdue invoices" />
        <KpiCard testId="kpi-burn" label="Monthly burn" value={fmtMoney(burn)} sub="Active subscriptions" />
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-white border border-slate-200 rounded-lg p-5">
          <h2 className="font-display font-bold text-lg text-[#1B2A4A] mb-3">Leads by status</h2>
          {statusData.length === 0 ? (
            <EmptyState>No leads yet. Add one from the Leads page.</EmptyState>
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={statusData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                    {statusData.map((d) => (
                      <Cell key={d.name} fill={LEAD_STATUS_COLORS[d.name] || "#9AA3B2"} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="flex flex-wrap gap-2 mt-2">
            {statusData.map((d) => (
              <span key={d.name} className="inline-flex items-center gap-1.5 text-xs text-slate-600">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: LEAD_STATUS_COLORS[d.name] }} />
                {d.name} ({d.value})
              </span>
            ))}
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-lg p-5">
          <h2 className="font-display font-bold text-lg text-[#1B2A4A] mb-3">Money overview</h2>
          <Private block>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={moneyData} margin={{ left: 10, right: 10 }}>
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v >= 1000 ? `${Math.round(v / 1000)}k` : v}`} />
                  <Tooltip formatter={(v) => fmtMoney(v)} />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {moneyData.map((d, i) => (
                      <Cell key={d.name} fill={i % 2 === 0 ? "#1B2A4A" : "#E8743B"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Private>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="bg-white border border-slate-200 rounded-lg p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display font-bold text-lg text-[#1B2A4A]">Upcoming jobs</h2>
            <Link to="/projects" className="text-xs font-semibold text-[#E8743B] hover:underline">See all</Link>
          </div>
          {upcoming.length === 0 ? (
            <EmptyState>No jobs coming up. Book a lead to see it here.</EmptyState>
          ) : (
            <ul className="divide-y divide-slate-100">
              {upcoming.map((p) => (
                <li key={p.id} className="py-2.5 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Truck className="w-4 h-4 text-[#E8743B] shrink-0" />
                    <Private className="text-sm font-medium truncate">{f(p, PF.jobName) || "Job"}</Private>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-slate-500">{fmtDate(f(p, PF.jobDate))}</span>
                    <Pill value={f(p, PF.status)} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="bg-white border border-slate-200 rounded-lg p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display font-bold text-lg text-[#1B2A4A]">High-priority tasks</h2>
            <Link to="/tasks" className="text-xs font-semibold text-[#E8743B] hover:underline">See board</Link>
          </div>
          {hotTasks.length === 0 ? (
            <EmptyState>No urgent tasks. Nice.</EmptyState>
          ) : (
            <ul className="divide-y divide-slate-100">
              {hotTasks.map((t) => (
                <li key={t.id} className="py-2.5 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
                    <span className="text-sm font-medium truncate">{f(t, TF.task)}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {f(t, TF.dueDate) && (
                      <span className={`text-xs ${isOverdue(f(t, TF.dueDate)) ? "text-red-600 font-bold" : "text-slate-500"}`}>
                        {fmtDate(f(t, TF.dueDate))}
                      </span>
                    )}
                    <StatusPill value={f(t, TF.status)} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
