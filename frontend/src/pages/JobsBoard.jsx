import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  CheckCircle2, XCircle, Clock3, MapPin, Truck, Users, Pencil, Briefcase, Plus, Loader2, PlugZap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { InstructionBanner, PageTitle, Private } from "@/components/Bits";
import { fmtMoney } from "@/lib/format";
import { mapsUrl, fmtTime12 } from "@/lib/maps";
import {
  listJobsApi, patchJobApi, squareSyncStatusApi, listUsersApi, listTrucksApi, createTruckApi,
  listReviewRequestsApi, apiErrorMessage,
} from "@/lib/api";

const POSITIONS = ["Driver", "Lead", "Helper", "Packer"];

const fmtPaidAt = (iso) =>
  iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "";

const fmtJobDate = (d) =>
  d ? new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) : "Date TBD";

const PayRow = ({ label, info }) => {
  const status = info?.status || "unpaid";
  const Icon = status === "paid" ? CheckCircle2 : status === "pending" ? Clock3 : XCircle;
  const color = status === "paid" ? "text-emerald-600" : status === "pending" ? "text-amber-500" : "text-red-500";
  return (
    <div data-testid={`pay-row-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`} className="flex items-center gap-2 text-sm">
      <Icon className={`w-4 h-4 shrink-0 ${color}`} />
      <span className="font-semibold text-[#1B2A4A]">{label}:</span>
      {status === "paid" ? (
        <span className="text-slate-600"><Private><Money v={info.amount} /></Private> — paid {fmtPaidAt(info.paid_at)}</span>
      ) : status === "pending" ? (
        <span className="text-amber-600">Payment pending confirmation{info?.amount ? <> (<Private><Money v={info.amount} /></Private>)</> : ""}</span>
      ) : (
        <span className="text-slate-400">Not paid</span>
      )}
    </div>
  );
};

const Money = ({ v }) => <>{fmtMoney(v)}</>;

