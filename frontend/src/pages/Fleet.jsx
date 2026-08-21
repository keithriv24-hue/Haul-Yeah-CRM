import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Truck, Gauge, ClipboardCheck, AlertTriangle, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageTitle, InstructionBanner } from "@/components/Bits";
import { TruckDetailDialog } from "@/components/fleet/TruckDetailDialog";
import { fleetApi, patchTruckApi, apiErrorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const STATUS_META = {
  in_service: { label: "In service", cls: "bg-success/12 text-success border-success/30" },
  needs_attention: { label: "Needs attention", cls: "bg-warning/12 text-warning border-warning/30" },
  in_shop: { label: "In the shop", cls: "bg-destructive/12 text-destructive border-destructive/30" },
};

const ExpiryChip = ({ label, state, date, testId }) => {
  if (!date) return <span data-testid={testId} className="text-[10px] text-faint">{label}: not set</span>;
  const cls = state === "expired" ? "bg-destructive/12 text-destructive border-destructive/30"
    : state === "soon" ? "bg-warning/12 text-warning border-warning/30"
    : "bg-surface-sunk text-ink-2 border-border-strong";
  return (
    <Badge data-testid={testId} variant="outline" className={`text-[10px] ${cls}`}>
      {label} {state === "expired" ? "EXPIRED" : `exp ${fmtDate(date)}`}
    </Badge>
  );
};

export default function Fleet() {
  const [data, setData] = useState(null);
  const [detailId, setDetailId] = useState(null);

  const load = useCallback(() => fleetApi().then(setData).catch((e) => toast.error(apiErrorMessage(e))), []);
  useEffect(() => {
    load();
  }, [load]);

  const setStatus = async (t, status) => {
    try {
      await patchTruckApi(t.id, { fleet_status: status });
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const trucks = data?.trucks || [];
  const detailTruck = trucks.find((t) => t.id === detailId) || null;

  return (
    <div data-testid="fleet-page" className="pb-8">
      <PageTitle title="Fleet" subtitle="Every truck's health, paperwork, and history in one place." />
      <InstructionBanner testId="fleet-banner">
        Crew file a daily inspection right from their job's Warehouse Departure checklist. Anything they flag lands here and pings your bell. Click a truck for its full file.
      </InstructionBanner>

      {data === null ? (
        <p className="text-sm text-faint">Loading the fleet…</p>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {trucks.map((t) => {
            const st = STATUS_META[t.fleet_status] || STATUS_META.in_service;
            return (
              <div key={t.id} data-testid="fleet-truck-card" className={`bg-surface rounded-lg border p-4 ${t.active ? "border-border" : "border-border opacity-50"}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-bold text-primary flex items-center gap-1.5">
                      <Truck className="w-4 h-4 text-accent-ink" /> {t.name}
                    </p>
                    <p className="text-xs text-faint">{t.plate || "no plate"}{!t.active && " · retired"}</p>
                  </div>
                  <Select value={t.fleet_status} onValueChange={(v) => setStatus(t, v)}>
                    <SelectTrigger data-testid="fleet-status-select" className={`h-7 w-auto gap-1 text-[11px] font-semibold border ${st.cls}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(STATUS_META).map(([k, v]) => (
                        <SelectItem key={k} value={k} className="text-xs">{v.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center gap-3 mt-3 text-xs text-ink-2">
                  <span className="inline-flex items-center gap-1"><Gauge className="w-3.5 h-3.5 text-faint" />
                    {t.mileage ? `${Math.round(t.mileage).toLocaleString()} mi` : "mileage not set"}
                  </span>
                  {t.last_inspection ? (
                    <Badge data-testid="fleet-last-inspection" variant="outline"
                      className={`text-[10px] gap-1 ${t.last_inspection.passed ? "bg-success/10 text-success border-success/25" : "bg-destructive/10 text-destructive border-destructive/25"}`}>
                      <ClipboardCheck className="w-3 h-3" />
                      {t.last_inspection.inspected_today ? "Inspected today" : `Last ${fmtDate(t.last_inspection.date)}`}
                      {t.last_inspection.passed ? "" : " — issues"}
                    </Badge>
                  ) : (
                    <span data-testid="fleet-no-inspection" className="text-[10px] text-faint">never inspected</span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
                  <ExpiryChip label="Reg" state={t.registration_state} date={t.registration?.expires} testId="fleet-reg-chip" />
                  <ExpiryChip label="Ins" state={t.insurance_state} date={t.insurance?.expires} testId="fleet-ins-chip" />
                  {t.open_damage > 0 && (
                    <Badge data-testid="fleet-damage-badge" variant="outline" className="text-[10px] bg-destructive/10 text-destructive border-destructive/30 gap-0.5">
                      <AlertTriangle className="w-2.5 h-2.5" /> {t.open_damage} damage
                    </Badge>
                  )}
                  {t.reminders_due > 0 && (
                    <Badge data-testid="fleet-reminder-badge" variant="outline" className="text-[10px] bg-warning/10 text-warning border-warning/30 gap-0.5">
                      <Wrench className="w-2.5 h-2.5" /> {t.reminders_due} due
                    </Badge>
                  )}
                </div>
                <Button data-testid="fleet-open-truck" variant="outline" size="sm" className="w-full mt-3 text-xs" onClick={() => setDetailId(t.id)}>
                  Open the truck file
                </Button>
              </div>
            );
          })}
          {trucks.length === 0 && (
            <p className="text-sm text-faint col-span-full bg-surface border border-dashed border-border rounded-lg p-8 text-center">
              No trucks yet — add them on the Crew page under Team.
            </p>
          )}
        </div>
      )}

      <TruckDetailDialog truck={detailTruck} onOpenChange={(v) => !v && setDetailId(null)} onChanged={load} />
    </div>
  );
}
