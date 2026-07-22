import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { UserPlus, Handshake, Star, Bell, Mail, Copy, Zap, Lock } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/AuthGate";
import { PageTitle, InstructionBanner, EmptyState, LoadingRows } from "@/components/Bits";
import { alertsApi, webhookInfoApi, gmailStatusApi } from "@/lib/api";
import { EmailInbox } from "@/components/EmailInbox";
import { SocialFeed } from "@/components/SocialFeed";

const KIND_ICON = { new_lead: UserPlus, booked: Handshake, review: Star, custom: Bell };
const KIND_COLOR = {
  new_lead: "bg-sky-100 text-sky-700 border-sky-200",
  booked: "bg-emerald-100 text-emerald-700 border-emerald-200",
  review: "bg-yellow-100 text-yellow-700 border-yellow-200",
  custom: "bg-slate-100 text-slate-600 border-slate-200",
};

const ago = (iso) => {
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
};

const LeadTimer = ({ createdAt, contactedAt }) => {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 30000);
    return () => clearInterval(t);
  }, []);
  if (contactedAt) {
    const mins = Math.max(0, Math.round((new Date(contactedAt) - new Date(createdAt)) / 60000));
    return (
      <span data-testid="lead-timer-contacted" className="border rounded-full px-2 py-0.5 text-[11px] font-bold bg-emerald-100 text-emerald-700 border-emerald-300">
        Contacted in {mins}m
      </span>
    );
  }
  const mins = Math.floor((Date.now() - new Date(createdAt).getTime()) / 60000);
  const cls = mins >= 15
    ? "bg-red-600 text-white border-red-600 animate-pulse"
    : mins >= 5
      ? "bg-orange-500 text-white border-orange-500"
      : "bg-emerald-100 text-emerald-700 border-emerald-300";
  return (
    <span data-testid="lead-timer" className={`border rounded-full px-2 py-0.5 text-[11px] font-bold ${cls}`}>
      Uncontacted {mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}m`}
    </span>
  );
};

const AlertRow = ({ a, canOpenLead }) => {
  const Icon = KIND_ICON[a.kind] || Bell;
  const inner = (
    <div className="flex items-start gap-3 px-4 py-3">
      <div className={`w-9 h-9 rounded-lg border flex items-center justify-center shrink-0 ${KIND_COLOR[a.kind] || KIND_COLOR.custom}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`text-sm ${a.unread ? "font-bold text-[#1B2A4A]" : "font-semibold text-slate-600"}`}>{a.title}</span>
          {a.kind === "new_lead" && <LeadTimer createdAt={a.created_at} contactedAt={a.contacted_at} />}
          {a.source === "zapier" && <Badge variant="outline" className="text-[9px] gap-0.5 text-slate-500"><Zap className="w-2.5 h-2.5" /> Zapier</Badge>}
        </div>
        {a.body && <p className="text-xs text-slate-500 mt-0.5">{a.body}</p>}
      </div>
      <span className="text-[11px] text-slate-400 shrink-0">{ago(a.created_at)}</span>
    </div>
  );
  const cls = `block border-b border-slate-100 last:border-0 ${a.unread ? "bg-orange-50/50" : ""} ${canOpenLead && a.lead_id ? "hover:bg-slate-50" : ""}`;
  return canOpenLead && a.lead_id ? (
    <Link data-testid="alert-row" to={`/leads/${a.lead_id}`} className={cls}>{inner}</Link>
  ) : (
    <div data-testid="alert-row" className={cls}>{inner}</div>
  );
};

const ZapierCard = () => {
  const [info, setInfo] = useState(null);
  useEffect(() => {
    webhookInfoApi().then(setInfo).catch(() => {});
  }, []);
  if (!info) return null;
  const url = `${process.env.REACT_APP_BACKEND_URL}${info.path}?token=${info.token}`;
  const copy = () => navigator.clipboard.writeText(url).then(() => toast.success("Webhook URL copied.")).catch(() => toast.error("Couldn't copy."));
  return (
    <div data-testid="zapier-webhook-card" className="bg-white border border-slate-200 rounded-lg p-4 mt-4">
      <h3 className="font-bold text-[#1B2A4A] flex items-center gap-2"><Zap className="w-4 h-4 text-[#E8743B]" /> Push alerts in from Zapier <span className="text-xs font-normal text-slate-400">(only you see this)</span></h3>
      <p className="text-xs text-slate-500 mt-1">
        In Zapier: pick a trigger (new Google review, form entry, anything) → add a <strong>Webhooks by Zapier → POST</strong> step → paste this URL.
        Optional JSON fields: <code className="bg-slate-100 px-1 rounded">kind</code> (new_lead / booked / review / custom), <code className="bg-slate-100 px-1 rounded">title</code>, <code className="bg-slate-100 px-1 rounded">body</code>, <code className="bg-slate-100 px-1 rounded">lead_name</code>.
      </p>
      <div className="flex items-center gap-2 mt-2">
        <code data-testid="zapier-webhook-url" className="flex-1 text-[11px] bg-slate-50 border border-slate-200 rounded px-2 py-1.5 truncate">{url}</code>
        <Button data-testid="zapier-copy-btn" variant="outline" size="sm" className="gap-1.5" onClick={copy}><Copy className="w-3.5 h-3.5" /> Copy</Button>
      </div>
    </div>
  );
};

