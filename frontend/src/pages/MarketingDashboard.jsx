import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Megaphone, Plus, Trash2, Star, DollarSign, Timer, TrendingUp, Users, CalendarRange, Loader2, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/components/AuthGate";
import { useApp } from "@/context/AppContext";
import { SearchBar, searchMatch } from "@/components/Bits";
import { fmtMoney, fmtDate } from "@/lib/format";
import {
  marketingOverviewApi, listAdSpendApi, addAdSpendApi, deleteAdSpendApi,
  getMktThresholdsApi, saveMktThresholdsApi, marketingMarginApi,
  listReviewRequestsApi, patchReviewRequestApi, apiErrorMessage,
} from "@/lib/api";

const iso = (d) => d.toISOString().slice(0, 10);
const daysAgo = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return iso(d);
};
const speedLabel = (mins) =>
  mins == null ? "—" : mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
const pct = (num, den) => (den ? Math.round((num / den) * 100) : null);

const CHIP = {
  green: "bg-emerald-100 text-emerald-800 border-emerald-300",
  amber: "bg-amber-100 text-amber-800 border-amber-300",
  red: "bg-red-100 text-red-700 border-red-300",
  slate: "bg-slate-100 text-slate-500 border-slate-200",
};
const Chip = ({ tone, children, testid }) => (
  <span data-testid={testid} className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${CHIP[tone] || CHIP.slate}`}>
    {children}
  </span>
);

const cplTone = (v, t) => (v == null ? "slate" : v <= t.cplGreen ? "green" : v >= t.cplRed ? "red" : "amber");
const bookTone = (v, t) => (v == null ? "slate" : v >= t.bookingGreen ? "green" : v <= t.bookingRed ? "red" : "amber");
const roasTone = (v) => (v == null ? "slate" : v >= 3 ? "green" : v >= 1.5 ? "amber" : "red");

const KpiCard = ({ icon: Icon, label, value, sub, testid, blur }) => (
  <div data-testid={testid} className="bg-white rounded-lg border border-slate-200 p-4">
    <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">
      <Icon className="w-4 h-4 text-[#E8743B]" /> {label}
    </div>
    <p className={`text-2xl font-bold text-[#1B2A4A] mt-1.5 ${blur ? "blur-sm select-none" : ""}`}>{value}</p>
    {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
  </div>
);

const Funnel = ({ funnel }) => {
  const max = funnel[0]?.count || 1;
  return (
    <div className="space-y-2">
      {funnel.map((f, i) => {
        const conv = i === 0 ? null : pct(f.count, funnel[i - 1].count || 0);
        return (
          <div key={f.stage} data-testid={`funnel-row-${f.stage.toLowerCase()}`} className="flex items-center gap-3">
            <span className="w-24 text-sm font-semibold text-[#1B2A4A]">{f.stage}</span>
            <div className="flex-1 h-7 bg-slate-100 rounded overflow-hidden">
              <div
                className="h-full rounded bg-[#E8743B] transition-all"
                style={{ width: `${Math.max(4, (f.count / max) * 100)}%`, opacity: 1 - i * 0.13 }}
              />
            </div>
            <span className="w-10 text-right text-sm font-bold text-[#1B2A4A]">{f.count}</span>
            <span className="w-14 text-right text-xs text-slate-500">{conv == null ? "" : `${conv}%`}</span>
          </div>
        );
      })}
      <p className="text-[11px] text-slate-400 pt-1">The % next to each step = how many made it from the step above.</p>
    </div>
  );
};

const SourcesTable = ({ sources, blur }) => (
  <div className="overflow-x-auto">
    <table data-testid="sources-table" className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-slate-500 uppercase tracking-wide border-b border-slate-100">
          <th className="py-2 pr-3">Source</th>
          <th className="py-2 px-2 text-right">Leads</th>
          <th className="py-2 px-2 text-right">Contacted</th>
          <th className="py-2 px-2 text-right">Quoted</th>
          <th className="py-2 px-2 text-right">Booked</th>
          <th className="py-2 px-2 text-right">Booking %</th>
          <th className="py-2 px-2 text-right">Revenue (paid)</th>
          <th className="py-2 pl-2 text-right">Speed to lead</th>
        </tr>
      </thead>
      <tbody>
        {sources.map((s) => (
          <tr key={s.key} data-testid="source-row" className="border-b border-slate-50">
            <td className="py-2.5 pr-3 font-semibold text-[#1B2A4A]">{s.key}</td>
            <td className="py-2.5 px-2 text-right">{s.leads}</td>
            <td className="py-2.5 px-2 text-right">{s.contacted}</td>
            <td className="py-2.5 px-2 text-right">{s.quoted}</td>
            <td className="py-2.5 px-2 text-right font-semibold">{s.booked}</td>
            <td className="py-2.5 px-2 text-right">{pct(s.booked, s.leads) == null ? "—" : `${pct(s.booked, s.leads)}%`}</td>
            <td className={`py-2.5 px-2 text-right font-semibold text-emerald-700 ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(s.revenue)}</td>
            <td className="py-2.5 pl-2 text-right text-slate-600">{speedLabel(s.avg_speed_minutes)}</td>
          </tr>
        ))}
        {sources.length === 0 && (
          <tr><td colSpan={8} className="py-6 text-center text-slate-400 text-sm">No leads in this date range yet.</td></tr>
        )}
      </tbody>
    </table>
  </div>
);

const OverviewTab = ({ overview, blur, query }) => {
  if (!overview) return <div className="py-10 text-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin inline" /></div>;
  const t = overview.totals;
  const sources = overview.sources.filter((s) => searchMatch(query, s.key));
  const campaigns = overview.campaigns.filter((c) => searchMatch(query, c.key));
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <KpiCard icon={Users} label="Leads" value={t.leads} testid="kpi-mkt-leads" />
        <KpiCard icon={TrendingUp} label="Booked" value={t.booked} testid="kpi-mkt-booked" />
        <KpiCard icon={TrendingUp} label="Booking rate" value={pct(t.booked, t.leads) == null ? "—" : `${pct(t.booked, t.leads)}%`} testid="kpi-mkt-booking-rate" />
        <KpiCard icon={DollarSign} label="Revenue (paid)" value={fmtMoney(t.revenue)} sub="Paid Square invoices only" testid="kpi-mkt-revenue" blur={blur} />
        <KpiCard icon={Timer} label="Speed to lead" value={speedLabel(t.avg_speed_minutes)} sub={t.speed_tracked ? `Tracked on ${t.speed_tracked} lead${t.speed_tracked === 1 ? "" : "s"}` : "No status changes tracked yet"} testid="kpi-mkt-speed" />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="font-bold text-[#1B2A4A] mb-3">Funnel</h2>
          <Funnel funnel={overview.funnel} />
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="font-bold text-[#1B2A4A] mb-3">Campaigns &amp; ads</h2>
          <table data-testid="campaigns-table" className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-wide border-b border-slate-100">
                <th className="py-2 pr-3">Campaign / Ad</th>
                <th className="py-2 px-2 text-right">Leads</th>
                <th className="py-2 px-2 text-right">Booked</th>
                <th className="py-2 pl-2 text-right">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => (
                <tr key={c.key} data-testid="campaign-row" className="border-b border-slate-50">
                  <td className="py-2 pr-3 font-medium text-[#1B2A4A]">{c.key}</td>
                  <td className="py-2 px-2 text-right">{c.leads}</td>
                  <td className="py-2 px-2 text-right">{c.booked}</td>
                  <td className={`py-2 pl-2 text-right text-emerald-700 font-semibold ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(c.revenue)}</td>
                </tr>
              ))}
              {campaigns.length === 0 && (
                <tr><td colSpan={4} className="py-6 text-center text-slate-400 text-sm">No UTM campaigns captured yet. They show up automatically from your Tally form.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="font-bold text-[#1B2A4A] mb-3">By source</h2>
        <SourcesTable sources={sources} blur={blur} />
      </div>
    </div>
  );
};

const PLATFORMS = ["Meta", "Google", "Other"];

const AdSpendTab = ({ overview, range, isOwner, blur, query }) => {
  const [entries, setEntries] = useState(null);
  const [thresholds, setThresholds] = useState(null);
  const [tDraft, setTDraft] = useState(null);
  const [form, setForm] = useState({ platform: "Meta", campaign: "", date_start: range.start, date_end: range.end, amount: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    listAdSpendApi().then(setEntries).catch((e) => toast.error(apiErrorMessage(e)));
    getMktThresholdsApi().then((t) => { setThresholds(t); setTDraft(t); }).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    setBusy(true);
    try {
      await addAdSpendApi({ ...form, amount: Number(form.amount) });
      toast.success("Spend logged.");
      setForm((f) => ({ ...f, campaign: "", amount: "" }));
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  const remove = async (id) => {
    try {
      await deleteAdSpendApi(id);
      setEntries((list) => list.filter((e) => e.id !== id));
      toast.success("Spend entry removed.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const saveThresholds = async () => {
    try {
      const saved = await saveMktThresholdsApi({
        cplGreen: Number(tDraft.cplGreen), cplRed: Number(tDraft.cplRed),
        bookingGreen: Number(tDraft.bookingGreen), bookingRed: Number(tDraft.bookingRed),
      });
      setThresholds(saved);
      setTDraft(saved);
      toast.success("Thresholds saved.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const perf = useMemo(() => {
    if (!entries) return [];
    const inRange = entries.filter((e) => e.date_start <= range.end && e.date_end >= range.start);
    const spendBy = {};
    for (const e of inRange) {
      const k = e.campaign.trim().toLowerCase();
      spendBy[k] = { name: e.campaign.trim(), spend: (spendBy[k]?.spend || 0) + e.amount };
    }
    const stats = {};
    for (const c of overview?.campaigns || []) stats[c.key.trim().toLowerCase()] = c;
    return Object.entries(spendBy).map(([k, v]) => {
      const s = stats[k] || { leads: 0, booked: 0, revenue: 0 };
      return {
        campaign: v.name, spend: v.spend, leads: s.leads, booked: s.booked, revenue: s.revenue,
        cpl: s.leads ? v.spend / s.leads : null,
        costPerBooked: s.booked ? v.spend / s.booked : null,
        bookingRate: s.leads ? (s.booked / s.leads) * 100 : null,
        roas: v.spend ? s.revenue / v.spend : null,
      };
    }).filter((r) => searchMatch(query, r.campaign)).sort((a, b) => b.spend - a.spend);
  }, [entries, overview, range, query]);

  const totals = useMemo(() => {
    const t = perf.reduce((acc, r) => ({
      spend: acc.spend + r.spend, leads: acc.leads + r.leads, booked: acc.booked + r.booked, revenue: acc.revenue + r.revenue,
    }), { spend: 0, leads: 0, booked: 0, revenue: 0 });
    return {
      ...t,
      cpl: t.leads ? t.spend / t.leads : null,
      costPerBooked: t.booked ? t.spend / t.booked : null,
      bookingRate: t.leads ? (t.booked / t.leads) * 100 : null,
      roas: t.spend ? t.revenue / t.spend : null,
    };
  }, [perf]);

  const th = thresholds || { cplGreen: 20, cplRed: 25, bookingGreen: 20, bookingRed: 15 };
  const entriesShown = (entries || []).filter((e) => searchMatch(query, e.campaign, e.platform));

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="font-bold text-[#1B2A4A] mb-3 flex items-center gap-2"><Plus className="w-4 h-4 text-[#E8743B]" /> Log ad spend</h2>
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-2 items-end">
          <div>
            <Label className="text-xs">Platform</Label>
            <Select value={form.platform} onValueChange={(v) => setForm((f) => ({ ...f, platform: v }))}>
              <SelectTrigger data-testid="adspend-platform-select" className="h-9"><SelectValue /></SelectTrigger>
              <SelectContent>{PLATFORMS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Campaign</Label>
            <Input data-testid="adspend-campaign-input" className="h-9" list="known-campaigns" value={form.campaign}
              onChange={(e) => setForm((f) => ({ ...f, campaign: e.target.value }))} placeholder="Spring Movers" />
            <datalist id="known-campaigns">
              {(overview?.known_campaigns || []).map((c) => <option key={c} value={c} />)}
            </datalist>
          </div>
          <div>
            <Label className="text-xs">From</Label>
            <Input data-testid="adspend-start-input" className="h-9" type="date" value={form.date_start} onChange={(e) => setForm((f) => ({ ...f, date_start: e.target.value }))} />
          </div>
          <div>
            <Label className="text-xs">To</Label>
            <Input data-testid="adspend-end-input" className="h-9" type="date" value={form.date_end} onChange={(e) => setForm((f) => ({ ...f, date_end: e.target.value }))} />
          </div>
          <div>
            <Label className="text-xs">Amount ($)</Label>
            <Input data-testid="adspend-amount-input" className="h-9" type="number" min="0" value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} placeholder="250" />
          </div>
          <Button data-testid="adspend-add-btn" onClick={add} disabled={busy || !form.campaign.trim() || !Number(form.amount)} className="h-9 gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]">
            <Plus className="w-4 h-4" /> Add
          </Button>
        </div>
      </div>

      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="font-bold text-[#1B2A4A] mb-1">How the ads are doing</h2>
        <p className="text-xs text-slate-400 mb-3">Spend entries that touch the picked date range, matched to leads by campaign name. Revenue = paid Square invoices only.</p>
        <div className="overflow-x-auto">
          <table data-testid="perf-table" className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-wide border-b border-slate-100">
                <th className="py-2 pr-3">Campaign</th>
                <th className="py-2 px-2 text-right">Spend</th>
                <th className="py-2 px-2 text-right">Leads</th>
                <th className="py-2 px-2 text-right">CPL</th>
                <th className="py-2 px-2 text-right">Booked</th>
                <th className="py-2 px-2 text-right">Cost / booked</th>
                <th className="py-2 px-2 text-right">Booking rate</th>
                <th className="py-2 px-2 text-right">Revenue</th>
                <th className="py-2 pl-2 text-right">ROAS</th>
              </tr>
            </thead>
            <tbody>
              {perf.map((r) => (
                <tr key={r.campaign} data-testid="perf-row" className="border-b border-slate-50">
                  <td className="py-2.5 pr-3 font-semibold text-[#1B2A4A]">{r.campaign}</td>
                  <td className={`py-2.5 px-2 text-right ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(r.spend)}</td>
                  <td className="py-2.5 px-2 text-right">{r.leads}</td>
                  <td className="py-2.5 px-2 text-right"><Chip tone={cplTone(r.cpl, th)} testid="perf-cpl-chip">{r.cpl == null ? "—" : fmtMoney(r.cpl)}</Chip></td>
                  <td className="py-2.5 px-2 text-right">{r.booked}</td>
                  <td className="py-2.5 px-2 text-right">{r.costPerBooked == null ? "—" : fmtMoney(r.costPerBooked)}</td>
                  <td className="py-2.5 px-2 text-right"><Chip tone={bookTone(r.bookingRate, th)} testid="perf-booking-chip">{r.bookingRate == null ? "—" : `${Math.round(r.bookingRate)}%`}</Chip></td>
                  <td className={`py-2.5 px-2 text-right text-emerald-700 font-semibold ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(r.revenue)}</td>
                  <td className="py-2.5 pl-2 text-right"><Chip tone={roasTone(r.roas)} testid="perf-roas-chip">{r.roas == null ? "—" : `${r.roas.toFixed(1)}x`}</Chip></td>
                </tr>
              ))}
              {perf.length > 0 && (
                <tr data-testid="perf-total-row" className="border-t-2 border-slate-200 font-bold">
                  <td className="py-2.5 pr-3 text-[#1B2A4A]">All ads</td>
                  <td className={`py-2.5 px-2 text-right ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(totals.spend)}</td>
                  <td className="py-2.5 px-2 text-right">{totals.leads}</td>
                  <td className="py-2.5 px-2 text-right"><Chip tone={cplTone(totals.cpl, th)}>{totals.cpl == null ? "—" : fmtMoney(totals.cpl)}</Chip></td>
                  <td className="py-2.5 px-2 text-right">{totals.booked}</td>
                  <td className="py-2.5 px-2 text-right">{totals.costPerBooked == null ? "—" : fmtMoney(totals.costPerBooked)}</td>
                  <td className="py-2.5 px-2 text-right"><Chip tone={bookTone(totals.bookingRate, th)}>{totals.bookingRate == null ? "—" : `${Math.round(totals.bookingRate)}%`}</Chip></td>
                  <td className={`py-2.5 px-2 text-right text-emerald-700 ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(totals.revenue)}</td>
                  <td className="py-2.5 pl-2 text-right"><Chip tone={roasTone(totals.roas)}>{totals.roas == null ? "—" : `${totals.roas.toFixed(1)}x`}</Chip></td>
                </tr>
              )}
              {perf.length === 0 && (
                <tr><td colSpan={9} className="py-6 text-center text-slate-400 text-sm">Log your first spend entry above to see CPL, booking rate, and ROAS.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="font-bold text-[#1B2A4A] mb-3">Spend log</h2>
          <div className="space-y-1.5">
            {entriesShown.map((e) => (
              <div key={e.id} data-testid="adspend-entry-row" className="flex items-center gap-2 text-sm border-b border-slate-50 pb-1.5">
                <Badge variant="outline" className="text-[10px]">{e.platform}</Badge>
                <span className="flex-1 font-medium text-[#1B2A4A] truncate">{e.campaign}</span>
                <span className="text-xs text-slate-400">{fmtDate(e.date_start)} → {fmtDate(e.date_end)}</span>
                <span className={`font-semibold ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(e.amount)}</span>
                <Button data-testid="adspend-delete-btn" variant="ghost" size="sm" className="h-7 px-1.5 text-red-500 hover:text-red-700" onClick={() => remove(e.id)}>
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            ))}
            {entries && entriesShown.length === 0 && <p className="text-sm text-slate-400 py-4 text-center">{query ? "No spend entries match that search." : "Nothing logged yet."}</p>}
          </div>
        </div>

        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="font-bold text-[#1B2A4A] mb-1">Color thresholds</h2>
          <p className="text-xs text-slate-400 mb-3">Green means healthy, red means look at it. {!isOwner && "Only the owner can change these."}</p>
          {tDraft && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">CPL green at or under ($)</Label>
                <Input data-testid="threshold-cpl-green" className="h-9" type="number" disabled={!isOwner} value={tDraft.cplGreen} onChange={(e) => setTDraft((t) => ({ ...t, cplGreen: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">CPL red at or over ($)</Label>
                <Input data-testid="threshold-cpl-red" className="h-9" type="number" disabled={!isOwner} value={tDraft.cplRed} onChange={(e) => setTDraft((t) => ({ ...t, cplRed: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">Booking rate green at or over (%)</Label>
                <Input data-testid="threshold-booking-green" className="h-9" type="number" disabled={!isOwner} value={tDraft.bookingGreen} onChange={(e) => setTDraft((t) => ({ ...t, bookingGreen: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">Booking rate red at or under (%)</Label>
                <Input data-testid="threshold-booking-red" className="h-9" type="number" disabled={!isOwner} value={tDraft.bookingRed} onChange={(e) => setTDraft((t) => ({ ...t, bookingRed: e.target.value }))} />
              </div>
              {isOwner && (
                <Button data-testid="threshold-save-btn" onClick={saveThresholds} className="col-span-2 bg-[#1B2A4A] hover:bg-[#152238]">Save thresholds</Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const ReviewsTab = ({ query }) => {
  const [requests, setRequests] = useState(null);
  useEffect(() => {
    listReviewRequestsApi().then(setRequests).catch((e) => toast.error(apiErrorMessage(e)));
  }, []);

  const shown = (requests || []).filter((r) => searchMatch(query, r.crew_name, r.customer?.name, r.channel, r.invoice_number));

  const patch = async (id, payload) => {
    try {
      const updated = await patchReviewRequestApi(id, payload);
      setRequests((list) => list.map((r) => (r.id === id ? { ...r, review: updated.review } : r)));
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const received = (requests || []).filter((r) => r.review?.received);
  const starred = received.filter((r) => r.review?.stars);
  const avgStars = starred.length ? (starred.reduce((s, r) => s + r.review.stars, 0) / starred.length).toFixed(1) : null;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <h2 className="font-bold text-[#1B2A4A] flex-1">Review requests</h2>
        <Chip tone="slate" testid="reviews-asked-chip">{(requests || []).length} asked</Chip>
        <Chip tone="green" testid="reviews-received-chip">{received.length} came in</Chip>
        {avgStars && <Chip tone="amber" testid="reviews-avg-chip">★ {avgStars} average</Chip>}
      </div>
      <div className="overflow-x-auto">
        <table data-testid="reviews-table" className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500 uppercase tracking-wide border-b border-slate-100">
              <th className="py-2 pr-3">Sent</th>
              <th className="py-2 px-2">Crew</th>
              <th className="py-2 px-2">How</th>
              <th className="py-2 px-2">Customer</th>
              <th className="py-2 px-2">Job</th>
              <th className="py-2 px-2 text-center">Review came in?</th>
              <th className="py-2 pl-2">Stars</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} data-testid="review-row" className="border-b border-slate-50">
                <td className="py-2.5 pr-3 text-slate-600 whitespace-nowrap">{fmtDate(r.sent_at)}</td>
                <td className="py-2.5 px-2 font-medium text-[#1B2A4A]">{r.crew_name}</td>
                <td className="py-2.5 px-2"><Badge variant="outline" className="text-[10px] uppercase">{r.channel}</Badge></td>
                <td className="py-2.5 px-2">{r.customer?.name || "—"}</td>
                <td className="py-2.5 px-2 text-slate-500">{r.invoice_number ? `#${r.invoice_number}` : "—"}</td>
                <td className="py-2.5 px-2 text-center">
                  <Checkbox data-testid="review-received-checkbox" checked={!!r.review?.received} onCheckedChange={(v) => patch(r.id, { review_received: !!v })} />
                </td>
                <td className="py-2.5 pl-2">
                  <div className="flex gap-0.5">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button key={n} data-testid={`review-star-${n}`} onClick={() => patch(r.id, { stars: n })} className="p-0.5">
                        <Star className={`w-4 h-4 ${r.review?.stars >= n ? "fill-amber-400 text-amber-400" : "text-slate-300"}`} />
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
            {requests && shown.length === 0 && (
              <tr><td colSpan={7} className="py-6 text-center text-slate-400 text-sm">{query ? "No review requests match that search." : "No review requests yet. Crew send them right after they finish a job."}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const MarginTab = ({ range, blur, query }) => {
  const [data, setData] = useState(null);
  useEffect(() => {
    setData(null);
    marketingMarginApi(range.start, range.end).then(setData).catch((e) => toast.error(apiErrorMessage(e)));
  }, [range]);

  if (!data) return <div className="py-10 text-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin inline" /></div>;
  const shown = data.sources.filter((s) => searchMatch(query, s.source));
  const totals = shown.reduce((a, s) => ({ revenue: a.revenue + s.revenue, labor_cost: a.labor_cost + s.labor_cost, margin: a.margin + s.margin }), { revenue: 0, labor_cost: 0, margin: 0 });

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex items-center gap-2 mb-1">
        <Lock className="w-4 h-4 text-[#E8743B]" />
        <h2 className="font-bold text-[#1B2A4A]">True margin — owner's eyes only</h2>
      </div>
      <p className="text-xs text-slate-400 mb-3">Paid Square revenue minus what the crew's clocked hours cost you, grouped by where the lead came from.</p>
      <div className="overflow-x-auto">
        <table data-testid="margin-table" className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500 uppercase tracking-wide border-b border-slate-100">
              <th className="py-2 pr-3">Source</th>
              <th className="py-2 px-2 text-right">Revenue (paid)</th>
              <th className="py-2 px-2 text-right">Crew labor</th>
              <th className="py-2 px-2 text-right">True margin</th>
              <th className="py-2 pl-2 text-right">Margin %</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((s) => (
              <tr key={s.source} data-testid="margin-row" className="border-b border-slate-50">
                <td className="py-2.5 pr-3 font-semibold text-[#1B2A4A]">{s.source}</td>
                <td className={`py-2.5 px-2 text-right ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(s.revenue)}</td>
                <td className={`py-2.5 px-2 text-right text-red-600 ${blur ? "blur-sm select-none" : ""}`}>−{fmtMoney(s.labor_cost)}</td>
                <td className={`py-2.5 px-2 text-right font-bold ${s.margin >= 0 ? "text-emerald-700" : "text-red-600"} ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(s.margin)}</td>
                <td className="py-2.5 pl-2 text-right">{s.margin_pct == null ? "—" : `${s.margin_pct}%`}</td>
              </tr>
            ))}
            {shown.length > 0 && (
              <tr data-testid="margin-total-row" className="border-t-2 border-slate-200 font-bold">
                <td className="py-2.5 pr-3 text-[#1B2A4A]">Everything</td>
                <td className={`py-2.5 px-2 text-right ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(totals.revenue)}</td>
                <td className={`py-2.5 px-2 text-right text-red-600 ${blur ? "blur-sm select-none" : ""}`}>−{fmtMoney(totals.labor_cost)}</td>
                <td className={`py-2.5 px-2 text-right ${totals.margin >= 0 ? "text-emerald-700" : "text-red-600"} ${blur ? "blur-sm select-none" : ""}`}>{fmtMoney(totals.margin)}</td>
                <td className="py-2.5 pl-2 text-right">{totals.revenue ? `${Math.round((totals.margin / totals.revenue) * 100)}%` : "—"}</td>
              </tr>
            )}
            {shown.length === 0 && (
              <tr><td colSpan={5} className="py-6 text-center text-slate-400 text-sm">{query ? "No sources match that search." : "No paid revenue or labor in this range yet."}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default function MarketingDashboard() {
  const { role } = useAuth();
  const { privacy } = useApp();
  const isOwner = role === "owner";
  const [range, setRange] = useState({ start: daysAgo(29), end: iso(new Date()) });
  const [overview, setOverview] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!range.start || !range.end || range.start > range.end) return;
    setOverview(null);
    marketingOverviewApi(range.start, range.end)
      .then(setOverview)
      .catch((e) => toast.error(apiErrorMessage(e)));
  }, [range]);

  const preset = (days) => setRange({ start: daysAgo(days - 1), end: iso(new Date()) });

  return (
    <div data-testid="marketing-dashboard" className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-display text-2xl font-bold text-[#1B2A4A] flex items-center gap-2 flex-1">
          <Megaphone className="w-6 h-6 text-[#E8743B]" /> Marketing
        </h1>
        <div className="flex items-center gap-1.5">
          {[7, 30, 90].map((d) => (
            <Button key={d} data-testid={`mkt-preset-${d}`} variant="outline" size="sm" className="h-8 text-xs" onClick={() => preset(d)}>
              {d} days
            </Button>
          ))}
        </div>
        <div className="flex items-center gap-1.5 text-sm">
          <CalendarRange className="w-4 h-4 text-slate-400" />
          <Input data-testid="mkt-range-start" type="date" className="h-8 w-36" value={range.start} onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))} />
          <span className="text-slate-400">→</span>
          <Input data-testid="mkt-range-end" type="date" className="h-8 w-36" value={range.end} onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))} />
        </div>
      </div>

      <SearchBar value={query} onChange={setQuery} placeholder="Search source, campaign, crew, or customer…" testId="marketing-search-input" />

      {overview && overview.airtable_available === false && role === "marketing" && (
        <div data-testid="mkt-airtable-banner" className="rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-sm px-4 py-2.5">
          Lead numbers need the Airtable connection. Add the AIRTABLE_API_KEY and refresh — spend logging still works meanwhile.
        </div>
      )}

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger data-testid="mkt-tab-overview" value="overview">Overview</TabsTrigger>
          <TabsTrigger data-testid="mkt-tab-adspend" value="adspend">Ad Spend</TabsTrigger>
          <TabsTrigger data-testid="mkt-tab-reviews" value="reviews">Reviews</TabsTrigger>
          {isOwner && <TabsTrigger data-testid="mkt-tab-margin" value="margin">True Margin</TabsTrigger>}
        </TabsList>
        <TabsContent value="overview" className="mt-4"><OverviewTab overview={overview} blur={privacy} query={query} /></TabsContent>
        <TabsContent value="adspend" className="mt-4"><AdSpendTab overview={overview} range={range} isOwner={isOwner} blur={privacy} query={query} /></TabsContent>
        <TabsContent value="reviews" className="mt-4"><ReviewsTab query={query} /></TabsContent>
        {isOwner && <TabsContent value="margin" className="mt-4"><MarginTab range={range} blur={privacy} query={query} /></TabsContent>}
      </Tabs>
    </div>
  );
}
