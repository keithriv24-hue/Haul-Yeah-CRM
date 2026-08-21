import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Facebook, Instagram, Copy, Unplug, Plug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { metaStatusApi, metaConnectApi, metaDisconnectApi, capiStatusApi, apiErrorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const RESULT_MSG = {
  connected: ["success", "Facebook connected. The Social tab on Notifications is live."],
  denied: ["error", "Facebook sign-in was cancelled. Try connecting again."],
  expired: ["error", "That connect link expired. Start again from here."],
  error: ["error", "Facebook didn't hand back a valid token. Try again and approve every permission."],
  "no-pages": ["error", "That Facebook account doesn't manage any Pages. Sign in with the account that owns the Haul Yeah Page."],
};

export const MetaCard = () => {
  const [status, setStatus] = useState(null);
  const [capi, setCapi] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    metaStatusApi().then(setStatus).catch(() => {});
    capiStatusApi().then(setCapi).catch(() => {});
  };
  useEffect(() => {
    load();
    const params = new URLSearchParams(window.location.search);
    const res = params.get("meta");
    if (res) {
      const [kind, msg] = RESULT_MSG[res] || ["error", "Something went sideways connecting Facebook."];
      toast[kind](msg);
      window.history.replaceState({}, "", "/settings");
    }
  }, []);

  const connect = async () => {
    setBusy(true);
    try {
      const { auth_url } = await metaConnectApi();
      window.location.href = auth_url;
    } catch (e) {
      toast.error(apiErrorMessage(e));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await metaDisconnectApi();
      toast.success("Facebook disconnected.");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  const copyUri = () =>
    navigator.clipboard.writeText(status?.redirect_uri || "").then(() => toast.success("Redirect URI copied.")).catch(() => {});

  if (!status) return null;
  return (
    <div data-testid="meta-settings-card" className="surface p-5 mt-4">
      <h2 className="font-display font-bold text-primary flex items-center gap-2">
        <Facebook className="w-4 h-4 text-accent-ink" /> Facebook &amp; Instagram
      </h2>
      <p className="text-xs text-faint mt-1">
        Connect the business Facebook Page (and its linked Instagram) — new comments, DMs, and mentions land on the Notifications → Social tab with a jump-out link to reply natively.
      </p>

      {!status.configured && (
        <div data-testid="meta-setup-instructions" className="mt-3 border border-warning/25 bg-warning/10 rounded-lg p-4 text-sm text-ink-2">
          <p className="font-semibold text-primary mb-2">One-time setup (about 15 minutes):</p>
          <ol className="list-decimal pl-5 space-y-1 text-xs">
            <li>Go to <strong>developers.facebook.com</strong> → My Apps → <strong>Create App</strong> → pick <strong>Business</strong> type, name it "Haul Yeah Admin".</li>
            <li>On the app dashboard, add the <strong>Facebook Login</strong> product (choose "Web").</li>
            <li><strong>Facebook Login → Settings</strong> → under "Valid OAuth Redirect URIs" paste the URI below → Save.</li>
            <li><strong>App settings → Basic</strong> → copy the <strong>App ID</strong> and <strong>App Secret</strong> and send them to me in the Emergent chat.</li>
            <li>Keep the app in <strong>Development Mode</strong> — since you're the app admin AND the Page admin, everything works without Meta's App Review.</li>
          </ol>
          <div className="flex items-center gap-2 mt-3">
            <code data-testid="meta-redirect-uri" className="flex-1 text-[11px] bg-surface border border-border rounded px-2 py-1.5 truncate">{status.redirect_uri}</code>
            <Button data-testid="meta-copy-uri-btn" variant="outline" size="sm" className="gap-1.5" onClick={copyUri}>
              <Copy className="w-3.5 h-3.5" /> Copy
            </Button>
          </div>
        </div>
      )}

      <div className="mt-3">
        {status.connected ? (
          <div className="space-y-2">
            {(status.pages || []).map((pg) => (
              <div key={pg.id} data-testid={`meta-page-${pg.id}`} className="flex flex-wrap items-center gap-2 border border-border rounded-lg px-3 py-2.5">
                <div className="flex-1 min-w-[200px]">
                  <p className="text-sm font-semibold text-primary flex items-center gap-1.5">
                    <Facebook className="w-3.5 h-3.5 text-[#1877F2]" /> {pg.name}
                  </p>
                  {pg.ig_username && (
                    <p className="text-[11px] text-faint flex items-center gap-1 mt-0.5">
                      <Instagram className="w-3 h-3 text-accent-ink" /> @{pg.ig_username}
                    </p>
                  )}
                </div>
                <Badge variant="outline" className="text-[10px] bg-success/12 text-success border-success/30">
                  Connected {status.connected_at ? fmtDate(status.connected_at.slice(0, 10)) : ""}
                </Badge>
              </div>
            ))}
            <div className="flex items-center gap-2">
              <Button data-testid="meta-reconnect-btn" variant="outline" size="sm" className="gap-1 text-xs" disabled={busy || !status.configured} onClick={connect}>
                <Plug className="w-3.5 h-3.5" /> Reconnect
              </Button>
              <Button data-testid="meta-disconnect-btn" variant="outline" size="sm" className="gap-1 text-xs text-destructive border-destructive/25 hover:bg-destructive/10" disabled={busy} onClick={disconnect}>
                <Unplug className="w-3.5 h-3.5" /> Disconnect
              </Button>
            </div>
          </div>
        ) : (
          <Button data-testid="meta-connect-btn" size="sm" className="gap-1.5 bg-[#1877F2] hover:bg-[#1465cc]" disabled={busy || !status.configured} onClick={connect}>
            <Facebook className="w-3.5 h-3.5" /> Connect with Facebook
          </Button>
        )}
      </div>
      {!status.configured && <p className="text-[11px] text-faint mt-2">The button unlocks once the Meta App ID and Secret are in.</p>}

      {capi && (
        <div data-testid="meta-capi-status" className="mt-4 border-t border-border pt-3">
          <div className="text-sm font-semibold text-primary flex items-center gap-2">
            Conversions API (ad signals)
            {capi.configured ? (
              <Badge variant="outline" className="text-[10px] bg-success/12 text-success border-success/30">On</Badge>
            ) : (
              <Badge variant="outline" className="text-[10px] bg-surface-sunk text-faint border-border-strong">Off</Badge>
            )}
          </div>
          {capi.configured ? (
            <p data-testid="meta-capi-counts" className="text-[11px] text-faint mt-1">
              New leads and paid deposits are sent to Meta so your ads learn from real bookings.
              Sent {capi.sent} · pending {capi.pending} · failed {capi.failed}
              {capi.test_event_code_set && <span className="text-warning"> · test mode on — remove META_TEST_EVENT_CODE when done</span>}
              {capi.last_error && <span className="text-destructive"> · last error: {capi.last_error}</span>}
            </p>
          ) : (
            <p className="text-[11px] text-faint mt-1">
              Add <strong>META_DATASET_ID</strong> and <strong>META_CAPI_ACCESS_TOKEN</strong> (from Events Manager → your dataset → Conversions API → Generate access token) in the secrets panel to start sending Lead + Purchase events.
            </p>
          )}
        </div>
      )}
    </div>
  );
};
