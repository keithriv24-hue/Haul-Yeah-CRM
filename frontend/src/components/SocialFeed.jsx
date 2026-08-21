import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Facebook, Instagram, ExternalLink, RefreshCw, Lock, MessageCircle, AtSign, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { metaStatusApi, metaFeedApi, metaRefreshApi, apiErrorMessage } from "@/lib/api";

const TYPE_META = {
  comment: { label: "Comment", icon: MessageCircle, cls: "bg-info/12 text-info border-info/25" },
  message: { label: "DM", icon: MessageSquare, cls: "bg-success/12 text-success border-success/25" },
  mention: { label: "Mention", icon: AtSign, cls: "bg-purple-100 text-primary border-primary/20" },
};

const ago = (iso) => {
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
};

const PlaceholderCard = ({ icon: Icon, title, note, testId }) => (
  <div data-testid={testId} className="bg-surface border border-dashed border-border-strong rounded-lg p-5 flex items-start gap-3">
    <div className="w-10 h-10 rounded-lg bg-surface-sunk flex items-center justify-center shrink-0">
      <Icon className="w-5 h-5 text-faint" />
    </div>
    <div>
      <p className="font-semibold text-primary flex items-center gap-1.5">{title} <Lock className="w-3.5 h-3.5 text-faint/70" /></p>
      <p className="text-xs text-faint mt-0.5">{note}</p>
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
          <p className="text-xs text-faint">
            Hook it up on the <Link to="/settings" className="font-semibold text-accent-ink hover:underline" data-testid="social-setup-link">Settings page</Link> — one Facebook sign-in covers the Page and Instagram.
          </p>
        )}
      </div>
    );
  }

  return (
    <div data-testid="social-feed" className="mt-3">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {(status.pages || []).map((pg) => (
          <span key={pg.id} className="text-xs font-semibold text-faint flex items-center gap-1">
            <Facebook className="w-3.5 h-3.5 text-[#1877F2]" /> {pg.name}
            {pg.ig_username && <><span className="text-faint/70">·</span><Instagram className="w-3.5 h-3.5 text-accent-ink" /> @{pg.ig_username}</>}
          </span>
        ))}
        <Button data-testid="social-refresh-btn" variant="outline" size="sm" className="h-8 gap-1.5 text-xs ml-auto" disabled={busy} onClick={refresh}>
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>
      <div className="surface">
        {items === null ? (
          <p className="text-sm text-faint text-center py-10">Loading social activity…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-faint text-center py-10">No social activity yet. New comments, DMs, and mentions land here within 5 minutes.</p>
        ) : (
          items.map((it) => {
            const t = TYPE_META[it.type] || TYPE_META.comment;
            const PIcon = it.platform === "instagram" ? Instagram : Facebook;
            return (
              <div key={it.id} data-testid="social-item" className="flex items-start gap-3 px-4 py-3 border-b border-border last:border-0">
                <div className={`w-9 h-9 rounded-lg border flex items-center justify-center shrink-0 ${it.platform === "instagram" ? "bg-pink-50 text-accent-ink border-accent/25" : "bg-info/10 text-[#1877F2] border-info/25"}`}>
                  <PIcon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-primary">{it.title}</span>
                    <Badge variant="outline" className={`text-[9px] gap-0.5 ${t.cls}`}><t.icon className="w-2.5 h-2.5" /> {t.label}</Badge>
                  </div>
                  {it.body && <p className="text-xs text-faint mt-0.5 line-clamp-2">{it.body}</p>}
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <span className="text-[11px] text-faint">{ago(it.created_at)}</span>
                  <a data-testid="social-open-link" href={it.link} target="_blank" rel="noreferrer"
                     className="text-[11px] font-semibold text-accent-ink hover:underline flex items-center gap-0.5">
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
