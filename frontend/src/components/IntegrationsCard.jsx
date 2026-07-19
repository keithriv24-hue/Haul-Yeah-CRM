import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plug, Save, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getIntegrationsApi, saveIntegrationsApi, squareSyncStatusApi, apiErrorMessage } from "@/lib/api";

const Chip = ({ ok, label }) => (
  <span data-testid={`integr-status-${label.toLowerCase().replace(/\s+/g, "-")}`} className={`inline-flex items-center gap-1.5 text-xs font-semibold rounded-full px-2.5 py-1 ${ok ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-red-50 text-red-700 border border-red-200"}`}>
    <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
    {label} {ok ? "connected" : "not connected"}
  </span>
);

const SecretInput = ({ testId, label, hint, isSet, value, onChange }) => (
  <div>
    <Label>{label}</Label>
    <Input
      data-testid={testId}
      type="password"
      autoComplete="off"
      placeholder={isSet ? "•••••••• saved — paste a new one to replace" : "Paste it here"}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
    {hint && <p className="text-[11px] text-slate-400 mt-0.5">{hint}</p>}
  </div>
);

export const IntegrationsCard = () => {
  const [data, setData] = useState(null);
  const [sync, setSync] = useState(null);
  const [form, setForm] = useState({ square_location_id: "", square_notification_url: "", openphone_number: "", default_truck_pickup: "" });
  const [secrets, setSecrets] = useState({ square_access_token: "", square_webhook_key: "", openphone_api_key: "" });
  const [saving, setSaving] = useState(false);

  const load = () => {
    getIntegrationsApi().then((d) => {
      setData(d);
      setForm({
        square_location_id: d.square_location_id || "",
        square_notification_url: d.square_notification_url || "",
        openphone_number: d.openphone_number || "",
        default_truck_pickup: d.default_truck_pickup || "",
      });
    }).catch(() => {});
    squareSyncStatusApi().then(setSync).catch(() => {});
  };
  useEffect(load, []);

  const save = async () => {
    setSaving(true);
    try {
      const payload = { ...form };
      Object.entries(secrets).forEach(([k, v]) => {
        if (v.trim()) payload[k] = v.trim();
      });
      const d = await saveIntegrationsApi(payload);
      setData(d);
      setSecrets({ square_access_token: "", square_webhook_key: "", openphone_api_key: "" });
      squareSyncStatusApi().then(setSync).catch(() => {});
      toast.success("Integrations saved.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };

  if (!data) return null;
  return (
    <div data-testid="integrations-card" className="bg-white border border-slate-200 rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-500 flex items-center gap-1.5">
          <Plug className="w-3.5 h-3.5" /> Integrations
        </p>
        {sync && (
          <div className="flex gap-1.5 flex-wrap">
            <Chip ok={sync.square_connected} label="Square" />
            <Chip ok={sync.webhook_connected} label="Square sync" />
            <Chip ok={sync.openphone_connected} label="OpenPhone" />
          </div>
        )}
      </div>
      <div className="space-y-3">
        <p className="text-xs font-bold text-[#1B2A4A]">Square (payments)</p>
        <SecretInput testId="integr-square-token-input" label="Square access token" isSet={data.square_access_token_set || data.square_env_token_present}
          hint={data.square_env_token_present && !data.square_access_token_set ? "Using the token from the app's secure secrets. Paste one here to override." : ""}
          value={secrets.square_access_token} onChange={(v) => setSecrets((s) => ({ ...s, square_access_token: v }))} />
        <div>
          <Label>Square location ID</Label>
          <Input data-testid="integr-square-location-input" value={form.square_location_id} placeholder="Leave blank to use the saved one"
            onChange={(e) => setForm((s) => ({ ...s, square_location_id: e.target.value }))} />
        </div>
        <SecretInput testId="integr-webhook-key-input" label="Square webhook signature key"
          hint="From Square Developer dashboard → Webhooks → your subscription. Payments then sync automatically."
          isSet={data.square_webhook_key_set} value={secrets.square_webhook_key} onChange={(v) => setSecrets((s) => ({ ...s, square_webhook_key: v }))} />
        <div>
          <Label>Webhook notification URL</Label>
          <Input data-testid="integr-notification-url-input" value={form.square_notification_url} placeholder="https://haulyeahadmin.com/api/webhooks/square"
            onChange={(e) => setForm((s) => ({ ...s, square_notification_url: e.target.value }))} />
          <p className="text-[11px] text-slate-400 mt-0.5">
            In Square, subscribe to <strong>invoice.payment_made, invoice.updated, payment.updated</strong> and point them at
            {" "}<code className="bg-slate-100 px-1 rounded">https://haulyeahadmin.com/api/webhooks/square</code> — paste the same URL here.
          </p>
        </div>
        <p className="text-xs font-bold text-[#1B2A4A] pt-2">OpenPhone (customer texts)</p>
        <SecretInput testId="integr-openphone-key-input" label="OpenPhone API key" isSet={data.openphone_api_key_set}
          hint="OpenPhone → Settings → API. Tracking links and review texts send through this."
          value={secrets.openphone_api_key} onChange={(v) => setSecrets((s) => ({ ...s, openphone_api_key: v }))} />
        <div>
          <Label>OpenPhone sending number</Label>
          <Input data-testid="integr-openphone-number-input" placeholder="+1 973 555 0100" value={form.openphone_number}
            onChange={(e) => setForm((s) => ({ ...s, openphone_number: e.target.value }))} />
        </div>
        <p className="text-xs font-bold text-[#1B2A4A] pt-2">Defaults</p>
        <div>
          <Label>Default truck pickup location</Label>
          <Input data-testid="integr-truck-pickup-input" value={form.default_truck_pickup}
            onChange={(e) => setForm((s) => ({ ...s, default_truck_pickup: e.target.value }))} />
          <p className="text-[11px] text-slate-400 mt-0.5">New jobs start with this address. You can change it per job on the Jobs board.</p>
        </div>
        <Button data-testid="integr-save-btn" onClick={save} disabled={saving} className="gap-1.5 bg-[#1B2A4A] hover:bg-[#16233d]">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save integrations
        </Button>
      </div>
    </div>
  );
};
