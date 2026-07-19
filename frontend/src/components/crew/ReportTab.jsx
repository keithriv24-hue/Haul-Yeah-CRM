import React, { useCallback, useEffect, useState } from "react";
import dayjs from "dayjs";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { laborReportApi, apiErrorMessage } from "@/lib/api";
import { fmtDate, fmtMoney } from "@/lib/format";
import { Private } from "@/components/Bits";

export const ReportTab = () => {
  const [start, setStart] = useState(() => dayjs().subtract(27, "day").format("YYYY-MM-DD"));
  const [end, setEnd] = useState(() => dayjs().format("YYYY-MM-DD"));
  const [report, setReport] = useState(null);

  const load = useCallback(() => {
    laborReportApi({ start, end }).then(setReport).catch((e) => toast.error(apiErrorMessage(e)));
  }, [start, end]);
  useEffect(() => {
    load();
  }, [load]);

  const t = report?.totals || {};

  return (
    <div className="mt-4 space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <Label className="text-xs">From</Label>
          <Input data-testid="report-start-input" type="date" className="h-9" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div>
          <Label className="text-xs">To</Label>
          <Input data-testid="report-end-input" type="date" className="h-9" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <p className="text-[11px] uppercase tracking-wide text-slate-400">Jobs done</p>
          <p data-testid="report-jobs-completed" className="text-2xl font-bold text-[#1B2A4A]">{t.jobs_completed ?? "—"}</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <p className="text-[11px] uppercase tracking-wide text-slate-400">Crew hours</p>
          <p data-testid="report-total-hours" className="text-2xl font-bold text-[#1B2A4A]">{t.total_hours ?? "—"}</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <p className="text-[11px] uppercase tracking-wide text-slate-400">Labor cost</p>
          <Private><p data-testid="report-labor-cost" className="text-2xl font-bold text-[#1B2A4A]">{t.total_labor_cost != null ? fmtMoney(t.total_labor_cost) : "—"}</p></Private>
        </div>
      </div>

      <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Job</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Hours</TableHead>
              <TableHead>Labor</TableHead>
              <TableHead>Revenue</TableHead>
              <TableHead>Margin</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(report?.jobs || []).map((j) => (
              <TableRow key={j.assignment_id} data-testid="report-job-row">
                <TableCell className="font-medium">{j.job_name}</TableCell>
                <TableCell>{fmtDate(j.job_date)}</TableCell>
                <TableCell><Badge variant="outline" className="text-[10px]">{j.exec_status}</Badge></TableCell>
                <TableCell>{j.hours}</TableCell>
                <TableCell><Private>{fmtMoney(j.labor_cost)}</Private></TableCell>
                <TableCell><Private>{j.revenue != null ? fmtMoney(j.revenue) : "—"}</Private></TableCell>
                <TableCell className={j.margin != null && j.margin < 0 ? "text-red-600 font-bold" : "font-bold"}>
                  <Private>{j.margin != null ? fmtMoney(j.margin) : "—"}</Private>
                </TableCell>
              </TableRow>
            ))}
            {report && report.jobs.length === 0 && (
              <TableRow><TableCell colSpan={7} className="text-center text-slate-400 py-8">No assigned jobs in this range yet.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      {report && (report.unassigned_hours || 0) > 0 && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          {report.unassigned_hours} clocked hours (<Private className="inline">{fmtMoney(report.unassigned_cost)}</Private>) weren't tied to any job — check the Time clock tab.
        </p>
      )}
    </div>
  );
};
