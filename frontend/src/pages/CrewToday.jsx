import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Phone, MessageSquare, Mail, MapPin, Truck, Clock3, Sun, Send, Star, Loader2, LinkIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { InstructionBanner } from "@/components/Bits";
import { useAuth } from "@/components/AuthGate";
import { crewActiveJobApi, sendTrackingLinkApi, sendReviewRequestApi, apiErrorMessage } from "@/lib/api";
import { mapsUrl, telUrl, smsUrl, fmtTime12 } from "@/lib/maps";

const REMINDER = "If you text, start with your name and why you're reaching out.";

const fmtDay = (d) =>
  d ? new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" }) : "";

const ContactActions = ({ phone, email, idBase }) => (
  <div className="flex gap-1.5 shrink-0">
    {phone && (
      <>
        <a data-testid={`${idBase}-call`} href={telUrl(phone)} className="p-2 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-200 hover:bg-emerald-100">
          <Phone className="w-4 h-4" />
        </a>
        <a data-testid={`${idBase}-text`} href={smsUrl(phone)} className="p-2 rounded-full bg-sky-50 text-sky-600 border border-sky-200 hover:bg-sky-100">
          <MessageSquare className="w-4 h-4" />
        </a>
      </>
    )}
    {email && (
      <a data-testid={`${idBase}-email`} href={`mailto:${email}`} className="p-2 rounded-full bg-orange-50 text-[#E8743B] border border-orange-200 hover:bg-orange-100">
        <Mail className="w-4 h-4" />
      </a>
    )}
  </div>
);

const DetailRow = ({ icon: Icon, label, children }) => (
  <div className="flex items-start gap-2 text-sm py-1.5">
    <Icon className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
    <span className="text-slate-500 w-24 shrink-0">{label}</span>
    <span className="text-[#1B2A4A] font-medium">{children}</span>
  </div>
);

