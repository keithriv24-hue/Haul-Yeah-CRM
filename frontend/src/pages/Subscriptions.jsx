import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { InstructionBanner, PageTitle, Money, KpiCard, EmptyState, LoadingRows, SearchBar, searchMatch } from "@/components/Bits";
import { SF, f, SUB_CATEGORIES, SUB_STATUSES, STATUS_PILL } from "@/lib/fields";
import { fmtDate, fmtMoney, daysUntil } from "@/lib/format";

const blank = { name: "", category: "Software", monthlyCost: "", billingCycle: "Monthly", nextRenewal: "", status: "Active" };
const num = (v) => Number(v) || 0;

export default function Subscriptions() {
  const { loadTable, records, tableState, updateRecord, createRecord } = useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    loadTable("subscriptions");
  }, [loadTable]);

  const allSubs = [...records("subscriptions")].sort((a, b) => (f(a, SF.nextRenewal) || "9999").localeCompare(f(b, SF.nextRenewal) || "9999"));
  const subs = allSubs.filter((s) => searchMatch(query, f(s, SF.name), f(s, SF.category), f(s, SF.status), f(s, SF.billingCycle)));
  const { loading, error } = tableState("subscriptions");
  const burn = allSubs.filter((s) => f(s, SF.status) === "Active").reduce((sum, s) => sum + num(f(s, SF.monthlyCost)), 0);

  const set = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));

  const save = async () => {
    if (!form.name.trim() || !form.monthlyCost) {
      toast.error("Add the name and monthly cost first.");
      return;
    }
    setSaving(true);
    try {
      await createRecord("subscriptions", {
        [SF.name]: form.name.trim(),
        [SF.category]: form.category,
        [SF.monthlyCost]: Number(form.monthlyCost),
        [SF.billingCycle]: form.billingCycle,
        [SF.nextRenewal]: form.nextRenewal,
        [SF.status]: form.status,
      });
      toast.success("Subscription saved.");
      setForm(blank);
      setModalOpen(false);
    } catch {}
    setSaving(false);
  };

  return (
    <div data-testid="subscriptions-page">
      <PageTitle
        title="Subscriptions"
        subtitle="What the business pays for each month."
        action={
          <Button data-testid="new-sub-btn" onClick={() => setModalOpen(true)} className="gap-1.5 bg-accent hover:bg-accent-press">
            <Plus className="w-4 h-4" /> New subscription
          </Button>
        }
      />
      <InstructionBanner>Everything you pay for each month. Cancel what you don't use — renewal dates in red are less than a week away.</InstructionBanner>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <KpiCard testId="kpi-monthly-burn" label="Monthly burn (active)" value={fmtMoney(burn)} />
        <KpiCard testId="kpi-annual-burn" label="Per year" value={fmtMoney(burn * 12)} sub="Monthly burn × 12" />
      </div>

      <div className="mb-4">
        <SearchBar value={query} onChange={setQuery} placeholder="Search subscriptions…" testId="subs-search-input" />
      </div>

      {loading && !allSubs.length ? (
        <LoadingRows />
      ) : error && !allSubs.length ? (
        <EmptyState>{error}</EmptyState>
      ) : subs.length === 0 ? (
        <EmptyState>{query ? "No subscriptions match that search." : "No subscriptions tracked yet."}</EmptyState>
      ) : (
        <div className="surface overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="hidden sm:table-cell">Category</TableHead>
                <TableHead>Monthly</TableHead>
                <TableHead className="hidden sm:table-cell">Cycle</TableHead>
                <TableHead>Next renewal</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {subs.map((s) => {
                const status = f(s, SF.status) || "Active";
                const dleft = daysUntil(f(s, SF.nextRenewal));
                const soon = dleft !== null && dleft <= 7 && status === "Active";
                return (
                  <TableRow key={s.id} data-testid="subscription-row">
                    <TableCell className="font-semibold">{f(s, SF.name) || "—"}</TableCell>
                    <TableCell className="hidden sm:table-cell text-xs text-faint">{f(s, SF.category) || "—"}</TableCell>
                    <TableCell className="font-bold text-primary"><Money value={f(s, SF.monthlyCost)} /></TableCell>
                    <TableCell className="hidden sm:table-cell text-xs text-faint">{f(s, SF.billingCycle) || "—"}</TableCell>
                    <TableCell className={`text-xs ${soon ? "text-destructive font-bold" : "text-faint"}`}>
                      {fmtDate(f(s, SF.nextRenewal))}{soon && " (soon)"}
                    </TableCell>
                    <TableCell>
                      <Select value={status} onValueChange={(v) => updateRecord("subscriptions", s.id, { [SF.status]: v }).catch(() => {})}>
                        <SelectTrigger data-testid="sub-status-select" className={`w-[140px] h-8 text-xs font-semibold border ${STATUS_PILL[status] || ""}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>{SUB_STATUSES.map((st) => <SelectItem key={st} value={st}>{st}</SelectItem>)}</SelectContent>
                      </Select>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent data-testid="new-sub-modal" className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-display">New subscription</DialogTitle>
            <DialogDescription>Track it so it never surprises you.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>Name *</Label>
              <Input data-testid="sub-name-input" value={form.name} onChange={set("name")} placeholder="QuickBooks" />
            </div>
            <div>
              <Label>Category</Label>
              <Select value={form.category} onValueChange={(v) => setForm((s) => ({ ...s, category: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{SUB_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Monthly cost ($) *</Label>
              <Input data-testid="sub-cost-input" type="number" min="0" step="0.01" value={form.monthlyCost} onChange={set("monthlyCost")} />
            </div>
            <div>
              <Label>Billing cycle</Label>
              <Input value={form.billingCycle} onChange={set("billingCycle")} placeholder="Monthly" />
            </div>
            <div>
              <Label>Next renewal</Label>
              <Input type="date" value={form.nextRenewal} onChange={set("nextRenewal")} />
            </div>
          </div>
          <Button data-testid="sub-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-accent hover:bg-accent-press">
            <Plus className="w-4 h-4" /> {saving ? "Saving…" : "Save subscription"}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