const AddrLink = ({ label, addr, testId }) =>
  addr ? (
    <a data-testid={testId} href={mapsUrl(addr)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[#1B2A4A] underline decoration-slate-300 hover:decoration-[#E8743B]">
      <MapPin className="w-3.5 h-3.5 text-[#E8743B] shrink-0" />{label ? `${label}: ` : ""}{addr}
    </a>
  ) : (
    <span className="text-slate-400">{label ? `${label}: ` : ""}not set</span>
  );

function AssignDialog({ job, users, trucks, onSaved, onClose, onTruckCreated }) {
  const crewUsers = users.filter((u) => u.active !== false && (u.roles || [u.role]).includes("crew"));
  const [sel, setSel] = useState(() => (job.crew || []).map((c) => ({ user_id: c.user_id, position: c.position })));
  const [truckId, setTruckId] = useState(job.truck_id || "");
  const [newTruck, setNewTruck] = useState("");
  const [showNewTruck, setShowNewTruck] = useState(false);
  const [fields, setFields] = useState({
    pickup_address: job.pickup_address || "",
    dropoff_address: job.dropoff_address || "",
    job_date: job.job_date || "",
    start_time: job.start_time || "",
    truck_pickup_location: job.truck_pickup_location || "",
  });
  const [saving, setSaving] = useState(false);

  const toggle = (uid) =>
    setSel((s) => (s.some((x) => x.user_id === uid) ? s.filter((x) => x.user_id !== uid) : [...s, { user_id: uid, position: "Helper" }]));
  const setPos = (uid, position) => setSel((s) => s.map((x) => (x.user_id === uid ? { ...x, position } : x)));

  const addTruck = async () => {
    if (!newTruck.trim()) return;
    try {
      const t = await createTruckApi({ name: newTruck.trim() });
      onTruckCreated(t);
      setTruckId(t.id || t._id);
      setShowNewTruck(false);
      setNewTruck("");
      toast.success("Truck added.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await patchJobApi(job.id, { crew: sel, truck_id: truckId || "", ...fields });
      toast.success("Saved. Assigned crew can see this job right now.");
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSaving(false);
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="assign-job-dialog" className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">Job #{job.invoice_number}</DialogTitle>
          <DialogDescription>Assign crew, truck, and addresses. Saving publishes it to each crew member's app.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label className="mb-1.5 block">Crew &amp; positions</Label>
            <div className="space-y-1.5 border border-slate-200 rounded-md p-2">
              {crewUsers.map((u) => {
                const picked = sel.find((x) => x.user_id === u.id);
                return (
                  <div key={u.id} data-testid={`crew-pick-${u.id}`} className="flex items-center gap-2">
                    <Checkbox data-testid={`crew-check-${u.id}`} checked={!!picked} onCheckedChange={() => toggle(u.id)} />
                    <span className="text-sm flex-1 text-[#1B2A4A]">{u.name}</span>
                    {picked && (
                      <>
                        <Input data-testid={`crew-position-${u.id}`} className="w-24 h-8 text-xs" list="hy-positions"
                          value={picked.position} onChange={(e) => setPos(u.id, e.target.value)} />
                      </>
                    )}
                  </div>
                );
              })}
              {crewUsers.length === 0 && <p className="text-xs text-slate-400">No crew accounts yet — add them on the Crew page.</p>}
              <datalist id="hy-positions">
                {POSITIONS.map((p) => <option key={p} value={p} />)}
              </datalist>
            </div>
          </div>
          <div>
            <Label>Truck</Label>
            <div className="flex gap-2">
              <Select value={truckId || "none"} onValueChange={(v) => (v === "__new" ? setShowNewTruck(true) : setTruckId(v === "none" ? "" : v))}>
                <SelectTrigger data-testid="assign-truck-select" className="flex-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No truck yet</SelectItem>
                  {trucks.map((t) => <SelectItem key={t.id || t._id} value={t.id || t._id}>{t.name}</SelectItem>)}
                  <SelectItem value="__new">+ Add new truck…</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {showNewTruck && (
              <div className="flex gap-2 mt-2">
                <Input data-testid="new-truck-name-input" placeholder="Truck name (e.g. Box #3)" value={newTruck} onChange={(e) => setNewTruck(e.target.value)} />
                <Button data-testid="new-truck-save-btn" size="sm" onClick={addTruck}><Plus className="w-4 h-4" /></Button>
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Job date</Label>
              <Input data-testid="assign-date-input" type="date" value={fields.job_date} onChange={(e) => setFields((s) => ({ ...s, job_date: e.target.value }))} />
            </div>
            <div>
              <Label>Start time</Label>
              <Input data-testid="assign-time-input" type="time" value={fields.start_time} onChange={(e) => setFields((s) => ({ ...s, start_time: e.target.value }))} />
            </div>
          </div>
          <div>
            <Label>Pickup (from)</Label>
            <Input data-testid="assign-pickup-input" value={fields.pickup_address} onChange={(e) => setFields((s) => ({ ...s, pickup_address: e.target.value }))} />
          </div>
          <div>
            <Label>Drop-off (to)</Label>
            <Input data-testid="assign-dropoff-input" value={fields.dropoff_address} onChange={(e) => setFields((s) => ({ ...s, dropoff_address: e.target.value }))} />
          </div>
          <div>
            <Label>Truck pickup location</Label>
            <Input data-testid="assign-truck-pickup-input" value={fields.truck_pickup_location} onChange={(e) => setFields((s) => ({ ...s, truck_pickup_location: e.target.value }))} />
          </div>
          <Button data-testid="assign-save-btn" className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]" disabled={saving} onClick={save}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Save &amp; publish to crew
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function JobsBoard() {
  const [jobs, setJobs] = useState(null);
  const [sync, setSync] = useState(null);
  const [users, setUsers] = useState([]);
  const [trucks, setTrucks] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [editJob, setEditJob] = useState(null);

  const load = useCallback(() => {
    listJobsApi().then(setJobs).catch(() => setJobs([]));
    squareSyncStatusApi().then(setSync).catch(() => {});
    listUsersApi().then(setUsers).catch(() => {});
    listTrucksApi().then(setTrucks).catch(() => {});
    listReviewRequestsApi().then(setReviews).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    const id = setInterval(() => listJobsApi().then(setJobs).catch(() => {}), 60000);
    return () => clearInterval(id);
  }, [load]);

  const upcoming = useMemo(() => jobs || [], [jobs]);

  return (
    <div data-testid="jobs-board-page" className="space-y-5">
      <PageTitle title="Jobs" subtitle="Deposit-paid moves, labeled by Square invoice number." />
      {sync && !sync.webhook_connected && (
        <div data-testid="square-sync-banner" className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-lg px-4 py-2.5">
          <PlugZap className="w-4 h-4 shrink-0" />
          <span>
            Square sync not connected — go to{" "}
            <Link to="/settings" className="font-bold underline">Settings → Integrations</Link>.
            {sync.square_connected ? " (A backup check still runs every 2 minutes.)" : ""}
          </span>
        </div>
      )}
      <InstructionBanner testId="jobs-board-banner">
        A job shows up here the moment its Square deposit is confirmed paid — never before. Tap Assign to pick the crew, truck, and addresses.
      </InstructionBanner>

      {jobs === null ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : upcoming.length === 0 ? (
        <div data-testid="jobs-empty" className="bg-white border border-slate-200 rounded-lg p-8 text-center">
          <Briefcase className="w-10 h-10 text-slate-300 mx-auto" />
          <p className="text-sm text-slate-500 mt-2">No deposit-paid jobs yet. When a customer pays a Square deposit, the job pops up here on its own.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {upcoming.map((job) => (
            <div key={job.id} data-testid={`job-card-${job.invoice_number}`} className="bg-white border border-slate-200 rounded-lg p-4 space-y-3">
              <div className="flex items-start justify-between gap-2 flex-wrap">
                <div>
                  <p className="text-lg font-bold text-[#1B2A4A]">
                    Job #{job.invoice_number}
                    <span className="text-slate-400 font-medium"> — {fmtJobDate(job.job_date)}{job.start_time ? ` ${fmtTime12(job.start_time)}` : ""}</span>
                  </p>
                  <p className="text-sm text-slate-500">
                    {job.customer?.name || "Customer"}{job.customer?.phone ? ` · ${job.customer.phone}` : ""}
                  </p>
                </div>
                <Button data-testid={`assign-btn-${job.invoice_number}`} size="sm" variant="outline" className="gap-1.5" onClick={() => setEditJob(job)}>
                  <Pencil className="w-3.5 h-3.5" /> {job.crew?.length ? "Edit" : "Assign"}
                </Button>
              </div>
              <div className="space-y-1 bg-slate-50 rounded-md p-3">
                <PayRow label="Deposit Paid (25%)" info={job.deposit_paid} />
                <PayRow label="Paid in Full" info={job.paid_in_full} />
              </div>
              <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
                <span className="inline-flex items-center gap-1.5 text-slate-600">
                  <Users className="w-3.5 h-3.5 text-slate-400" />
                  {job.crew?.length ? job.crew.map((c) => `${c.name.split(" ")[0]} (${c.position})`).join(", ") : <span className="text-slate-400">No crew yet</span>}
                </span>
                <span className="inline-flex items-center gap-1.5 text-slate-600">
                  <Truck className="w-3.5 h-3.5 text-slate-400" />
                  {job.truck_name || <span className="text-slate-400">No truck yet</span>}
                </span>
              </div>
              <div className="flex flex-col gap-1 text-sm">
                <AddrLink label="From" addr={job.pickup_address} testId={`maps-from-${job.invoice_number}`} />
                <AddrLink label="To" addr={job.dropoff_address} testId={`maps-to-${job.invoice_number}`} />
                <AddrLink label="Truck pickup" addr={job.truck_pickup_location} testId={`maps-truck-${job.invoice_number}`} />
              </div>
            </div>
          ))}
        </div>
      )}

      <div>
        <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 mb-2 mt-8">Review requests sent by crew</h2>
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-400 border-b border-slate-100">
                <th className="px-3 py-2">When</th>
                <th className="px-3 py-2">Crew member</th>
                <th className="px-3 py-2">Channel</th>
                <th className="px-3 py-2">Customer</th>
                <th className="px-3 py-2">Phone</th>
                <th className="px-3 py-2">Email</th>
                <th className="px-3 py-2">Job</th>
              </tr>
            </thead>
            <tbody>
              {reviews.map((r) => (
                <tr key={r.id} data-testid="review-log-row" className="border-b border-slate-50">
                  <td className="px-3 py-2 whitespace-nowrap">{fmtPaidAt(r.sent_at)}</td>
                  <td className="px-3 py-2">{r.crew_name}</td>
                  <td className="px-3 py-2 uppercase text-xs font-bold text-slate-500">{r.channel}</td>
                  <td className="px-3 py-2">{r.customer?.name}</td>
                  <td className="px-3 py-2">{r.customer?.phone}</td>
                  <td className="px-3 py-2">{r.customer?.email}</td>
                  <td className="px-3 py-2">#{r.invoice_number}</td>
                </tr>
              ))}
              {reviews.length === 0 && (
                <tr><td colSpan="7" className="px-3 py-5 text-center text-slate-400">No review requests yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {editJob && (
        <AssignDialog
          job={editJob}
          users={users}
          trucks={trucks}
          onSaved={() => { setEditJob(null); load(); }}
          onClose={() => setEditJob(null)}
          onTruckCreated={(t) => setTrucks((list) => [...list, t])}
        />
      )}
    </div>
  );
}