export default function CrewToday() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [confirmTrack, setConfirmTrack] = useState(false);
  const [sendingTrack, setSendingTrack] = useState(false);
  const [reviewMsg, setReviewMsg] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);

  const load = useCallback(() => crewActiveJobApi().then(setData).catch(() => setData({ job: null })), []);
  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  const job = data?.job;

  useEffect(() => {
    if (!job) return;
    const customerFirst = (job.customer?.name || "").split(" ")[0] || "there";
    const myFirst = (user?.name || "").split(" ")[0] || "your mover";
    const link = job.review_link ? ` ${job.review_link}` : "";
    setReviewMsg(
      `Hi ${customerFirst}, this is ${myFirst} with Haul Yeah Moving. Thanks for moving with us today! If we did a good job, would you leave us a quick review?${link}`
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.job_id, job?.review_link]);

  const sendTrack = async () => {
    setConfirmTrack(false);
    setSendingTrack(true);
    try {
      await sendTrackingLinkApi(job.job_id);
      toast.success("New tracking link texted to the customer.");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setSendingTrack(false);
  };

  const sendReview = async (channel) => {
    setReviewBusy(true);
    try {
      if (channel === "email") {
        const subject = encodeURIComponent("Thanks from Haul Yeah Moving!");
        window.location.href = `mailto:${job.customer?.email}?subject=${subject}&body=${encodeURIComponent(reviewMsg)}`;
      }
      await sendReviewRequestApi(job.job_id, { channel, message: reviewMsg });
      toast.success(channel === "sms" ? "Review text sent!" : "Email opened and logged.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setReviewBusy(false);
  };

  return (
    <div data-testid="crew-today-page" className="space-y-5 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold text-[#1B2A4A]">Today</h1>
        <p className="text-sm text-slate-500">Your job, your crew, and who to call.</p>
      </div>

      {data === null ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : !job ? (
        <div data-testid="no-active-job" className="bg-white border border-slate-200 rounded-lg p-8 text-center">
          <Sun className="w-10 h-10 text-slate-300 mx-auto" />
          <p className="text-sm text-slate-500 mt-2">No job on your list yet. The boss will assign you soon.</p>
        </div>
      ) : (
        <>
          <div data-testid="active-job-card" className="bg-[#1B2A4A] text-white rounded-xl p-5">
            <p className="text-xs uppercase tracking-wide text-white/50 font-bold">
              {job.is_today ? "Your Job Today" : `Your Next Job — ${fmtDay(job.job_date)}`}
            </p>
            <p data-testid="active-job-invoice" className="text-2xl font-bold mt-0.5">#{job.invoice_number}</p>
            <div className="flex flex-wrap gap-2 mt-3">
              <span data-testid="my-position-chip" className="text-xs font-bold bg-[#E8743B] rounded-full px-3 py-1">Your role: {job.my_position}</span>
              {job.start_time && <span className="text-xs font-bold bg-white/10 rounded-full px-3 py-1">Start: {fmtTime12(job.start_time)}</span>}
              {job.truck_name && <span className="text-xs font-bold bg-white/10 rounded-full px-3 py-1">Truck: {job.truck_name}</span>}
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-1">My Crew</p>
            {job.crew.filter((c) => !c.me).map((c) => (
              <div key={c.user_id} data-testid={`teammate-row-${c.user_id}`} className="flex items-center justify-between gap-2 py-2 border-b border-slate-100 last:border-0">
                <div>
                  <p className="text-sm font-semibold text-[#1B2A4A]">{c.name}</p>
                  <p className="text-xs text-slate-500">{c.position}{c.phone ? ` — ${c.phone}` : ""}</p>
                </div>
                <ContactActions phone={c.phone} idBase={`teammate-${c.user_id}`} />
              </div>
            ))}
            {job.crew.filter((c) => !c.me).length === 0 && <p className="text-sm text-slate-400 py-1">Just you on this one so far.</p>}
            <p className="text-[11px] text-[#E8743B] font-medium mt-2">{REMINDER}</p>
          </div>

          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-1">Customer</p>
            <div className="flex items-center justify-between gap-2 py-1">
              <div>
                <p data-testid="customer-name" className="text-sm font-semibold text-[#1B2A4A]">{job.customer?.name || "Customer"}</p>
                <p className="text-xs text-slate-500">
                  {job.customer?.phone || "no phone"}{job.customer?.email ? ` · ${job.customer.email}` : ""}
                </p>
              </div>
              <ContactActions phone={job.customer?.phone} email={job.customer?.email} idBase="customer" />
            </div>
            <p className="text-[11px] text-[#E8743B] font-medium mt-2">{REMINDER}</p>
          </div>

          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-1">Job details</p>
            <DetailRow icon={Truck} label="Truck">{job.truck_name || "Boss will pick"}</DetailRow>
            <DetailRow icon={MapPin} label="Get truck">
              {job.truck_pickup_location ? (
                <a data-testid="maps-truck-pickup" href={mapsUrl(job.truck_pickup_location)} target="_blank" rel="noreferrer" className="underline decoration-slate-300">{job.truck_pickup_location}</a>
              ) : "TBD"}
            </DetailRow>
            <DetailRow icon={MapPin} label="From">
              {job.pickup_address ? (
                <a data-testid="maps-pickup" href={mapsUrl(job.pickup_address)} target="_blank" rel="noreferrer" className="underline decoration-slate-300">{job.pickup_address}</a>
              ) : "TBD"}
            </DetailRow>
            <DetailRow icon={MapPin} label="To">
              {job.dropoff_address ? (
                <a data-testid="maps-dropoff" href={mapsUrl(job.dropoff_address)} target="_blank" rel="noreferrer" className="underline decoration-slate-300">{job.dropoff_address}</a>
              ) : "TBD"}
            </DetailRow>
            <DetailRow icon={Clock3} label="Start">{job.start_time ? fmtTime12(job.start_time) : "TBD"}</DetailRow>
          </div>

          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-1">Customer tracking link</p>
            <p className="text-sm text-slate-500">
              {job.tracking_sms_sent
                ? "The customer already got a tracking text. Only send a new one if their link broke."
                : "The customer gets one tracking text automatically when the first person clocks in."}
            </p>
            <Button
              data-testid="send-tracking-link-btn"
              variant="outline"
              className="w-full mt-3 gap-2"
              disabled={sendingTrack}
              onClick={() => setConfirmTrack(true)}
            >
              {sendingTrack ? <Loader2 className="w-4 h-4 animate-spin" /> : <LinkIcon className="w-4 h-4" />}
              Send New Tracking Link
            </Button>
          </div>

          <div id="review" data-testid="review-section" className="bg-white border border-slate-200 rounded-lg p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-1 flex items-center gap-1">
              <Star className="w-3.5 h-3.5 text-[#E8743B]" /> Ask for a review
            </p>
            <p className="text-sm text-slate-500 mb-2">Edit the message if you want, then send it.</p>
            <Textarea data-testid="review-message-input" rows={4} value={reviewMsg} onChange={(e) => setReviewMsg(e.target.value)} />
            {!job.review_link && (
              <p className="text-[11px] text-amber-600 mt-1">Heads up: no review link is saved yet. Ask the boss to add it in Settings.</p>
            )}
            <div className="grid grid-cols-2 gap-2 mt-3">
              <Button data-testid="review-send-sms-btn" className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]" disabled={reviewBusy || !job.customer?.phone} onClick={() => sendReview("sms")}>
                <Send className="w-4 h-4" /> Text it
              </Button>
              <Button data-testid="review-send-email-btn" variant="outline" className="gap-1.5" disabled={reviewBusy || !job.customer?.email} onClick={() => sendReview("email")}>
                <Mail className="w-4 h-4" /> Email it
              </Button>
            </div>
          </div>
        </>
      )}

      <AlertDialog open={confirmTrack} onOpenChange={setConfirmTrack}>
        <AlertDialogContent data-testid="confirm-tracking-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display">Text a new tracking link?</AlertDialogTitle>
            <AlertDialogDescription>
              This sends the customer a fresh link right away. The old link stops working.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="confirm-tracking-cancel">No, go back</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-tracking-send" onClick={sendTrack} className="bg-[#E8743B] hover:bg-[#d4632e]">
              Yes, send it
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
