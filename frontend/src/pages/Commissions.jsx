import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Save, Clock, Lock, Ban } from "lucide-react";
import { useAuth } from "@/components/AuthGate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageTitle, InstructionBanner, EmptyState, LoadingRows } from "@/components/Bits";
import { commissionsReportApi, commissionRatesApi, saveCommissionRatesApi, apiErrorMessage } from "@/lib/api";
import { fmtDate, fmtMoneyCents, todayISO } from "@/lib/format";

const STATUS_CHIP = {
  pending: "bg-warning/12 text-warning border-warning/30",
  locked: "bg-success/12 text-success border-success/30",
  voided: "bg-destructive/12 text-destructive border-destructive/30",
};

const iso = (d) => d.toISOString().slice(0, 10);

const PERIODS = {
  this_week: { label: "This week" },
  this_month: { label: "This month" },
  last_month: { label: "Last month" },
  all: { label: "All time" },
};

const periodRange = (key) => {
  const now = new Date();
  if (key === "this_week") {
    const d = new Date(now);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    return { start: iso(d), end: todayISO() };
  }
  if (key === "this_month") return { start: iso(new Date(now.getFullYear(), now.getMonth(), 1)), end: todayISO() };
  if (key === "last_month") {
    return {
      start: iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
      end: iso(new Date(now.getFullYear(), now.getMonth(), 0)),
    };
  }
  return {};
};

const groupKey = (dateStr, mode) => {
  if (mode === "month") return dateStr.slice(0, 7);
  if (mode === "week") {
    const d = new Date(`${dateStr}T12:00:00`);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    return iso(d);
  }
  return dateStr;
};

const groupLabel = (key, mode) => {
  if (mode === "month") {
    const [y, m] = key.split("-");
    return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
  }
  if (mode === "week") return `Week of ${fmtDate(key)}`;
  return fmtDate(key);
};

const RatesEditor = ({ onSaved }) => {
  const [rates, setRates] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    commissionRatesApi().then((d) => setRates(d.rates)).catch(() => {});
  }, []);
  if (!rates) return null;
  const setFlat = (k, v) => setRates((r) => ({ ...r, small_flat: { ...r.small_flat, [k]: v } }));
  const save = async () => {
    setBusy(true);
    try {
      await saveCommissionRatesApi({
        small_flat: Object.fromEntries(Object.entries(rates.small_flat).map(([k, v]) => [k, Number(v) || 0])),
        medium_min: Number(rates.medium_min) || 0,
        medium_pct: Number(rates.medium_pct) || 0,
        big_min: Number(rates.big_min) || 0,
        big_pct: Number(rates.big_pct) || 0,
      });
      toast.success("Rate table saved. New math applies everywhere right away.");
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <div className="surface p-4" data-testid="commission-rates-editor">
      <h2 className="font-bold text-primary mb-1">Rate table <span className="text-xs font-normal text-faint">(only you see this)</span></h2>
      <p className="text-xs text-faint mb-3">
        Small moves (under {fmtMoneyCents(rates.medium_min)}) pay a flat amount by move type. Medium pays {rates.medium_pct}% of the quote. Big ({fmtMoneyCents(rates.big_min)}+) pays {rates.big_pct}%.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {Object.keys(rates.small_flat).map((k) => (
          <div key={k}>
            <Label className="text-xs">{k} flat ($)</Label>
            <Input data-testid={`rate-flat-${k}`} type="number" min="0" value={rates.small_flat[k]} onChange={(e) => setFlat(k, e.target.value)} />
          </div>
        ))}
        <div><Label className="text-xs">Medium starts at ($)</Label><Input data-testid="rate-medium-min" type="number" value={rates.medium_min} onChange={(e) => setRates((r) => ({ ...r, medium_min: e.target.value }))} /></div>
        <div><Label className="text-xs">Medium %</Label><Input data-testid="rate-medium-pct" type="number" value={rates.medium_pct} onChange={(e) => setRates((r) => ({ ...r, medium_pct: e.target.value }))} /></div>
        <div><Label className="text-xs">Big starts at ($)</Label><Input data-testid="rate-big-min" type="number" value={rates.big_min} onChange={(e) => setRates((r) => ({ ...r, big_min: e.target.value }))} /></div>
        <div><Label className="text-xs">Big %</Label><Input data-testid="rate-big-pct" type="number" value={rates.big_pct} onChange={(e) => setRates((r) => ({ ...r, big_pct: e.target.value }))} /></div>
      </div>
      <Button data-testid="rates-save-btn" size="sm" className="mt-3 gap-1.5 bg-primary hover:bg-[#26395f]" disabled={busy} onClick={save}>
        <Save className="w-4 h-4" /> Save rates
      </Button>
    </div>
  );
};

