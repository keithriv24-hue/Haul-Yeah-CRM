import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Save, Link2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { getPortalSettingsApi, savePortalSettingsApi, apiErrorMessage } from "@/lib/api";

const TPL = [
  { key: "booked", label: "Booked", hint: "Right after the deposit is paid." },
  { key: "move_day", label: "Move day", hint: "Auto-sent when the first crew clocks in." },
  { key: "wrap_up", label: "Wrap-up", hint: "After the move — receipt, tip, review." },
  { key: "reminder", label: "T-48h reminder", hint: "Auto-sent ~2 days before the move. Use {arrival_window} & {paperwork_line}." },
];

const VARS = "{first_name} · {move_date} · {arrival_window} · {start_time} · {link} · {job_number} · {business_phone} · {paperwork_line}";

export const CustomerPageCard = () => {
  const [f, setF] = useState(null);
  const [saving, setSaving] = useState(false);
  const [warning, setWarning] = useState("");

  useEffect(() => {
    getPortalSettingsApi().then(setF).catch((e) => toast.error(apiErrorMessage(e)));
  }, []);

  if (!f) return null;
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const setTpl = (k) => (e) => setF((s) => ({ ...s, templates: { ...s.templates, [k]: e.target.value } }));

  const save = async () => {
    setSaving(true);
    setWarning("");
    try {
      const res = await savePortalSettingsApi({
        portal_base_url: f.portal_base_url || "",
        business_phone: f.business_phone || "",
        license_number: f.license_number || "",
        brochure_url: f.brochure_url || "",
        arrival_window_minutes: Number(f.arrival_window_minutes ?? 30),
        templates: f.templates || {},
      });
      setF(res);
      if (res.warning) setWarning(res.warning);
      toast.success("Customer page settings saved.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };

  return (
    <div data-testid="customer-page-settings" className="surface p-4 mb-4">
      <p className="font-display text-[15px] font-bold text-primary flex items-center gap-1.5 mb-1">
        <Link2 className="w-4 h-4 text-accent-ink" /> Customer page
      </p>
      <p className="text-xs text-faint mb-3">The public move page customers get by text. No login — the link is the key.</p>

      <div className="space-y-3">
        <div>
          <Label>Customer page base URL</Label>
          <Input data-testid="portal-base-url-input" type="url" placeholder="https://yourmovepage.com"
            value={f.portal_base_url || ""} onChange={set("portal_base_url")} />
          <p className="text-[11px] text-faint mt-1">
            Must start with https://. Every customer link is built from this — a typo breaks them all.
            {f.env_base_set ? " (A PUBLIC_BASE_URL env fallback is also set.)" : ""}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Business phone (for customers)</Label>
            <Input data-testid="portal-business-phone-input" value={f.business_phone || ""} onChange={set("business_phone")} placeholder="Defaults to your OpenPhone number" />
          </div>
          <div>
            <Label>NJ Public Mover License #</Label>
            <Input data-testid="portal-license-input" value={f.license_number || ""} onChange={set("license_number")} placeholder="Shown in footer only if set" />
          </div>
        </div>
        <div>
          <Label>Brochure link (NJ Notice to Consumers)</Label>
          <Input data-testid="portal-brochure-input" type="url" value={f.brochure_url || ""} onChange={set("brochure_url")} placeholder="https://…" />
        </div>
        <div>
          <Label>Arrival window (minutes)</Label>
          <Input data-testid="portal-arrival-window-input" type="number" min="0" max="240" value={f.arrival_window_minutes ?? 30} onChange={set("arrival_window_minutes")} />
          <p className="text-[11px] text-faint mt-1">Customers see "crew arrives between {"{start}"} and {"{start + this}"}". Default 30.</p>
        </div>

        <div>
          <Label className="mb-1 block">Message templates</Label>
          <p className="text-[11px] text-faint mb-2">Variables: {VARS}</p>
          <div className="space-y-2.5">
            {TPL.map((t) => (
              <div key={t.key}>
                <p className="text-[11px] font-semibold text-ink-2">{t.label} <span className="text-faint font-normal">— {t.hint}</span></p>
                <Textarea data-testid={`portal-tpl-${t.key}`} rows={3} value={(f.templates || {})[t.key] || ""} onChange={setTpl(t.key)} />
              </div>
            ))}
          </div>
        </div>

        {warning && (
          <div data-testid="portal-settings-warning" className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/10 p-2.5 text-xs text-warning">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" /> {warning}
          </div>
        )}

        <Button data-testid="portal-settings-save" className="gap-1.5 bg-accent hover:bg-accent-press" disabled={saving} onClick={save}>
          <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : "Save customer page settings"}
        </Button>
      </div>
    </div>
  );
};
