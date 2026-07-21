import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Search, Archive, MailOpen, Reply, Send, ArrowLeft, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { gmailMessagesApi, gmailMessageApi, gmailReplyApi, gmailModifyApi, apiErrorMessage } from "@/lib/api";

const fromName = (from) => (from || "").replace(/<.*>/, "").replace(/"/g, "").trim() || from || "Unknown";
const fmtMailDate = (ms) => {
  if (!ms) return "";
  const d = new Date(Number(ms));
  const today = new Date().toDateString() === d.toDateString();
  return today
    ? d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

export const EmailInbox = ({ mailboxes }) => {
  const [boxId, setBoxId] = useState(mailboxes[0]?.id);
  const [messages, setMessages] = useState(null);
  const [nextToken, setNextToken] = useState(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback((append = false, token = "") => {
    if (!boxId) return;
    gmailMessagesApi(boxId, { q: query, page_token: token })
      .then((d) => {
        setMessages((m) => (append && m ? [...m, ...d.messages] : d.messages));
        setNextToken(d.next_page_token || null);
      })
      .catch((e) => {
        setMessages([]);
        toast.error(apiErrorMessage(e));
      });
  }, [boxId, query]);

  useEffect(() => {
    setMessages(null);
    setSelected(null);
    load();
  }, [boxId]); // eslint-disable-line react-hooks/exhaustive-deps

  const open = async (m) => {
    setReplyOpen(false);
    setReplyText("");
    try {
      const full = await gmailMessageApi(boxId, m.id);
      setSelected(full);
      setMessages((list) => (list || []).map((x) => (x.id === m.id ? { ...x, unread: false } : x)));
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const modify = async (action) => {
    if (!selected) return;
    setBusy(true);
    try {
      await gmailModifyApi(boxId, selected.id, action);
      if (action === "archive") {
        toast.success("Archived.");
        setMessages((list) => (list || []).filter((x) => x.id !== selected.id));
        setSelected(null);
      } else {
        toast.success("Marked unread.");
        setMessages((list) => (list || []).map((x) => (x.id === selected.id ? { ...x, unread: true } : x)));
        setSelected(null);
      }
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  const sendReply = async () => {
    setBusy(true);
    try {
      await gmailReplyApi(boxId, selected.id, replyText);
      toast.success("Reply sent.");
      setReplyOpen(false);
      setReplyText("");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <div data-testid="email-inbox" className="mt-3">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {mailboxes.length > 1 && mailboxes.map((mb) => (
          <button
            key={mb.id}
            data-testid={`mailbox-switch-${mb.id}`}
            onClick={() => setBoxId(mb.id)}
            className={`text-xs font-semibold rounded-full border px-3 py-1.5 transition-colors ${
              boxId === mb.id ? "bg-[#1B2A4A] text-white border-[#1B2A4A]" : "bg-white text-slate-600 border-slate-300 hover:border-slate-400"
            }`}
          >
            {mb.email}
          </button>
        ))}
        {mailboxes.length === 1 && <span className="text-xs font-semibold text-slate-500">{mailboxes[0].email}</span>}
        <div className="flex items-center gap-1.5 ml-auto">
          <Input
            data-testid="email-search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="Search mail…"
            className="h-8 w-44"
          />
          <Button data-testid="email-search-btn" variant="outline" size="sm" className="h-8 px-2" onClick={() => load()}>
            <Search className="w-3.5 h-3.5" />
          </Button>
          <Button data-testid="email-refresh-btn" variant="outline" size="sm" className="h-8 px-2" onClick={() => load()}>
            <RefreshCw className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] gap-3 items-start">
        <div className={`bg-white border border-slate-200 rounded-lg overflow-hidden ${selected ? "hidden lg:block" : ""}`} data-testid="email-list">
          {messages === null ? (
            <p className="text-sm text-slate-400 text-center py-10">Loading inbox…</p>
          ) : messages.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-10">{query ? "Nothing matches that search." : "Inbox zero. Nice."}</p>
          ) : (
            <div className="divide-y divide-slate-100 max-h-[70vh] overflow-y-auto">
              {messages.map((m) => (
                <button
                  key={m.id}
                  data-testid="email-list-row"
                  onClick={() => open(m)}
                  className={`w-full text-left px-3 py-2.5 hover:bg-slate-50 transition-colors ${selected?.id === m.id ? "bg-orange-50/60" : ""}`}
                >
                  <div className="flex items-center gap-2">
                    {m.unread && <span className="w-2 h-2 rounded-full bg-[#E8743B] shrink-0" />}
                    <span className={`text-sm truncate flex-1 ${m.unread ? "font-bold text-[#1B2A4A]" : "text-slate-600"}`}>{fromName(m.from)}</span>
                    <span className="text-[11px] text-slate-400 shrink-0">{fmtMailDate(m.date)}</span>
                  </div>
                  <p className={`text-xs truncate ${m.unread ? "font-semibold text-[#1B2A4A]" : "text-slate-500"}`}>{m.subject}</p>
                  <p className="text-[11px] text-slate-400 truncate">{m.snippet}</p>
                </button>
              ))}
              {nextToken && (
                <button data-testid="email-load-more" onClick={() => load(true, nextToken)} className="w-full text-center text-xs font-semibold text-[#E8743B] py-2.5 hover:bg-orange-50">
                  Load more
                </button>
              )}
            </div>
          )}
        </div>

        <div className={`bg-white border border-slate-200 rounded-lg ${selected ? "" : "hidden lg:block"}`} data-testid="email-reading-pane">
          {!selected ? (
            <p className="text-sm text-slate-400 text-center py-16">Pick an email to read it here.</p>
          ) : (
            <div className="p-4">
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <Button data-testid="email-back-btn" variant="outline" size="sm" className="lg:hidden h-8 px-2" onClick={() => setSelected(null)}>
                  <ArrowLeft className="w-3.5 h-3.5" />
                </Button>
                <Button data-testid="email-reply-btn" variant="outline" size="sm" className="h-8 gap-1 text-xs" disabled={busy} onClick={() => setReplyOpen((v) => !v)}>
                  <Reply className="w-3.5 h-3.5" /> Reply
                </Button>
                <Button data-testid="email-archive-btn" variant="outline" size="sm" className="h-8 gap-1 text-xs" disabled={busy} onClick={() => modify("archive")}>
                  <Archive className="w-3.5 h-3.5" /> Archive
                </Button>
                <Button data-testid="email-unread-btn" variant="outline" size="sm" className="h-8 gap-1 text-xs" disabled={busy} onClick={() => modify("unread")}>
                  <MailOpen className="w-3.5 h-3.5" /> Mark unread
                </Button>
              </div>
              <h3 className="font-display font-bold text-[#1B2A4A]" data-testid="email-subject">{selected.subject}</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                From <strong>{selected.from}</strong>
                {selected.to && <> · to {selected.to}</>}
                {selected.date && <> · {new Date(Number(selected.date)).toLocaleString()}</>}
              </p>
              {replyOpen && (
                <div className="mt-3 border border-orange-200 bg-orange-50/50 rounded-lg p-3" data-testid="email-reply-box">
                  <Textarea data-testid="email-reply-textarea" rows={4} value={replyText} onChange={(e) => setReplyText(e.target.value)} placeholder={`Reply to ${fromName(selected.from)}…`} />
                  <Button data-testid="email-reply-send-btn" size="sm" className="mt-2 gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]" disabled={busy || !replyText.trim()} onClick={sendReply}>
                    <Send className="w-3.5 h-3.5" /> Send reply
                  </Button>
                </div>
              )}
              <div className="mt-3 border-t border-slate-100 pt-3">
                {selected.body_html ? (
                  <iframe
                    title="email-body"
                    sandbox=""
                    srcDoc={selected.body_html}
                    className="w-full min-h-[50vh] border-0"
                    data-testid="email-body-html"
                  />
                ) : (
                  <pre className="text-sm text-slate-700 whitespace-pre-wrap font-sans" data-testid="email-body-text">{selected.body_text || selected.snippet}</pre>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