export default function Commissions() {
  const { role } = useAuth();
  const isOwner = role === "owner";
  const [period, setPeriod] = useState("this_month");
  const [groupBy, setGroupBy] = useState("week");
  const [data, setData] = useState(null);

  const load = useCallback(() => {
    commissionsReportApi(periodRange(period)).then(setData).catch(() => setData({ rows: [], reps: [] }));
  }, [period]);
  useEffect(() => {
    load();
  }, [load]);

  const rows = data?.rows || [];
  const groups = rows.reduce((acc, r) => {
    const k = groupKey(r.earn_date, groupBy);
    (acc[k] = acc[k] || []).push(r);
    return acc;
  }, {});

  return (
    <div data-testid="commissions-page" className="space-y-4">
      <PageTitle title="Commissions" subtitle={isOwner ? "Every rep's earnings — pending until fully paid, then locked." : "Your earnings — pending until the customer fully pays, then locked."} />
      <InstructionBanner testId="commissions-banner">
        Set "Closed by" on a lead's page to start a commission. It shows as pending once the deposit is in, locks when the job is fully paid, and voids if it's refunded.
      </InstructionBanner>

      <div className="flex flex-wrap gap-3">
        <div>
          <Label className="text-xs">Period</Label>
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger data-testid="commissions-period-select" className="w-[150px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              {Object.entries(PERIODS).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">Group by</Label>
          <Select value={groupBy} onValueChange={setGroupBy}>
            <SelectTrigger data-testid="commissions-group-select" className="w-[130px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="day">Day</SelectItem>
              <SelectItem value="week">Week</SelectItem>
              <SelectItem value="month">Month</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {data === null ? (
        <LoadingRows />
      ) : (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="commissions-rep-cards">
            {(data.reps || []).map((r) => (
              <div key={r.user_id} data-testid="rep-total-card" className="surface p-4">
                <p className="font-display font-bold text-primary">{r.name}</p>
                <div className="flex items-end gap-4 mt-2">
                  <div>
                    <p className="text-[10px] font-bold uppercase text-warning flex items-center gap-1"><Clock className="w-3 h-3" /> Pending</p>
                    <p className="font-display font-extrabold text-xl text-warning">{fmtMoneyCents(r.pending)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold uppercase text-success flex items-center gap-1"><Lock className="w-3 h-3" /> Locked</p>
                    <p className="font-display font-extrabold text-xl text-success">{fmtMoneyCents(r.locked)}</p>
                  </div>
                  <p className="ml-auto text-xs text-faint">{r.jobs} job{r.jobs === 1 ? "" : "s"}</p>
                </div>
              </div>
            ))}
            {(data.reps || []).length === 0 && (
              <EmptyState>No commissions in this period yet. Close a move, mark the deposit paid, and it lands here.</EmptyState>
            )}
          </div>

          {Object.keys(groups).sort().reverse().map((k) => {
            const list = groups[k];
            const pending = list.filter((r) => r.status === "pending").reduce((s, r) => s + r.commission, 0);
            const locked = list.filter((r) => r.status === "locked").reduce((s, r) => s + r.commission, 0);
            return (
              <div key={k} className="surface" data-testid="commissions-group">
                <div className="flex flex-wrap items-center gap-3 px-4 py-2.5 border-b border-border bg-surface-sunk/60 rounded-t-lg">
                  <span className="font-bold text-primary text-sm">{groupLabel(k, groupBy)}</span>
                  <span className="text-xs font-semibold text-warning">{fmtMoneyCents(pending)} pending</span>
                  <span className="text-xs font-semibold text-success">{fmtMoneyCents(locked)} locked</span>
                </div>
                <div className="divide-y divide-border">
                  {list.map((r) => (
                    <div key={r.lead_id + r.earn_date} data-testid="commission-row" className={`flex flex-wrap items-center gap-2 px-4 py-2.5 text-sm ${r.status === "voided" ? "opacity-60" : ""}`}>
                      <span className="text-xs text-faint w-16">{fmtDate(r.earn_date)}</span>
                      <span className={`font-semibold text-primary flex-1 min-w-[120px] truncate ${r.status === "voided" ? "line-through" : ""}`}>{r.lead_name || "Unnamed lead"}</span>
                      {isOwner && <span className="text-xs text-faint w-28 truncate">{r.closed_by_name}</span>}
                      <span className="text-xs text-faint w-24">{r.move_type || "—"}</span>
                      <span className="text-xs text-faint w-20 text-right">{fmtMoneyCents(r.quote_amount)}</span>
                      <span className={`font-display font-bold w-20 text-right ${r.status === "voided" ? "line-through text-faint" : "text-primary"}`}>{fmtMoneyCents(r.commission)}</span>
                      <span className={`border rounded-full px-2 py-0.5 text-[10px] font-bold capitalize ${STATUS_CHIP[r.status]}`}>
                        {r.status === "voided" ? <Ban className="w-3 h-3 inline mr-0.5 -mt-0.5" /> : null}{r.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}

          {isOwner && <RatesEditor onSaved={load} />}
        </>
      )}
    </div>
  );
}
