import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, MapPin, Users, Clock3, CheckCircle2, XCircle, ShieldCheck, ShieldAlert,
  FileText, Star, DollarSign, Send, CalendarClock, Loader2, UserCog, Pencil, History,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { InstructionBanner } from "@/components/Bits";
import { ComplianceSection } from "@/components/ComplianceSection";
import { JobEditDialog } from "@/components/job/JobEditDialog";
import { useAuth } from "@/components/AuthGate";
import { PF, STATUS_PILL } from "@/lib/fields";
import { fmtDate, fmtMoney, mapsLink } from "@/lib/format";
import { jobMgmtDetailApi, recordDeliveredApi, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

const g = (fields, id) => fields?.[id];

const fmtDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—";

const Field = ({ label, value, testId, mono = false }) => (
  <div className="min-w-0">
    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">{label}</p>
    <p data-testid={testId} className={`text-sm text-primary ${mono ? "font-mono" : ""} break-words`}>{value ?? "—"}</p>
  </div>
);

const PayChip = ({ label, info }) => {
  const status = info?.status || info || "unpaid";
  const Icon = status === "paid" ? CheckCircle2 : status === "pending" ? Clock3 : XCircle;
  const tone = status === "paid" ? "text-success" : status === "pending" ? "text-warning" : "text-faint";
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm ${tone}`}>
      <Icon className="w-4 h-4" /> <span className="font-semibold text-primary">{label}:</span> {status}
    </span>
  );
};

export default function JobDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { role } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [recording, setRecording] = useState(false);

  const recordDelivered = useCallback(async () => {
    setRecording(true);
    try {
      const res = await recordDeliveredApi(id);
      toast.success(res.updated ? `Recorded ${res.count} gate date${res.count === 1 ? "" : "s"} from the customer's confirmation.` : (res.message || "Nothing to record."));
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setRecording(false);
  }, [id, load]);

  const load = useCallback(() => {
    setLoading(true);
    jobMgmtDetailApi(id)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(apiErrorMessage(e)))
      .finally(() => setLoading(false));
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return (
      <div data-testid="job-detail-loading" className="flex items-center gap-2 text-faint text-sm p-6">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading job…
      </div>
    );
  }
  if (error && !data) {
    return (
      <div data-testid="job-detail-error" className="space-y-4">
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => navigate("/projects")}>
          <ArrowLeft className="w-4 h-4" /> Back to Jobs
        </Button>
        <div className="surface p-8 text-center text-sm text-faint">{error}</div>
      </div>
    );
  }

  const f = data.fields || {};
  const money = data.can_see_money;
  const status = g(f, PF.status) || "—";
  const portal = data.portal;
  const quality = data.quality;

  return (
    <div data-testid="job-detail-page" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Button data-testid="job-detail-back" variant="ghost" size="sm" className="gap-1.5 -ml-2 mb-1 text-faint" onClick={() => navigate("/projects")}>
            <ArrowLeft className="w-4 h-4" /> Back to Jobs
          </Button>
          <h1 className="text-2xl font-bold text-primary truncate">{g(f, PF.jobName) || "Job"}</h1>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <Badge variant="outline" className={`text-[11px] ${STATUS_PILL[status] || ""}`} data-testid="job-detail-status">{status}</Badge>
            {portal?.invoice_number && <span className="text-xs text-faint">Job #{portal.invoice_number}</span>}
            <span className="text-xs text-faint">{fmtDate(g(f, PF.jobDate))}</span>
          </div>
        </div>
        {role === "owner" && (
          <div className="flex items-center gap-2">
            <Button data-testid="job-detail-edit" variant="default" className="gap-1.5" onClick={() => setEditOpen(true)}>
              <Pencil className="w-4 h-4" /> Edit job
            </Button>
            <Button data-testid="job-detail-assign-crew" variant="outline" className="gap-1.5" asChild>
              <Link to="/jobs"><UserCog className="w-4 h-4" /> Assign crew</Link>
            </Button>
          </div>
        )}
      </div>

      {data.can_edit && (
        <JobEditDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          projectId={id}
          fields={f}
          onSaved={load}
        />
      )}

      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger data-testid="job-tab-overview" value="overview">Overview</TabsTrigger>
          <TabsTrigger data-testid="job-tab-scope" value="scope">Scope</TabsTrigger>
          <TabsTrigger data-testid="job-tab-crew" value="crew">Crew</TabsTrigger>
          <TabsTrigger data-testid="job-tab-timeline" value="timeline">Timeline</TabsTrigger>
          {money && <TabsTrigger data-testid="job-tab-financial" value="financial">Financial</TabsTrigger>}
          {data.can_see_compliance && <TabsTrigger data-testid="job-tab-compliance" value="compliance">Compliance</TabsTrigger>}
          {data.can_see_quality && <TabsTrigger data-testid="job-tab-quality" value="quality">Quality</TabsTrigger>}
          <TabsTrigger data-testid="job-tab-documents" value="documents">Customer page</TabsTrigger>
          <TabsTrigger data-testid="job-tab-history" value="history">History</TabsTrigger>
        </TabsList>

        {/* OVERVIEW */}
        <TabsContent value="overview" className="mt-4">
          <div className="surface p-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <Field label="Customer" value={data.customer?.name} testId="job-ov-customer" />
            {data.customer?.phone !== undefined && <Field label="Phone" value={data.customer?.phone || "—"} testId="job-ov-phone" />}
            {data.customer?.email !== undefined && <Field label="Email" value={data.customer?.email || "—"} testId="job-ov-email" />}
            <Field label="Move date" value={fmtDate(g(f, PF.jobDate))} testId="job-ov-date" />
            <Field label="Status" value={status} testId="job-ov-status" />
            <Field label="Crew size" value={g(f, PF.crewSize) || "—"} testId="job-ov-crew-size" />
            <Field label="Est. hours" value={g(f, PF.estHours) || "—"} testId="job-ov-est-hours" />
            <Field label="Actual on-site hours" value={data.actual_onsite_hours != null ? `${data.actual_onsite_hours}h` : "—"} testId="job-ov-actual-hours" />
            <Field label="Truck" value={g(f, PF.truck) || "—"} testId="job-ov-truck" />
            <div className="sm:col-span-2 lg:col-span-3 grid sm:grid-cols-2 gap-3 pt-1">
              <AddrField label="From" addr={g(f, PF.fromAddr)} testId="job-ov-from" />
              <AddrField label="To" addr={g(f, PF.toAddr)} testId="job-ov-to" />
            </div>
          </div>
        </TabsContent>

        {/* SCOPE */}
        <TabsContent value="scope" className="mt-4">
          <div className="surface p-4 space-y-3">
            <h3 className="font-bold text-primary">Scope &amp; estimate</h3>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <Field label="Recommended crew" value={g(f, PF.crewSize) || "—"} />
              <Field label="Estimated hours" value={g(f, PF.estHours) || "—"} />
              <Field label="Truck" value={g(f, PF.truck) || "—"} />
              {money && <Field label="Quote" value={g(f, PF.quote) != null ? fmtMoney(g(f, PF.quote)) : "—"} />}
              {money && <Field label="Final revenue" value={g(f, PF.finalRevenue) != null ? fmtMoney(g(f, PF.finalRevenue)) : "—"} />}
            </div>
            {data.scope ? (
              <div className="border-t border-border pt-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-faint mb-2">Latest saved scope — {data.scope.created_by}</p>
                <pre data-testid="job-scope-json" className="text-xs bg-surface-sunk rounded-md p-3 overflow-x-auto whitespace-pre-wrap break-words text-ink-2">
                  {JSON.stringify(data.scope.inputs || {}, null, 2)}
                </pre>
                <p className="text-xs text-faint mt-2">Historical numbers are preserved — they never re-price when settings change later.</p>
              </div>
            ) : (
              <p className="text-sm text-faint">No saved scope linked to this job.</p>
            )}
            {g(f, PF.notes) && (
              <div className="border-t border-border pt-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Notes</p>
                <p className="text-sm text-ink-2 whitespace-pre-wrap">{g(f, PF.notes)}</p>
              </div>
            )}
          </div>
        </TabsContent>

        {/* CREW */}
        <TabsContent value="crew" className="mt-4">
          <div className="surface p-4 space-y-4">
            <h3 className="font-bold text-primary flex items-center gap-2"><Users className="w-4 h-4 text-accent-ink" /> Crew &amp; timing</h3>
            {(data.assignments || []).length === 0 && <p className="text-sm text-faint">No crew assigned yet. Use “Assign crew”.</p>}
            {(data.assignments || []).map((a) => (
              <div key={a.id} data-testid="job-crew-assignment" className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-primary">{a.job_name || "Assignment"}</span>
                  <Badge variant="outline" className="text-[11px]">{a.exec_status || "Scheduled"}</Badge>
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {(a.crew || []).map((c, i) => (
                    <span key={i} className="text-xs rounded-full bg-surface-sunk px-2 py-1 text-ink-2">{c.name} · {c.position}</span>
                  ))}
                  {(a.crew || []).length === 0 && <span className="text-xs text-faint">No crew on this assignment.</span>}
                </div>
              </div>
            ))}
            {(data.crew_clock || []).length > 0 && (
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-faint mb-1">Clock in / out</p>
                <div className="space-y-1">
                  {data.crew_clock.map((c, i) => (
                    <div key={i} data-testid="job-crew-clock-row" className="flex flex-wrap items-center gap-x-3 text-sm text-ink-2">
                      <span className="font-semibold text-primary">{c.name}</span>
                      {c.position && <span className="text-faint">{c.position}</span>}
                      <span>In: {fmtDateTime(c.clock_in)}</span>
                      <span>Out: {fmtDateTime(c.clock_out)}</span>
                      {c.hours != null && <span className="text-faint">{c.hours.toFixed ? c.hours.toFixed(1) : c.hours}h</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </TabsContent>

        {/* TIMELINE */}
        <TabsContent value="timeline" className="mt-4">
          <div className="surface p-4">
            <h3 className="font-bold text-primary flex items-center gap-2 mb-3"><CalendarClock className="w-4 h-4 text-accent-ink" /> Job timeline</h3>
            {(data.timeline || []).length === 0 ? (
              <p className="text-sm text-faint">No events yet — the timeline fills in as the job is scheduled, worked, and completed.</p>
            ) : (
              <ol className="space-y-2.5">
                {data.timeline.map((e, i) => (
                  <li key={i} data-testid="job-timeline-event" className="flex gap-3 text-sm">
                    <span className="text-xs text-faint whitespace-nowrap w-28 shrink-0">{fmtDateTime(e.at)}</span>
                    <span className="mt-1.5 w-2 h-2 rounded-full bg-accent shrink-0" />
                    <span className="text-primary">{e.title}{e.by ? <span className="text-faint"> · {e.by}</span> : null}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </TabsContent>

        {/* FINANCIAL (owner) */}
        {money && (
          <TabsContent value="financial" className="mt-4">
            <div className="surface p-4 space-y-4">
              <h3 className="font-bold text-primary flex items-center gap-2"><DollarSign className="w-4 h-4 text-accent-ink" /> Money</h3>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <Field label="Quote" value={g(f, PF.quote) != null ? fmtMoney(g(f, PF.quote)) : "—"} testId="job-fin-quote" />
                <Field label="Final revenue" value={g(f, PF.finalRevenue) != null ? fmtMoney(g(f, PF.finalRevenue)) : "—"} testId="job-fin-final" />
                <Field label="Deposit collected on Airtable" value={g(f, PF.depositCollected) ? "Yes" : "No"} />
                {portal?.payment && <Field label="Deposit (Square)" value={portal.payment.deposit_amount != null ? fmtMoney(portal.payment.deposit_amount) : portal.payment.deposit} />}
                {portal?.payment && <Field label="Paid in full (Square)" value={portal.payment.paid_amount != null ? fmtMoney(portal.payment.paid_amount) : portal.payment.full} />}
              </div>
              {portal?.payment && (
                <div className="flex flex-wrap gap-4 border-t border-border pt-3">
                  <PayChip label="Deposit" info={portal.payment.deposit} />
                  <PayChip label="Paid in full" info={portal.payment.full} />
                </div>
              )}
              {data.internal && (
                <div className="rounded-md border border-border bg-surface-sunk p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-faint flex items-center gap-1.5"><ShieldAlert className="w-3.5 h-3.5 text-destructive" /> Internal margin — never show customers</p>
                  <div className="flex gap-6 mt-1 text-sm">
                    <span>Crew cost: {fmtMoney(data.internal.crew_cost)}</span>
                    <span className={data.internal.margin >= 0 ? "text-success font-semibold" : "text-destructive font-semibold"}>Margin: {fmtMoney(data.internal.margin)}</span>
                  </div>
                </div>
              )}
              {(portal?.tips || []).length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-faint mb-1">Crew tips</p>
                  {portal.tips.map((t, i) => (
                    <div key={i} className="text-sm text-ink-2">{t.name || "Someone"} — {t.amount != null ? fmtMoney(t.amount) : ""} <span className="text-faint">({t.status})</span></div>
                  ))}
                </div>
              )}
            </div>
          </TabsContent>
        )}

        {/* COMPLIANCE */}
        {data.can_see_compliance && (
          <TabsContent value="compliance" className="mt-4">
            <div className="surface p-4 space-y-4">
              <div data-testid="job-customer-paperwork" className="space-y-3 border-b border-border/60 pb-4">
                <h3 className="font-bold text-primary flex items-center gap-2"><FileText className="w-4 h-4 text-accent-ink" /> Customer paperwork &amp; confirmation</h3>
                {data.paperwork_ack ? (
                  <div className="rounded-md bg-success/10 border border-success/25 p-3 text-sm">
                    <p className="text-success font-semibold flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> Customer confirmed receipt — {data.paperwork_ack.name} on {fmtDateTime(data.paperwork_ack.at)} via customer page</p>
                    {(data.paperwork_ack.documents || []).map((d, i) => (
                      <p key={i} className="text-[11px] text-ink-2 font-mono mt-1 break-all">{d.filename}{d.sha256 ? ` · sha256 ${d.sha256.slice(0, 16)}…` : " · (hash unavailable)"}</p>
                    ))}
                    {role === "owner" && (
                      <Button data-testid="job-record-delivered" size="sm" variant="outline" className="mt-2 gap-1.5" disabled={recording} onClick={recordDelivered}>
                        {recording ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />} Record as delivered
                      </Button>
                    )}
                    <p className="text-[11px] text-faint mt-1">Copies this confirmation time into the brochure &amp; estimate gate dates (only if empty). Never touches the signed Order for Service.</p>
                  </div>
                ) : (
                  <p className="text-sm text-faint" data-testid="job-paperwork-none">No customer paperwork acknowledgment on file yet.</p>
                )}
                {data.move_confirmation?.confirmed ? (
                  <p data-testid="job-move-confirmed" className="text-sm text-primary flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4 text-success" /> Customer confirmed move details on {fmtDateTime(data.move_confirmation.at)}
                    {data.move_confirmation.needs_reconfirm && <Badge variant="outline" className="text-warning border-warning/40">details changed since</Badge>}
                  </p>
                ) : (
                  <p className="text-sm text-faint" data-testid="job-move-confirm-none">Customer hasn't confirmed their move details yet.</p>
                )}
              </div>
              <ComplianceSection projectId={id} canEdit={role === "owner" || role === "sales"} canOverride={role === "owner"} />
            </div>
          </TabsContent>
        )}

        {/* QUALITY */}
        {data.can_see_quality && (
          <TabsContent value="quality" className="mt-4">
            <div className="surface p-4 space-y-4" data-testid="job-quality-tab">
              <h3 className="font-bold text-primary flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-accent-ink" /> Quality</h3>
              {!quality && <p className="text-sm text-faint">Quality data unavailable.</p>}
              {quality && (
                <>
                  <QualityGroup title="Audits" testId="job-quality-audits" empty="No audits on this job." rows={(quality.audits || []).map((a) => `#${a.number || "—"} · ${a.result || "—"}${a.completed ? ` · ${a.completed}` : ""}`)} />
                  <QualityGroup title="Nonconformances" testId="job-quality-ncs" empty="No nonconformances." rows={(quality.nonconformances || []).map((n) => `#${n.number || "—"} · ${n.type || ""} · ${n.severity || ""} · ${n.status || ""}`)} />
                  <QualityGroup title="Claims" testId="job-quality-claims" empty="No claims." rows={(quality.claims || []).map((c) => `#${c.number || "—"} · ${c.status || ""}${c.notice_date ? ` · notice ${c.notice_date}` : ""}`)} />
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint mb-1">Review</p>
                    {quality.review ? (
                      <p className="text-sm text-ink-2 flex items-center gap-1"><Star className="w-3.5 h-3.5 text-warning" /> {quality.review.rating ? `${quality.review.rating}★ · ` : ""}{quality.review.google_review_received ? "Google review received" : (quality.review.state || "waiting")}</p>
                    ) : <p className="text-sm text-faint">No review captured.</p>}
                  </div>
                </>
              )}
            </div>
          </TabsContent>
        )}

        {/* CUSTOMER PAGE / DOCUMENTS */}
        <TabsContent value="documents" className="mt-4">
          <div className="surface p-4 space-y-4" data-testid="job-documents-tab">
            <h3 className="font-bold text-primary flex items-center gap-2"><FileText className="w-4 h-4 text-accent-ink" /> Customer page</h3>
            {!portal ? (
              <p className="text-sm text-faint">No customer page yet — it's created once a Square deposit lands for this job.</p>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  {portal.link ? (
                    <a data-testid="job-portal-link" href={portal.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-info underline"><Send className="w-3.5 h-3.5" /> Open customer page</a>
                  ) : <span className="text-faint">No customer link (set the Customer Page URL in Settings).</span>}
                  {portal.onway_sms_sent && <Badge variant="outline" className="text-[10px] bg-info/12 text-info border-info/30">On-the-way text sent</Badge>}
                </div>
                {Object.keys(portal.details || {}).length > 0 && (
                  <div className="rounded-md bg-accent/10 border border-accent/20 p-3 text-sm space-y-1">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-accent-ink">From the customer</p>
                    {Object.entries(portal.details).filter(([, v]) => v).map(([k, v]) => (
                      <p key={k} className="text-ink-2"><strong className="capitalize">{k.replace(/_/g, " ")}:</strong> {v}</p>
                    ))}
                  </div>
                )}
                {portal.review && (
                  <p className="text-sm text-ink-2 flex items-center gap-1"><Star className="w-3.5 h-3.5 text-warning" /> {"★".repeat(portal.review.rating || 0)}{"☆".repeat(5 - (portal.review.rating || 0))} {portal.review.text ? `— "${portal.review.text}"` : ""}</p>
                )}
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-faint mb-1">Sends ({(portal.sends || []).length})</p>
                  {(portal.sends || []).length === 0 ? <p className="text-sm text-faint">Not sent yet.</p> : (
                    <div className="space-y-1">
                      {portal.sends.map((s, i) => (
                        <div key={i} className="text-sm text-ink-2">{fmtDateTime(s.at)} · {s.channel?.toUpperCase()} · {s.template_key} <span className="text-faint">by {s.by}</span></div>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-faint mb-1">Customer uploads ({(portal.uploads || []).length})</p>
                  {(portal.uploads || []).length === 0 ? <p className="text-sm text-faint">No files uploaded.</p> : (
                    <ul className="text-sm text-ink-2 list-disc pl-5">
                      {portal.uploads.map((u) => <li key={u.id}>{u.filename || u.kind} <span className="text-faint">· {fmtDateTime(u.created_at)}</span></li>)}
                    </ul>
                  )}
                </div>
              </>
            )}
          </div>
        </TabsContent>

        {/* HISTORY / AUDIT TRAIL */}
        <TabsContent value="history" className="mt-4">
          <div className="surface p-4 space-y-3" data-testid="job-history-tab">
            <h3 className="font-bold text-primary flex items-center gap-2"><History className="w-4 h-4 text-accent-ink" /> Change history</h3>
            {(data.history || []).length === 0 ? (
              <p className="text-sm text-faint">No edits yet. Every change an owner makes to this job record is logged here.</p>
            ) : (
              <ul className="space-y-2.5">
                {data.history.map((h) => (
                  <li key={h.id} data-testid="job-history-row" className="flex gap-3 text-sm border-b border-border/60 pb-2.5 last:border-0 last:pb-0">
                    <span className="text-xs text-faint whitespace-nowrap w-28 shrink-0">{fmtDateTime(h.at)}</span>
                    <span className="mt-1.5 w-2 h-2 rounded-full bg-accent shrink-0" />
                    <div className="min-w-0">
                      <p className="text-primary">
                        <span className="font-semibold">{h.label}</span>
                        {h.financial && <span className="ml-1.5 text-[10px] uppercase tracking-wide text-warning">financial</span>}
                      </p>
                      <p className="text-ink-2 break-words">
                        <span className="line-through text-faint">{h.old ?? "—"}</span>
                        <span className="mx-1.5 text-faint">→</span>
                        <span className="font-medium text-primary">{h.new ?? "—"}</span>
                      </p>
                      <p className="text-xs text-faint">by {h.by}{h.note ? <span> · “{h.note}”</span> : null}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </TabsContent>
      </Tabs>

      <InstructionBanner testId="job-detail-readonly-note">
        {data.can_edit
          ? "This is the full job record. Use “Edit job” to correct any field — every change is saved to the History tab with who changed what and when."
          : "This is the full job record — a complete read-only view. Only the owner can edit fields."}
      </InstructionBanner>
    </div>
  );
}

const AddrField = ({ label, addr, testId }) => (
  <div>
    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">{label}</p>
    {addr ? (
      <a data-testid={testId} href={mapsLink(addr)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-primary underline decoration-border-strong hover:decoration-accent">
        <MapPin className="w-3.5 h-3.5 text-accent-ink shrink-0" /> {addr}
      </a>
    ) : <p className="text-sm text-faint">—</p>}
  </div>
);

const QualityGroup = ({ title, rows, empty, testId }) => (
  <div data-testid={testId}>
    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint mb-1">{title} ({rows.length})</p>
    {rows.length === 0 ? <p className="text-sm text-faint">{empty}</p> : (
      <ul className="text-sm text-ink-2 space-y-0.5">{rows.map((r, i) => <li key={i}>{r}</li>)}</ul>
    )}
  </div>
);
