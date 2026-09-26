import React, { useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2, AlertTriangle, FileText, ExternalLink, Loader2, ThumbsUp,
  MessageSquareWarning, ChevronRight,
} from "lucide-react";
import { acknowledgePaperworkApi, confirmMoveApi, apiErrorMessage } from "@/lib/api";

const Card = ({ title, children, testId, tone = "" }) => (
  <div data-testid={testId} className={`w-full max-w-md bg-white/5 border rounded-2xl p-5 text-left ${tone || "border-white/10"}`}>
    {title && <p className="text-xs uppercase tracking-wide text-white/50 font-bold mb-3">{title}</p>}
    {children}
  </div>
);

const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric" }) + ", " +
  new Date(s).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : "");

// ---- Move timeline (5 steps; paperwork holds an order-independent 3-item checklist) ----
export const PortalTimeline = ({ timeline }) => {
  if (!timeline?.steps) return null;
  const dot = (state) => {
    if (state === "done") return "bg-success border-success text-white";
    if (state === "action") return "bg-warning/20 border-warning text-warning animate-pulse";
    if (state === "current") return "bg-accent/20 border-accent text-accent-ink";
    return "bg-white/5 border-white/20 text-white/30";
  };
  const label = (s) => {
    if (s.state === "done") return "text-white";
    if (s.state === "action") return "text-warning font-semibold";
    if (s.state === "current") return "text-white";
    return "text-white/40";
  };
  const sub = (s) => {
    if (s.key === "paperwork") {
      if (s.state === "done") return "All set ✓";
      if (s.state === "action") return "Action needed";
      return "In progress";
    }
    return null;
  };
  return (
    <Card title="Your move, step by step" testId="portal-timeline">
      <ol className="space-y-0">
        {timeline.steps.map((s, i) => (
          <li key={s.key} data-testid={`timeline-step-${s.key}`} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className={`w-7 h-7 shrink-0 rounded-full border-2 flex items-center justify-center text-xs font-bold ${dot(s.state)}`}>
                {s.state === "done" ? <CheckCircle2 className="w-4 h-4" /> : s.state === "action" ? "!" : i + 1}
              </span>
              {i < timeline.steps.length - 1 && <span className={`w-0.5 flex-1 min-h-[18px] ${s.state === "done" ? "bg-success/50" : "bg-white/10"}`} />}
            </div>
            <div className="pb-4 flex-1 min-w-0">
              <p className={`text-sm ${label(s)}`}>{s.label}{sub(s) && <span className="ml-2 text-[11px] font-normal text-white/45">{sub(s)}</span>}</p>
              {s.items && (
                <ul className="mt-1.5 space-y-1">
                  {s.items.map((it) => (
                    <li key={it.key} data-testid={`paperwork-item-${it.key}`} className="flex items-center gap-2 text-xs">
                      <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold ${it.done ? "bg-success text-white" : "bg-white/10 text-white/40 border border-white/20"}`}>
                        {it.done ? "✓" : ""}
                      </span>
                      <span className={it.done ? "text-white/80" : "text-white/45"}>{it.label}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
};

// ---- NJ paperwork acknowledgment ----
export const PortalPaperwork = ({ token, timeline, brochureUrl, onDone }) => {
  const acked = timeline?.paperwork_acknowledged;
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (name.trim().length < 2) { toast.error("Please type your full name to confirm."); return; }
    setBusy(true);
    try {
      await acknowledgePaperworkApi(token, name.trim());
      toast.success("Thank you — your paperwork receipt is on file.");
      onDone?.();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  const tone = !acked && timeline?.paperwork_action_needed ? "border-warning/40 bg-warning/5" : "border-white/10";
  return (
    <Card title="Your paperwork" testId="portal-paperwork" tone={tone}>
      <p className="text-xs text-white/55 mb-3">
        New Jersey law entitles you to these documents before your move. Please review them and confirm you've received them.
      </p>
      {brochureUrl && (
        <a data-testid="portal-brochure-link" href={brochureUrl} target="_blank" rel="noreferrer"
          className="flex items-center gap-1.5 text-sm text-info hover:underline mb-3">
          <FileText className="w-4 h-4" /> Read: Your Rights & Responsibilities When You Move <ExternalLink className="w-3 h-3" />
        </a>
      )}
      {acked ? (
        <div data-testid="portal-paperwork-done" className="flex items-start gap-2 rounded-lg bg-success/10 border border-success/25 p-3 text-sm text-success">
          <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
          <span>Received & confirmed by {timeline.acknowledged_name || "you"} on {fmtDate(timeline.acknowledged_at)}. Thank you!</span>
        </div>
      ) : (
        <div className="space-y-2">
          {timeline?.paperwork_action_needed && (
            <p className="flex items-center gap-1.5 text-xs text-warning font-semibold"><AlertTriangle className="w-3.5 h-3.5" /> Please confirm today — we need this before your move.</p>
          )}
          <label className="text-[11px] font-semibold text-white/60">Type your full name to confirm receipt</label>
          <input data-testid="portal-paperwork-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your full name"
            className="w-full rounded-md bg-white/10 border border-white/15 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-accent" />
          <button data-testid="portal-paperwork-submit" onClick={submit} disabled={busy}
            className="w-full inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent hover:bg-accent-press disabled:opacity-50 text-white font-bold text-sm px-4 py-2 transition-colors">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} I've received & read these
          </button>
        </div>
      )}
    </Card>
  );
};

// ---- Confirm my move details ----
export const PortalMoveConfirm = ({ token, confirm, businessPhone, jobNumber, onDone }) => {
  const [busy, setBusy] = useState(false);
  const needsAction = !confirm?.confirmed || confirm?.needs_reconfirm;
  const looksRight = async () => {
    setBusy(true);
    try {
      await confirmMoveApi(token);
      toast.success("Great — thanks for confirming!");
      onDone?.();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  const tel = (businessPhone || "").replace(/[^\d+]/g, "");
  const wrong = `sms:${tel}?&body=${encodeURIComponent(`Job #${jobNumber || ""}: needs a change — `)}`;
  if (!needsAction) {
    return (
      <div data-testid="portal-move-confirmed" className="mt-4 flex items-center justify-center gap-1.5 text-sm text-success">
        <CheckCircle2 className="w-4 h-4" /> You confirmed these details on {fmtDate(confirm.at)}
      </div>
    );
  }
  return (
    <div data-testid="portal-move-confirm" className="mt-4 border-t border-white/10 pt-4">
      <p className="text-sm text-white/70 mb-2.5">{confirm?.needs_reconfirm ? "Your move details changed — does everything still look right?" : "Does everything above look right?"}</p>
      <div className="flex gap-2">
        <button data-testid="portal-confirm-yes" onClick={looksRight} disabled={busy}
          className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-success/90 hover:bg-success text-white font-bold text-sm px-3 py-2 disabled:opacity-50 transition-colors">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ThumbsUp className="w-4 h-4" />} Looks right
        </button>
        <a data-testid="portal-confirm-no" href={wrong}
          className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg border border-white/20 bg-white/5 hover:bg-white/10 text-white/85 font-bold text-sm px-3 py-2 transition-colors">
          <MessageSquareWarning className="w-4 h-4" /> Something's wrong
        </a>
      </div>
    </div>
  );
};

// ---- Prep checklist (read-only; elevator/parking items jump to the move-details form) ----
const scrollToField = (id) => {
  const el = document.getElementById(id);
  if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); const inp = el.querySelector("input,textarea"); if (inp) setTimeout(() => inp.focus(), 400); }
};
export const PortalPrep = ({ items }) => {
  if (!items?.length) return null;
  const linkFor = (text) => {
    const t = text.toLowerCase();
    if (t.includes("elevator")) return { id: "portal-field-elevator", label: "Add elevator times" };
    if (t.includes("park") || t.includes("curb")) return { id: "portal-field-parking", label: "Add parking instructions" };
    return null;
  };
  return (
    <Card title="Get ready for moving day" testId="portal-prep">
      <ul className="space-y-2.5">
        {items.map((text, i) => {
          const link = linkFor(text);
          return (
            <li key={i} data-testid="prep-item" className="flex items-start gap-2 text-sm text-white/80">
              <ChevronRight className="w-4 h-4 text-accent-ink mt-0.5 shrink-0" />
              <div className="min-w-0">
                <span>{text}</span>
                {link && (
                  <button data-testid={`prep-link-${link.id}`} onClick={() => scrollToField(link.id)}
                    className="ml-1.5 inline-flex items-center gap-0.5 text-info hover:underline font-semibold">
                    {link.label} <ChevronRight className="w-3 h-3" />
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
};