const ComingSoonCard = ({ icon: Icon, title, note, testId }) => (
  <div data-testid={testId} className="bg-white border border-dashed border-slate-300 rounded-lg p-5 flex items-start gap-3">
    <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
      <Icon className="w-5 h-5 text-slate-400" />
    </div>
    <div>
      <p className="font-semibold text-[#1B2A4A] flex items-center gap-1.5">{title} <Lock className="w-3.5 h-3.5 text-slate-300" /></p>
      <p className="text-xs text-slate-500 mt-0.5">{note}</p>
    </div>
  </div>
);

export default function Notifications() {
  const { role } = useAuth();
  const isOwner = role === "owner";
  const canSocial = role === "owner" || role === "marketing";
  const canOpenLead = role === "owner" || role === "sales";
  const [data, setData] = useState(null);
  const [gmail, setGmail] = useState(null);

  const load = useCallback(() => alertsApi().then(setData).catch(() => setData({ alerts: [] })), []);
  useEffect(() => {
    load();
    gmailStatusApi().then(setGmail).catch(() => setGmail({ mailboxes: [] }));
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  const alerts = data?.alerts || [];
  const connectedBoxes = (gmail?.mailboxes || []).filter((m) => m.connected);
  const pendingBoxes = (gmail?.mailboxes || []).filter((m) => !m.connected);

  const Feed = ({ items }) => (
    <div className="bg-white border border-slate-200 rounded-lg mt-3" data-testid="alerts-feed">
      {items.length === 0 ? (
        <p className="text-sm text-slate-400 text-center py-10">Nothing here yet. New leads, bookings, and reviews will land in this feed.</p>
      ) : (
        items.map((a) => <AlertRow key={a.id} a={a} canOpenLead={canOpenLead} />)
      )}
    </div>
  );

  return (
    <div data-testid="notifications-page">
      <PageTitle title="Notifications" subtitle="Everything that needs eyes, newest first." />
      <InstructionBanner testId="notifications-banner">
        New-lead timers turn orange at 5 minutes and red at 15 — call before that happens. Email and social plug in here once they're connected.
      </InstructionBanner>
      {data === null ? (
        <LoadingRows />
      ) : (
        <Tabs defaultValue="all">
          <TabsList>
            <TabsTrigger data-testid="notif-tab-all" value="all">All</TabsTrigger>
            <TabsTrigger data-testid="notif-tab-email" value="email">Email</TabsTrigger>
            {canSocial && <TabsTrigger data-testid="notif-tab-social" value="social">Social</TabsTrigger>}
            <TabsTrigger data-testid="notif-tab-alerts" value="alerts">Alerts</TabsTrigger>
          </TabsList>
          <TabsContent value="all">
            <Feed items={alerts} />
            {isOwner && <ZapierCard />}
          </TabsContent>
          <TabsContent value="email">
            {connectedBoxes.length > 0 && <EmailInbox mailboxes={connectedBoxes} />}
            {pendingBoxes.length > 0 && (
              <div className="space-y-3 mt-3">
                {pendingBoxes.map((mb) => (
                  <ComingSoonCard
                    key={mb.id}
                    icon={Mail}
                    title={mb.email}
                    testId={`email-placeholder-${mb.id}`}
                    note={mb.id === "owner"
                      ? "Your private inbox. Only you will ever see this one — it stays invisible to everyone else."
                      : "The shared inbox isn't connected yet. The owner hooks it up with Google in Settings — then reading and replying happens right here."}
                  />
                ))}
                {isOwner && (
                  <p className="text-xs text-slate-500">
                    Hook these up on the <Link to="/settings" className="font-semibold text-[#E8743B] hover:underline" data-testid="email-setup-link">Settings page</Link> — takes one Google sign-in per inbox.
                  </p>
                )}
              </div>
            )}
          </TabsContent>
          {canSocial && (
            <TabsContent value="social">
              <SocialFeed isOwner={isOwner} />
            </TabsContent>
          )}
          <TabsContent value="alerts">
            <Feed items={alerts} />
            {isOwner && <ZapierCard />}
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
