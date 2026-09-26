import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Copy, MessageSquare, Mail, RefreshCw, Eye, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { jobPortalApi, jobPortalSendApi, jobPortalResetApi, apiErrorMessage } from "@/lib/api";

const TEMPLATES = [
  { key: "booked", label: "Booked" },
  { key: "move_day", label: "Move day" },
  { key: "wrap_up", label: "Wrap-up" },
];

export const CHANNEL_LABEL = { sms: "Texted", email: "Email opened", copy: "Copied" };

const fmtWhen = (iso) =>
  iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";

const segments = (n) => (n <= 160 ? 1 : Math.ceil(n / 153));

export default function CustomerPageDialog({ jobId, invoiceNumber, onClose, onChanged }) {
  const [data, setData] = useState(null);
  const [tpl, setTpl] = useState("booked");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const [highlightCopy, setHighlightCopy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  const load = useCallback(() => {
    jobPortalApi(jobId).then(setData).catch((e) => toast.error(apiErrorMessage(e)));
  }, [jobId]);

  useEffect(() => {
    jobPortalApi(jobId)
      .then((d) => { setData(d); setMsg((d.templates || {})[tpl] || ""); })
      .catch((e) => toast.error(apiErrorMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const pickTemplate = (key) => {
    setTpl(key);
    setMsg((data?.templates || {})[key] || "");
  };

  const baseSet = data?.base_set;
  const url = data?.url;

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 1800);
    } catch { toast.error("Couldn't copy — long-press the link to copy it."); }
  };

  const logAndRefresh = async (channel) => {
    await jobPortalSendApi(jobId, { channel, template_key: tpl, message: channel === "sms" ? msg : "" });
    await load();
    onChanged && onChanged();
  };

  const sendText = async () => {
    setBusy(true);
    setHighlightCopy(false);
    try {
      await logAndRefresh("sms");
      toast.success("Texted the customer their move page.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
      setHighlightCopy(true);   // OpenPhone failed — nudge the owner to Copy instead
    }
    setBusy(false);
  };

  const copyMessage = async () => {
    try {
      await navigator.clipboard.writeText(msg);
      await logAndRefresh("copy");
      toast.success("Message copied — paste it into your texts.");
    } catch (e) { toast.error(apiErrorMessage(e) || "Couldn't copy the message."); }
  };

  const emailIt = async () => {
    const email = (data?.customer?.email || "").trim();
    const subject = encodeURIComponent("Your Haul Yeah move page");
    window.location.href = `mailto:${email}?subject=${subject}&body=${encodeURIComponent(msg)}`;
    try { await logAndRefresh("email"); } catch { /* logging is best-effort */ }
  };

  const doReset = async () => {
    setConfirmReset(false);
    try {
      await jobPortalResetApi(jobId);
      toast.success("Link reset. The old link is now dead.");
      await load();
      onChanged && onChanged();
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  const len = msg.length;

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="customer-page-dialog" className="max-w-lg max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">Customer page · Job #{invoiceNumber}</DialogTitle>
          <DialogDescription>
            Send {data?.customer?.name || "the customer"} their own move page. No login — the link is the key.
          </DialogDescription>
        </DialogHeader>

        {!data ? (
          <p className="text-sm text-faint">Loading…</p>
        ) : !baseSet ? (
          <div data-testid="customer-page-no-base" className="rounded-lg border border-warning/30 bg-warning/10 p-4 text-sm text-warning">
            Set your Customer page URL in Settings → Customer Page first. Until then, the link can't be built or sent.
          </div>
        ) : (
          <div className="space-y-4">
            {/* Link */}
            <div className="rounded-lg bg-surface-sunk p-3">
              <p className="text-[11px] font-bold uppercase tracking-wide text-faint mb-1">The link</p>
              <p data-testid="customer-page-link" className="text-xs text-primary break-all">{url}</p>
              <div className="flex gap-2 mt-2">
                <Button data-testid="customer-page-copy-link" size="sm" variant="outline" className="gap-1.5" onClick={copyLink}>
                  {copiedLink ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />} Copy link
                </Button>
                <a data-testid="customer-page-preview" href={url} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-semibold text-primary hover:bg-surface-sunk">
                  <Eye className="w-3.5 h-3.5" /> Preview
                </a>
              </div>
            </div>

            {/* Template picker */}
            <div>
              <Label className="mb-1.5 block">Message</Label>
              <div className="flex gap-1.5 mb-2">
                {TEMPLATES.map((t) => (
                  <button key={t.key} data-testid={`customer-page-tpl-${t.key}`} onClick={() => pickTemplate(t.key)}
                    className={`rounded-full px-3 py-1 text-xs font-bold border transition-colors ${
                      tpl === t.key ? "border-accent bg-accent/15 text-accent-ink" : "border-border text-faint hover:bg-surface-sunk"}`}>
                    {t.label}
                  </button>
                ))}
              </div>
              <Textarea data-testid="customer-page-message" rows={6} value={msg} onChange={(e) => setMsg(e.target.value)} />
              <p className="mt-1 text-[11px] text-faint">
                {len} character{len === 1 ? "" : "s"} · {segments(len)} SMS segment{segments(len) === 1 ? "" : "s"}
              </p>
            </div>

            {/* Send buttons */}
            <div className="grid grid-cols-3 gap-2">
              <Button data-testid="customer-page-send-sms" className="gap-1.5 bg-accent hover:bg-accent-press"
                disabled={busy || !msg.trim() || !(data.customer?.phone)} onClick={sendText}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <MessageSquare className="w-4 h-4" />} Send text
              </Button>
              <Button data-testid="customer-page-copy-msg" variant={highlightCopy ? "default" : "outline"}
                className={`gap-1.5 ${highlightCopy ? "ring-2 ring-accent" : ""}`} disabled={!msg.trim()} onClick={copyMessage}>
                <Copy className="w-4 h-4" /> Copy
              </Button>
              <Button data-testid="customer-page-email" variant="outline" className="gap-1.5"
                disabled={!msg.trim() || !(data.customer?.email)} onClick={emailIt}>
                <Mail className="w-4 h-4" /> Email
              </Button>
            </div>
            {!data.customer?.phone && <p className="text-[11px] text-warning">No phone on file — texting is off. Copy or email instead.</p>}

            {/* History */}
            <div className="rounded-lg border border-border p-3">
              <p className="text-[11px] font-bold uppercase tracking-wide text-faint mb-1.5">Send history</p>
              {data.views?.count > 0 && (
                <p data-testid="customer-page-views" className="text-xs text-success mb-1.5">Opened {data.views.count}× · last {fmtWhen(data.views.last_at)}</p>
              )}
              {(data.sends || []).length === 0 ? (
                <p className="text-xs text-faint">Not sent yet.</p>
              ) : (
                <ul className="space-y-1">
                  {[...data.sends].reverse().map((s, i) => (
                    <li key={i} data-testid="customer-page-send-row" className="text-xs text-ink-2">
                      {CHANNEL_LABEL[s.channel] || s.channel} · {fmtWhen(s.at)}{s.by ? ` · ${s.by}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Reset */}
            <button data-testid="customer-page-reset" onClick={() => setConfirmReset(true)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-destructive hover:underline">
              <RefreshCw className="w-3.5 h-3.5" /> Reset link
            </button>
          </div>
        )}

        <AlertDialog open={confirmReset} onOpenChange={setConfirmReset}>
          <AlertDialogContent data-testid="customer-page-reset-confirm">
            <AlertDialogHeader>
              <AlertDialogTitle className="font-display">Reset the customer link?</AlertDialogTitle>
              <AlertDialogDescription>The old link stops working immediately. You'll need to send the new one.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel data-testid="customer-page-reset-cancel">Keep it</AlertDialogCancel>
              <AlertDialogAction data-testid="customer-page-reset-confirm-btn" onClick={doReset} className="bg-destructive hover:bg-destructive/90">
                Reset link
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogContent>
    </Dialog>
  );
}

export const PortalChip = ({ job }) => {
  const sends = job.portal_sends || [];
  const views = job.portal_views || {};
  const last = sends.length ? sends[sends.length - 1] : null;
  const auto = (job.tracking || {}).onway_sms_sent || (job.tracking || {}).sms_sent;
  if (!last && !auto) {
    return (
      <span data-testid={`portal-chip-${job.invoice_number}`} className="inline-flex items-center rounded-full bg-warning/15 text-warning border border-warning/25 px-2 py-0.5 text-[11px] font-bold">
        Page not sent
      </span>
    );
  }
  const label = last ? (CHANNEL_LABEL[last.channel] || "Sent") : "Texted";
  const when = last ? new Date(last.at) : null;
  const dateStr = when ? `${when.getMonth() + 1}/${when.getDate()}` : "";
  return (
    <span data-testid={`portal-chip-${job.invoice_number}`} className="inline-flex items-center rounded-full bg-success/12 text-success border border-success/25 px-2 py-0.5 text-[11px] font-bold">
      {label}{dateStr ? ` ${dateStr}` : ""}{views.count ? ` · opened ${views.count}×` : ""}
    </span>
  );
};
