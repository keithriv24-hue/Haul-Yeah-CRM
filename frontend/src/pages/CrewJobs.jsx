import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { MapPin, Truck, Camera, Navigation, Flag, Play, Images, Loader2, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { InstructionBanner } from "@/components/Bits";
import { myJobsApi, setJobStatusApi, uploadJobPhotoApi, listJobPhotosApi, photoUrl, apiErrorMessage } from "@/lib/api";
import { fmtDate, todayISO, mapsLink } from "@/lib/format";

const NEXT_LABEL = { "En Route": "I'm on the way", Arrived: "I've arrived", "In Progress": "Start the job", Complete: "Finish the job" };
const NEXT_ICON = { "En Route": Navigation, Arrived: MapPin, "In Progress": Play, Complete: Flag };
const STATUS_ORDER = ["Assigned", "En Route", "Arrived", "In Progress", "Complete"];
const STATUS_STYLE = {
  Assigned: "bg-slate-100 text-slate-600 border-slate-300",
  "En Route": "bg-sky-100 text-sky-800 border-sky-300",
  Arrived: "bg-amber-100 text-amber-800 border-amber-300",
  "In Progress": "bg-indigo-100 text-indigo-800 border-indigo-300",
  Complete: "bg-emerald-100 text-emerald-800 border-emerald-300",
};

const PhotoSection = ({ jobId }) => {
  const [open, setOpen] = useState(false);
  const [photos, setPhotos] = useState(null);
  const [uploading, setUploading] = useState(false);

  const loadPhotos = useCallback(() => listJobPhotosApi(jobId).then(setPhotos).catch(() => setPhotos([])), [jobId]);

  const toggle = () => {
    if (!open && photos === null) loadPhotos();
    setOpen((o) => !o);
  };

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadJobPhotoApi(jobId, file);
      toast.success("Photo saved.");
      await loadPhotos();
      setOpen(true);
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
    setUploading(false);
    e.target.value = "";
  };

  return (
    <div className="mt-3 border-t border-slate-100 pt-3">
      <div className="flex items-center gap-2">
        <Button data-testid="job-photos-toggle-btn" variant="outline" size="sm" className="gap-1.5 text-xs" onClick={toggle}>
          <Images className="w-3.5 h-3.5" /> {open ? "Hide photos" : `Photos${photos ? ` (${photos.length})` : ""}`}
        </Button>
        <label className="inline-flex">
          <input data-testid="job-photo-input" type="file" accept="image/*" className="hidden" onChange={onFile} disabled={uploading} />
          <span className="inline-flex items-center gap-1.5 cursor-pointer rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors">
            {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Camera className="w-3.5 h-3.5" />}
            {uploading ? "Uploading…" : "Add photo"}
          </span>
        </label>
      </div>
      {open && photos && (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 mt-3">
          {photos.length === 0 && <p className="col-span-full text-xs text-slate-400">No photos yet — snap the truck, the rooms, or any damage before you start.</p>}
          {photos.map((p) => (
            <a key={p.id} href={photoUrl(p.id)} target="_blank" rel="noreferrer">
              <img data-testid="job-photo-thumb" src={photoUrl(p.id)} alt={`By ${p.by}`} className="w-full h-20 object-cover rounded-md border border-slate-200" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
};

const JobCard = ({ job, onChanged }) => {
  const [busy, setBusy] = useState(false);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [notes, setNotes] = useState("");
  const idx = STATUS_ORDER.indexOf(job.exec_status || "Assigned");
  const next = STATUS_ORDER[idx + 1];
  const NextIcon = next ? NEXT_ICON[next] : CheckCircle2;

  const advance = async (status, extraNotes) => {
    setBusy(true);
    try {
      await setJobStatusApi(job.id, status, extraNotes);
      toast.success(status === "Complete" ? "Job done — nice work!" : `Marked "${status}".`);
      setCompleteOpen(false);
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <div data-testid="crew-job-card" className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-bold text-[#1B2A4A]">{job.job_name}</p>
          <p className="text-xs text-slate-500 mt-0.5">
            {fmtDate(job.job_date)}
            {job.arrival_time ? ` · arrive ${job.arrival_time}` : ""}
          </p>
        </div>
        <Badge data-testid="job-exec-status" variant="outline" className={`text-[10px] shrink-0 ${STATUS_STYLE[job.exec_status] || STATUS_STYLE.Assigned}`}>
          {job.exec_status || "Assigned"}
        </Badge>
      </div>
      <div className="mt-2 space-y-1 text-sm">
        {job.start_address && (
          <a data-testid="job-address-link" href={mapsLink(job.start_address)} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-[#1B2A4A] underline decoration-dotted underline-offset-2">
            <MapPin className="w-3.5 h-3.5 text-[#E8743B] shrink-0" /> {job.start_address}
          </a>
        )}
        <p className="flex items-center gap-3 text-xs text-slate-500">
          {job.truck_name && (
            <span className="inline-flex items-center gap-1"><Truck className="w-3.5 h-3.5" /> {job.truck_name}</span>
          )}
          {job.my_position && <span className="font-semibold text-[#E8743B]">You're the {job.my_position}</span>}
        </p>
      </div>
      {next && (
        <Button
          data-testid="job-next-status-btn"
          disabled={busy}
          onClick={() => (next === "Complete" ? setCompleteOpen(true) : advance(next))}
          className="w-full mt-3 gap-2 bg-[#1B2A4A] hover:bg-[#152238]"
        >
          <NextIcon className="w-4 h-4" /> {NEXT_LABEL[next]}
        </Button>
      )}
      {job.exec_status === "Complete" && job.completion_notes && (
        <p className="text-xs text-slate-500 mt-2 bg-slate-50 rounded p-2">Notes: {job.completion_notes}</p>
      )}
      <PhotoSection jobId={job.id} />
      <Dialog open={completeOpen} onOpenChange={setCompleteOpen}>
        <DialogContent data-testid="complete-job-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Finish "{job.job_name}"?</DialogTitle>
            <DialogDescription>Add a quick note about how it went (optional). The boss gets pinged to ask the customer for a review.</DialogDescription>
          </DialogHeader>
          <Textarea data-testid="complete-notes-input" placeholder="Anything to flag? Damage, extra stops, great customer…" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCompleteOpen(false)}>Not yet</Button>
            <Button data-testid="complete-confirm-btn" disabled={busy} onClick={() => advance("Complete", notes)} className="bg-emerald-600 hover:bg-emerald-700 gap-1.5">
              <Flag className="w-4 h-4" /> Mark complete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default function CrewJobs() {
  const [jobs, setJobs] = useState(null);

  const load = useCallback(() => myJobsApi().then(setJobs).catch(() => setJobs([])), []);
  useEffect(() => {
    load();
  }, [load]);

  const today = todayISO();
  const list = jobs || [];
  const todays = list.filter((j) => j.job_date === today);
  const upcoming = list.filter((j) => j.job_date > today);
  const past = list.filter((j) => j.job_date < today).reverse();

  const Section = ({ title, items, testId }) => (
    <div data-testid={testId}>
      <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 mb-2">{title}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-slate-400 bg-white border border-dashed border-slate-200 rounded-lg p-4">Nothing here.</p>
      ) : (
        <div className="space-y-3">{items.map((j) => <JobCard key={j.id} job={j} onChanged={load} />)}</div>
      )}
    </div>
  );

  return (
    <div data-testid="crew-jobs-page" className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold text-[#1B2A4A]">My Jobs</h1>
        <p className="text-sm text-slate-500">Your moves for the next two weeks.</p>
      </div>
      <InstructionBanner testId="crew-jobs-banner">
        Tap the big button as your day moves along: on the way → arrived → start → finish. Snap photos before and after.
      </InstructionBanner>
      {jobs === null ? (
        <p className="text-sm text-slate-400">Loading your jobs…</p>
      ) : (
        <>
          <Section title="Today" items={todays} testId="jobs-today-section" />
          <Section title="Coming up" items={upcoming} testId="jobs-upcoming-section" />
          {past.length > 0 && <Section title="Recent" items={past} testId="jobs-past-section" />}
        </>
      )}
    </div>
  );
}
