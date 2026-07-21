import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, Copy, Unplug, Plug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { gmailStatusApi, gmailConnectApi, gmailDisconnectApi, apiErrorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const RESULT_MSG = {
  connected: ["success", "Gmail inbox connected. Check the Notifications page."],
  denied: ["error", "Google sign-in was cancelled or the link expired. Try connecting again."],
  expired: ["error", "That connect link expired. Start again from here."],
  error: ["error", "Google didn't hand back a valid token. Try again — make sure you approve all permissions."],
  "wrong-account": ["error", "Wrong Google account — sign in with the mailbox shown on the button."],
};

export const GmailCard = () => {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => gmailStatusApi().then(setStatus).catch(() => {});
  useEffect(() => {
    load();
    const params = new URLSearchParams(window.location.search);
    const res = params.get("gmail");
    if (res) {
      const [kind, msg] = RESULT_MSG[res] || ["error", "Something went sideways connecting Gmail."];
      toast[kind](msg);
      window.history.replaceState({}, "", "/settings");
    }
  }, []);

  const connect = async (id) => {
    setBusy(true);
    try {
      const { auth_url } = await gmailConnectApi(id);
      window.location.href = auth_url;
    } catch (e) {
      toast.error(apiErrorMessage(e));
      setBusy(false);
    }
  };

  const disconnect = async (id) => {
    setBusy(true);
    try {
      await gmailDisconnectApi(id);
      toast.success("Mailbox disconnected.");
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
    <div data-testid="gmail-settings-card" className="bg-white border border-slate-200 rounded-lg p-5 mt-4">
      <h2 className="font-display font-bold text-[#1B2A4A] flex items-center gap-2">
        <Mail className="w-4 h-4 text-[#E8743B]" /> Email inboxes
      </h2>
      <p className="text-xs text-slate-500 mt-1">
        Connect the business Gmail accounts with Google sign-in — no passwords ever stored. Emails show up on the Notifications page.
      </p>

      {!status.configured && (
        <div data-testid="gmail-setup-instructions" className="mt-3 border border-amber-200 bg-amber-50/70 rounded-lg p-4 text-sm text-slate-700">
          <p className="font-semibold text-[#1B2A4A] mb-2">One-time setup (about 10 minutes):</p>
          <ol className="list-decimal pl-5 space-y-1 text-xs">
            <li>Go to <strong>console.cloud.google.com</strong> → create a project (name it "Haul Yeah Admin").</li>
            <li><strong>APIs &amp; Services → Library</strong> → search "Gmail API" → Enable.</li>
            <li><strong>OAuth consent screen</strong> → External → fill in app name + your email → under <strong>Test users</strong> add contact@haulyeahmoves.com and keithrivera@haulyeahmoves.com → Save.</li>
            <li><strong>Credentials → Create Credentials → OAuth client ID → Web application</strong>. Under "Authorized redirect URIs" paste the URI below.</li>
            <li>Copy the <strong>Client ID</strong> and <strong>Client Secret</strong> it gives you and send them to me in the Emergent chat — I'll wire them in and the Connect buttons below light up.</li>
          </ol>
          <div className="flex items-center gap-2 mt-3">
            <code data-testid="gmail-redirect-uri" className="flex-1 text-[11px] bg-white border border-slate-200 rounded px-2 py-1.5 truncate">{status.redirect_uri}</code>
            <Button data-testid="gmail-copy-uri-btn" variant="outline" size="sm" className="gap-1.5" onClick={copyUri}>
              <Copy className="w-3.5 h-3.5" /> Copy
            </Button>
          </div>
        </div>
      )}

      <div className="mt-3 space-y-2">
        {(status.mailboxes || []).map((mb) => (
          <div key={mb.id} data-testid={`gmail-mailbox-${mb.id}`} className="flex flex-wrap items-center gap-2 border border-slate-200 rounded-lg px-3 py-2.5">
            <div className="flex-1 min-w-[200px]">
              <p className="text-sm font-semibold text-[#1B2A4A]">{mb.email}</p>
              <p className="text-[11px] text-slate-400">{mb.label}</p>
            </div>
            {mb.connected ? (
              <>
                <Badge variant="outline" className="text-[10px] bg-emerald-100 text-emerald-700 border-emerald-300">
                  Connected {mb.connected_at ? fmtDate(mb.connected_at.slice(0, 10)) : ""}
                </Badge>
                <Button data-testid={`gmail-reconnect-${mb.id}`} variant="outline" size="sm" className="gap-1 text-xs" disabled={busy || !status.configured} onClick={() => connect(mb.id)}>
                  <Plug className="w-3.5 h-3.5" /> Reconnect
                </Button>
                <Button data-testid={`gmail-disconnect-${mb.id}`} variant="outline" size="sm" className="gap-1 text-xs text-red-600 border-red-200 hover:bg-red-50" disabled={busy} onClick={() => disconnect(mb.id)}>
                  <Unplug className="w-3.5 h-3.5" /> Disconnect
                </Button>
              </>
            ) : (
              <Button data-testid={`gmail-connect-${mb.id}`} size="sm" className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]" disabled={busy || !status.configured} onClick={() => connect(mb.id)}>
                <Plug className="w-3.5 h-3.5" /> Connect with Google
              </Button>
            )}
          </div>
        ))}
      </div>
      {!status.configured && <p className="text-[11px] text-slate-400 mt-2">Buttons unlock once the Google credentials are in.</p>}
    </div>
  );
};
