import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, ShieldAlert, CheckCircle2, AlertTriangle, XCircle, Lock, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { getJobComplianceApi, saveJobComplianceApi, overrideJobComplianceApi, apiErrorMessage } from "@/lib/api";

const SEV_ORDER = ["Liability risk", "Regulatory", "Major", "Minor"];

const INPUTS = [
  { k: "move_classification", label: "Move classification", type: "select", opts: ["Household Goods", "Office Goods Only", "Other Commercial"] },
  { k: "survey_type", label: "Survey type", type: "select", opts: ["On site", "Video", "None"] },
  { k: "survey_date", label: "Survey date", type: "date" },
  { k: "inventory_complete", label: "Inventory complete", type: "checkbox" },
  { k: "brochure_sent_at", label: "Brochure sent", type: "datetime" },
  { k: "estimate_delivered_at", label: "Estimate delivered", type: "datetime" },
  { k: "ofs_signed_at", label: "Order for Service signed", type: "datetime" },
  { k: "short_notice_proof", label: "Short-notice proof", type: "textarea", placeholder: "The written evidence the customer requested service inside 24h — the email or quote, what they said and when, a link to the thread." },
  { k: "protection_option", label: "Protection option", type: "select", opts: ["Option 1", "Option 2", "Option 3"] },
  { k: "declared_value", label: "Declared value ($)", type: "number" },
  { k: "deductible", label: "Deductible ($)", type: "number" },
  { k: "owner_operator_used", label: "Owner-operator used", type: "checkbox" },
  { k: "owner_operator_notice_at", label: "Owner-operator notice sent", type: "datetime" },
  { k: "labor_equipment_change_agreed", label: "Labor/equipment change", type: "select", opts: ["None", "Agreed in writing", "Not agreed"] },
  { k: "one_way_miles", label: "One-way miles", type: "number" },
  { k: "long_haul_owner_ack", label: "Long-haul acknowledged", type: "checkbox", ownerOnly: true },
];

const toLocalInput = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};
const fromLocalInput = (v) => (v ? new Date(v).toISOString() : null);

const gateTone = (g) => {
  if (g.exempt) return "muted";
  if (g.passed) return "green";
  return g.severity === "Liability risk" || g.severity === "Regulatory" ? "red" : "amber";
};

