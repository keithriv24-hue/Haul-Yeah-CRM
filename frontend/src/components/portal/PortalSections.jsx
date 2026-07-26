import React, { useState } from "react";
import { toast } from "sonner";
import { Loader2, Upload, Star, HandCoins, FileText, ExternalLink } from "lucide-react";
import { portalDetailsApi, portalUploadApi, portalUploadUrl, portalTipApi, portalReviewApi, apiErrorMessage } from "@/lib/api";

const Card = ({ title, children, testId }) => (
  <div data-testid={testId} className="w-full max-w-md bg-white/5 border border-white/10 rounded-2xl p-5 text-left">
    <p className="text-xs uppercase tracking-wide text-white/50 font-bold mb-3">{title}</p>
    {children}
  </div>
);

const Field = ({ label, value, onChange, placeholder, testId, textarea }) => (
  <div>
    <label className="text-[11px] font-semibold text-white/60">{label}</label>
    {textarea ? (
      <textarea data-testid={testId} rows={2} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full mt-0.5 rounded-md bg-white/10 border border-white/15 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-[#E8743B]" />
    ) : (
      <input data-testid={testId} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full mt-0.5 rounded-md bg-white/10 border border-white/15 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-[#E8743B]" />
    )}
  </div>
);

const Btn = ({ children, onClick, disabled, testId, className = "" }) => (
  <button data-testid={testId} disabled={disabled} onClick={onClick}
    className={`inline-flex items-center justify-center gap-1.5 rounded-lg bg-[#E8743B] hover:bg-[#d4632e] disabled:opacity-50 text-white font-bold text-sm px-4 py-2 transition-colors ${className}`}>
    {children}
  </button>
);

export const PortalBalance = ({ data }) => {
  if (data.quote_total == null && !(data.invoices || []).length) return null;
  const money = (v) => (v == null ? "—" : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2 })}`);
  return (
    <Card title="Payments" testId="portal-balance">
      {data.quote_total != null && (
        <div className="space-y-1 text-sm">
          <p className="flex justify-between text-white/80"><span>Move total</span><span className="font-bold">{money(data.quote_total)}</span></p>
          {data.deposit_amount != null && (
            <p className="flex justify-between text-emerald-300"><span>Deposit paid ✓</span><span className="font-bold">{money(data.deposit_amount)}</span></p>
          )}
          {data.paid_in_full ? (
            <p data-testid="portal-paid-full" className="flex justify-between text-emerald-300 font-bold border-t border-white/10 pt-1.5"><span>Paid in full ✓</span><span>$0.00</span></p>
          ) : data.remaining_balance != null ? (
            <p data-testid="portal-remaining" className="flex justify-between text-amber-300 font-bold border-t border-white/10 pt-1.5"><span>Remaining balance</span><span>{money(data.remaining_balance)}</span></p>
          ) : null}
        </div>
      )}
      {(data.invoices || []).filter((i) => i.url).length > 0 && (
        <div className="mt-3 space-y-1">
          {data.invoices.filter((i) => i.url).map((inv, i) => (
            <a key={i} data-testid="portal-invoice-link" href={inv.url} target="_blank" rel="noreferrer"
              className="flex items-center gap-1.5 text-xs text-sky-300 hover:underline">
              <FileText className="w-3.5 h-3.5" /> Invoice #{inv.invoice_number} — view / download <ExternalLink className="w-3 h-3" />
            </a>
          ))}
        </div>
      )}
    </Card>
  );
};

export const PortalDetails = ({ token, initial }) => {
  const [f, setF] = useState({
    gate_code: initial?.gate_code || "", elevator: initial?.elevator || "", parking: initial?.parking || "",
    special_requests: initial?.special_requests || "", inventory_notes: initial?.inventory_notes || "",
  });
  const [busy, setBusy] = useState(false);
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    setBusy(true);
    try {
      await portalDetailsApi(token, f);
      toast.success("Got it — your crew will have all of this on move day.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <Card title="Help your crew — move details" testId="portal-details">
      <div className="space-y-2.5">
        <Field label="Gate / door code" value={f.gate_code} onChange={set("gate_code")} placeholder="#4321" testId="portal-gate-code" />
        <Field label="Elevator reservation" value={f.elevator} onChange={set("elevator")} placeholder="Booked 9–11am, service elevator on the left" testId="portal-elevator" />
        <Field label="Parking instructions" value={f.parking} onChange={set("parking")} placeholder="Loading dock behind the building on Oak St" testId="portal-parking" textarea />
        <Field label="Special requests" value={f.special_requests} onChange={set("special_requests")} placeholder="Please wrap the piano extra well" testId="portal-special" textarea />
        <Field label="Inventory notes" value={f.inventory_notes} onChange={set("inventory_notes")} placeholder="3 beds, 2 dressers, ~40 boxes, 1 treadmill" testId="portal-inventory" textarea />
        <Btn testId="portal-details-save" onClick={save} disabled={busy} className="w-full">
          {busy && <Loader2 className="w-4 h-4 animate-spin" />} Save details
        </Btn>
      </div>
    </Card>
  );
};

export const PortalUploads = ({ token, initial }) => {
  const [uploads, setUploads] = useState(initial || []);
  const [busy, setBusy] = useState(false);
  const pick = (kind) => async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setBusy(true);
    for (const f of files) {
      try {
        const res = await portalUploadApi(token, f, kind);
        setUploads((u) => [{ id: res.id, kind, filename: f.name, content_type: f.type }, ...u]);
      } catch (err) {
        toast.error(apiErrorMessage(err));
      }
    }
    setBusy(false);
    toast.success("Uploaded — thanks!");
    e.target.value = "";
  };
  return (
    <Card title="Photos & inventory" testId="portal-uploads">
      <p className="text-xs text-white/50 mb-2.5">Snap your rooms, big furniture, or upload an inventory list (photos or PDF). It helps us show up ready.</p>
      <div className="flex gap-2">
        <label className="flex-1">
          <input data-testid="portal-photo-input" type="file" accept="image/*" multiple className="hidden" onChange={pick("photo")} />
          <span className="flex items-center justify-center gap-1.5 cursor-pointer rounded-lg border border-white/20 bg-white/10 hover:bg-white/15 px-3 py-2 text-sm font-semibold">
            <Upload className="w-4 h-4" /> Photos
          </span>
        </label>
        <label className="flex-1">
          <input data-testid="portal-inventory-input" type="file" accept="image/*,application/pdf" multiple className="hidden" onChange={pick("inventory")} />
          <span className="flex items-center justify-center gap-1.5 cursor-pointer rounded-lg border border-white/20 bg-white/10 hover:bg-white/15 px-3 py-2 text-sm font-semibold">
            <FileText className="w-4 h-4" /> Inventory
          </span>
        </label>
      </div>
      {busy && <p className="text-xs text-white/50 mt-2">Uploading…</p>}
      {uploads.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {uploads.map((u) => (
            <a key={u.id} data-testid="portal-upload-item" href={portalUploadUrl(token, u.id)} target="_blank" rel="noreferrer" className="block">
              {(u.content_type || "").startsWith("image/") ? (
                <img src={portalUploadUrl(token, u.id)} alt={u.filename} className="w-14 h-14 object-cover rounded-md border border-white/15" />
              ) : (
                <span className="flex items-center gap-1 text-[11px] text-sky-300 border border-white/15 rounded-md px-2 py-1.5"><FileText className="w-3.5 h-3.5" /> {u.filename}</span>
              )}
            </a>
          ))}
        </div>
      )}
    </Card>
  );
};

export const PortalTip = ({ token, crewNames }) => {
  const [amount, setAmount] = useState(null);
  const [custom, setCustom] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const amt = custom ? Number(custom) : amount;
  const go = async () => {
    setBusy(true);
    try {
      const { url } = await portalTipApi(token, { amount: amt, name });
      window.open(url, "_blank", "noopener");
      toast.success("Square checkout opened — the crew thanks you!");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <Card title="Tip your crew" testId="portal-tip">
      <p className="text-xs text-white/50 mb-2.5">{crewNames ? `100% goes to ${crewNames}.` : "100% goes to the crew who moved you."} Checkout is handled securely by Square.</p>
      <div className="flex gap-2 mb-2.5">
        {[20, 40, 60].map((v) => (
          <button key={v} data-testid={`portal-tip-${v}`} onClick={() => { setAmount(v); setCustom(""); }}
            className={`flex-1 rounded-lg border px-3 py-2 text-sm font-bold transition-colors ${amount === v && !custom ? "border-[#E8743B] bg-[#E8743B]/20 text-[#E8743B]" : "border-white/20 bg-white/5 text-white/80 hover:bg-white/10"}`}>
            ${v}
          </button>
        ))}
        <input data-testid="portal-tip-custom" type="number" min="1" placeholder="Other" value={custom}
          onChange={(e) => setCustom(e.target.value)}
          className="w-20 rounded-lg bg-white/10 border border-white/20 px-2 py-2 text-sm text-white text-center placeholder:text-white/30 focus:outline-none focus:border-[#E8743B]" />
      </div>
      <Field label="Who's this from? (leave your name)" value={name} onChange={setName} placeholder="The Johnson family" testId="portal-tip-name" />
      <Btn testId="portal-tip-btn" onClick={go} disabled={busy || !amt || amt < 1} className="w-full mt-2.5">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <HandCoins className="w-4 h-4" />}
        {amt >= 1 ? `Tip $${Number(amt).toFixed(0)} via Square` : "Pick an amount"}
      </Btn>
    </Card>
  );
};

export const PortalReview = ({ token, reviewLink, alreadyDone }) => {
  const [rating, setRating] = useState(0);
  const [text, setText] = useState("");
  const [done, setDone] = useState(alreadyDone);
  const [shareLink, setShareLink] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const res = await portalReviewApi(token, { rating, text });
      setDone(true);
      setShareLink(res.review_link || "");
      toast.success("Thanks for the feedback!");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  if (done) {
    return (
      <Card title="Your review" testId="portal-review">
        <p className="text-sm text-white/80">Thanks — we read every single one. 🧡</p>
        {(shareLink || (rating >= 4 && reviewLink)) && (
          <a data-testid="portal-google-review-link" href={shareLink || reviewLink} target="_blank" rel="noreferrer"
            className="mt-2 inline-flex items-center gap-1.5 text-sm font-bold text-sky-300 hover:underline">
            Share it on Google too <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </Card>
    );
  }
  return (
    <Card title="How did we do?" testId="portal-review">
      <div className="flex gap-1.5 mb-2.5">
        {[1, 2, 3, 4, 5].map((s) => (
          <button key={s} data-testid={`portal-star-${s}`} onClick={() => setRating(s)}>
            <Star className={`w-7 h-7 transition-colors ${s <= rating ? "fill-amber-400 text-amber-400" : "text-white/25"}`} />
          </button>
        ))}
      </div>
      <textarea data-testid="portal-review-text" rows={2} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Tell us about your move (optional)"
        className="w-full rounded-md bg-white/10 border border-white/15 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-[#E8743B]" />
      <Btn testId="portal-review-submit" onClick={submit} disabled={busy || !rating} className="w-full mt-2.5">
        {busy && <Loader2 className="w-4 h-4 animate-spin" />} Send review
      </Btn>
    </Card>
  );
};
