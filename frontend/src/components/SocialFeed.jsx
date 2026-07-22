import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Facebook, Instagram, ExternalLink, RefreshCw, Lock, MessageCircle, AtSign, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { metaStatusApi, metaFeedApi, metaRefreshApi, apiErrorMessage } from "@/lib/api";

const TYPE_META = {
  comment: { label: "Comment", icon: MessageCircle, cls: "bg-sky-100 text-sky-700 border-sky-200" },
  message: { label: "DM", icon: MessageSquare, cls: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  mention: { label: "Mention", icon: AtSign, cls: "bg-purple-100 text-purple-700 border-purple-200" },
};

const ago = (iso) => {
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
};

const PlaceholderCard = ({ icon: Icon, title, note, testId }) => (
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

export const SocialFeed = ({ isOwner }) => {
  const [status, setStatus] = useState(null);
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    metaStatusApi().then((s) => {
      setStatus(s);
      if (s.connected) metaFeedApi().then((d) => setItems(d.items)).catch(() => setItems([]));
    }).catch(() => setStatus({ connected: false }));
  };
  useEffect(load, []);

  const refresh = async () => {
    setBusy(true);
    try {
      const { new_items } = await metaRefreshApi();
      toast.success(new_items ? `${new_items} new item${new_items > 1 ? "s" : ""} pulled in.` : "All caught up — nothing new.");
      metaFeedApi().then((d) => setItems(d.items)).catch(() => {});
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  if (!status) return null;

  if (!status.connected) {
    return (
      <div className="space-y-3 mt-3">
        <PlaceholderCard icon={Facebook} title="Facebook Page" testId="social-placeholder-fb"
          note="Comments, DMs, and mentions show up here once the Meta account is connected. Each one links straight to Facebook to reply." />
        <PlaceholderCard icon={Instagram} title="Instagram" testId="social-placeholder-ig"
          note="Same deal for Instagram — connect once, and new activity lands in this feed." />
        {isOwner && (
          <p className="text-xs text-slate-500">
            Hook it up on the <Link to="/settings" className="font-semibold text-[#E8743B] hover:underline" data-testid="social-setup-link">Settings page</Link> — one Facebook sign-in covers the Page and Instagram.
          </p>
        )}
      </div>
    );
  }

  return (
    <div data-testid="social-feed" className="mt-3">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {(status.pages || []).map((pg) => (
          <span key={pg.id} className="text-xs font-semibold text-slate-500 flex items-center gap-1">
            <Facebook className="w-3.5 h-3.5 text-[#1877F2]" /> {pg.name}
            {pg.ig_username && <><span className="text-slate-300">·</span><Instagram className="w-3.5 h-3.5 text-pink-500" /> @{pg.ig_username}</>}
          </span>
        ))}
        <Button data-testid="social-refresh-btn" variant="outline" size="sm" className="h-8 gap-1.5 text-xs ml-auto" disabled={busy} onClick={refresh}>
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>
      <div className="bg-white border border-slate-200 rounded-lg">
        {items === null ? (
          <p className="text-sm text-slate-400 text-center py-10">Loading social activity…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-10">No social activity yet. New comments, DMs, and mentions land here within 5 minutes.</p>
        ) : (
          items.map((it) => {
            const t = TYPE_META[it.type] || TYPE_META.comment;
            const PIcon = it.platform === "instagram" ? Instagram : Facebook;
            return (
              <div key={it.id} data-testid="social-item" className="flex items-start gap-3 px-4 py-3 border-b border-slate-100 last:border-0">
                <div className={`w-9 h-9 rounded-lg border flex items-center justify-center shrink-0 ${it.platform === "instagram" ? "bg-pink-50 text-pink-600 border-pink-200" : "bg-blue-50 text-[#1877F2] border-blue-200"}`}>
                  <PIcon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-[#1B2A4A]">{it.title}</span>
                    <Badge variant="outline" className={`text-[9px] gap-0.5 ${t.cls}`}><t.icon className="w-2.5 h-2.5" /> {t.label}</Badge>
                  </div>
                  {it.body && <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{it.body}</p>}
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <span className="text-[11px] text-slate-400">{ago(it.created_at)}</span>
                  <a data-testid="social-open-link" href={it.link} target="_blank" rel="noreferrer"
                     className="text-[11px] font-semibold text-[#E8743B] hover:underline flex items-center gap-0.5">
                    Reply on {it.platform === "instagram" ? "Instagram" : "Facebook"} <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