const GateRow = ({ g }) => {
  const tone = gateTone(g);
  const Icon = tone === "green" || tone === "muted" ? CheckCircle2 : tone === "amber" ? AlertTriangle : XCircle;
  const color = tone === "green" ? "text-emerald-600" : tone === "amber" ? "text-amber-600" : tone === "red" ? "text-red-600" : "text-faint";
  return (
    <div data-testid={`gate-${g.key}`} data-passed={g.passed} className="flex items-start gap-2 py-1">
      <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${color}`} aria-hidden="true" />
      <div className="min-w-0">
        <div className="text-[13px] font-semibold text-ink">{g.label}{g.exempt ? " — exempt" : ""}</div>
        {!g.passed && g.reason && <div className="text-[12px] text-faint">{g.reason}</div>}
      </div>
    </div>
  );
};

const OverrideDialog = ({ open, onOpenChange, projectId, failing, onDone }) => {
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const hasLiability = failing.some((g) => g.severity === "Liability risk");
  useEffect(() => { if (open) { setReason(""); setConfirm(""); } }, [open]);
  const submit = async () => {
    if (reason.trim().length < 20) { toast.error("Give a written reason of at least 20 characters."); return; }
    if (confirm !== "OVERRIDE") { toast.error("Type OVERRIDE to confirm."); return; }
    setSaving(true);
    try {
      const data = await overrideJobComplianceApi(projectId, reason.trim(), confirm);
      toast.success("Override recorded — a nonconformance was opened. Failing gates stay red.");
      onOpenChange(false);
      onDone && onDone(data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    setSaving(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="override-modal" className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><ShieldAlert className="w-5 h-5 text-red-600" /> Override failing gates</DialogTitle>
          <DialogDescription>The job still books. This is recorded as a nonconformance. The failed gates stay red.</DialogDescription>
        </DialogHeader>
        <div className="rounded-lg border border-red-200 bg-red-50 p-2.5 mb-2">
          <div className="text-[12px] font-bold text-red-700 mb-1">Still failing ({failing.length})</div>
          <ul className="text-[12px] text-red-700 list-disc pl-4 space-y-0.5">
            {failing.map((g) => <li key={g.key}>{g.label} <span className="opacity-70">({g.severity})</span></li>)}
          </ul>
        </div>
        <div data-testid="override-consequence" className="rounded-lg border border-amber-300 bg-amber-50 p-2.5 mb-2 text-[12.5px] leading-snug text-amber-900">
          An override does not make this job compliant. The failed checks stay on the record and stay visible. This opens a nonconformance and is logged against your name.
          {hasLiability && (
            <div data-testid="override-liability-warning" className="mt-2 pt-2 border-t border-amber-300 font-semibold text-red-700">
              This gate protects our $1.00-per-pound limit of liability. Overriding it may expose the company to replacement-value damages on a claim.
            </div>
          )}
        </div>
        <Label className="text-[12px]">Written reason (20+ characters)</Label>
        <Textarea data-testid="override-reason-input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        <Label className="text-[12px] mt-2">Type OVERRIDE to confirm</Label>
        <Input data-testid="override-confirm-input" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="OVERRIDE" />
        <Button data-testid="override-submit-btn" onClick={submit} disabled={saving} className="w-full mt-3 gap-2 bg-red-600 hover:bg-red-700 text-white">
          <ShieldAlert className="w-4 h-4" /> {saving ? "Recording…" : "Record override"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

export const ComplianceSection = ({ projectId, canEdit, canOverride }) => {
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [ovOpen, setOvOpen] = useState(false);

  const hydrate = useCallback((d) => {
    setData(d);
    const f = {};
    for (const inp of INPUTS) {
      const v = d.inputs?.[inp.k];
      f[inp.k] = inp.type === "datetime" ? toLocalInput(v) : inp.type === "checkbox" ? !!v : (v ?? "");
    }
    setForm(f);
  }, []);

  const load = useCallback(async () => {
    setState("loading");
    try { hydrate(await getJobComplianceApi(projectId)); setState("ok"); }
    catch (e) { setState("error"); setData({ error: apiErrorMessage(e) }); }
  }, [projectId, hydrate]);

  useEffect(() => { load(); }, [load]);

  const setField = (k, v) => setForm((s) => ({ ...s, [k]: v }));

  const save = async () => {
    setSaving(true);
    const inputs = {};
    for (const inp of INPUTS) {
      if (inp.ownerOnly && !canOverride) continue;
      const v = form[inp.k];
      if (inp.type === "checkbox") inputs[inp.k] = !!v;
      else if (inp.type === "number") inputs[inp.k] = v === "" || v == null ? null : Number(v);
      else if (inp.type === "datetime") inputs[inp.k] = fromLocalInput(v);
      else inputs[inp.k] = v === "" ? null : v;
    }
    try { hydrate(await saveJobComplianceApi(projectId, inputs)); toast.success("Compliance saved."); }
    catch (e) { toast.error(apiErrorMessage(e)); }
    setSaving(false);
  };

  if (state === "loading") return <div className="mt-4 pt-4 border-t border-border text-[13px] text-faint">Loading compliance…</div>;
  if (state === "error") return <div className="mt-4 pt-4 border-t border-border text-[13px] text-faint" data-testid="compliance-error">{data?.error || "Couldn't load compliance."}</div>;

  const gates = data.gates || [];
  const summary = data.summary || {};
  const failing = gates.filter((g) => !g.passed);
  const override = data.override;

  return (
    <div className="mt-4 pt-4 border-t border-border" data-testid="compliance-section">
      <div className="flex items-center gap-2 mb-3">
        {summary.all_green ? <ShieldCheck className="w-5 h-5 text-emerald-600" /> : <ShieldAlert className="w-5 h-5 text-red-600" />}
        <h3 className="font-display font-bold text-[15px] text-primary">Compliance</h3>
        <span data-testid="compliance-status" className={`ml-1 rounded-md px-2 py-0.5 text-[11px] font-bold ${summary.all_green ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
          {summary.all_green ? "All gates green" : `${summary.failing} failing`}
        </span>
      </div>

      {override && (
        <div data-testid="override-banner" className="mb-3 rounded-lg border border-red-300 bg-red-50 p-2.5 text-[12.5px] text-red-700">
          <div className="font-bold flex items-center gap-1.5"><ShieldAlert className="w-4 h-4" /> Overridden by {override.by} · {new Date(override.at).toLocaleDateString("en-US")}</div>
          <div className="mt-0.5">{override.reason}</div>
          <div className="mt-0.5 opacity-80">Failed gates remain red on purpose — the override is the record, not a fix.</div>
        </div>
      )}

      {/* Panel: grouped by severity, liability first */}
      <div className="grid gap-3 md:grid-cols-2">
        {SEV_ORDER.map((sev) => {
          const inSev = gates.filter((g) => g.severity === sev);
          if (!inSev.length) return null;
          return (
            <div key={sev} className={`rounded-lg border p-2.5 ${sev === "Liability risk" ? "border-red-200 bg-red-50/40 md:col-span-2" : "border-border bg-surface-sunk"}`}>
              <div className={`text-[11px] font-bold uppercase tracking-wide mb-1 ${sev === "Liability risk" ? "text-red-700" : "text-faint"}`}>
                {sev === "Liability risk" ? "Liability risk — voids the $1/lb cap" : sev}
              </div>
              <div className={sev === "Liability risk" ? "grid md:grid-cols-3 gap-x-4" : ""}>
                {inSev.map((g) => <GateRow key={g.key} g={g} />)}
              </div>
            </div>
          );
        })}
      </div>

      {canOverride && failing.length > 0 && (
        <div className="mt-3">
          <Button data-testid="open-override-btn" variant="outline" onClick={() => setOvOpen(true)} className="gap-1.5 border-red-300 text-red-700 hover:bg-red-50">
            <ShieldAlert className="w-4 h-4" /> Override {failing.length} failing gate{failing.length > 1 ? "s" : ""}
          </Button>
          <OverrideDialog open={ovOpen} onOpenChange={setOvOpen} projectId={projectId} failing={failing} onDone={hydrate} />
        </div>
      )}

      {/* Gate-input form (owner + sales) */}
      {canEdit ? (
        <div className="mt-4" data-testid="compliance-form">
          <div className="text-[11px] font-bold uppercase tracking-wide text-faint mb-2">Gate inputs</div>
          <div className="grid gap-3 sm:grid-cols-2">
            {INPUTS.map((inp) => {
              const disabled = inp.ownerOnly && !canOverride;
              const testId = `ci-${inp.k.replace(/_/g, "-")}`;
              if (inp.type === "checkbox") {
                return (
                  <label key={inp.k} className="flex items-center gap-2 text-[13px] text-ink">
                    <Checkbox data-testid={testId} checked={!!form[inp.k]} disabled={disabled} onCheckedChange={(v) => setField(inp.k, !!v)} />
                    {inp.label}{disabled && <Lock className="w-3 h-3 text-faint" title="Owner only" />}
                  </label>
                );
              }
              return (
                <div key={inp.k} className={inp.type === "textarea" ? "sm:col-span-2" : ""}>
                  <Label className="text-[12px] flex items-center gap-1">{inp.label}{disabled && <Lock className="w-3 h-3 text-faint" />}</Label>
                  {inp.type === "select" ? (
                    <Select value={form[inp.k] || ""} onValueChange={(v) => setField(inp.k, v)} disabled={disabled}>
                      <SelectTrigger data-testid={testId} className="h-9"><SelectValue placeholder="Choose…" /></SelectTrigger>
                      <SelectContent>{inp.opts.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
                    </Select>
                  ) : inp.type === "textarea" ? (
                    <Textarea data-testid={testId} rows={2} value={form[inp.k] || ""} placeholder={inp.placeholder} disabled={disabled} onChange={(e) => setField(inp.k, e.target.value)} />
                  ) : (
                    <Input
                      data-testid={testId}
                      type={inp.type === "datetime" ? "datetime-local" : inp.type}
                      value={form[inp.k] ?? ""}
                      disabled={disabled}
                      onChange={(e) => setField(inp.k, e.target.value)}
                      className="h-9"
                    />
                  )}
                </div>
              );
            })}
          </div>
          <Button data-testid="compliance-save-btn" onClick={save} disabled={saving} className="mt-3 gap-2 bg-accent hover:bg-accent-press">
            <Save className="w-4 h-4" /> {saving ? "Saving…" : "Save compliance"}
          </Button>
        </div>
      ) : (
        <div className="mt-3 text-[12px] text-faint">Read-only — only the owner and sales can edit these fields.</div>
      )}
    </div>
  );
};
