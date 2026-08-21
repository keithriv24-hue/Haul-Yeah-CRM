import React, { useCallback, useEffect, useState } from "react";
import { Bell, CheckCheck } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { listNotificationsApi, readAllNotificationsApi } from "@/lib/api";
import { ageLabel, minutesSince } from "@/lib/format";

export const NotificationsBell = () => {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);

  const load = useCallback(async () => {
    try {
      const d = await listNotificationsApi();
      setItems(d.notifications);
      setUnread(d.unread);
    } catch {
      /* not signed in as a user account */
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  const markAll = async () => {
    try {
      await readAllNotificationsApi();
      setUnread(0);
      setItems((l) => l.map((n) => ({ ...n, read: true })));
    } catch {}
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button data-testid="notifications-bell-btn" className="relative p-2 rounded-full hover:bg-surface-sunk transition-colors" aria-label="Notifications">
          <Bell className="w-5 h-5 text-ink-2" />
          {unread > 0 && (
            <span data-testid="notifications-unread-badge" className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-accent text-white text-[10px] font-bold flex items-center justify-center">
              {unread}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
          <span className="text-sm font-bold text-primary">Notifications</span>
          {unread > 0 && (
            <Button data-testid="notifications-mark-read-btn" variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={markAll}>
              <CheckCheck className="w-3.5 h-3.5" /> Mark all read
            </Button>
          )}
        </div>
        <div className="max-h-80 overflow-y-auto">
          {items.length === 0 && <p className="text-sm text-faint text-center py-8">Nothing yet.</p>}
          {items.map((n) => (
            <div key={n.id} data-testid="notification-item" className={`px-4 py-3 border-b border-border ${n.read ? "" : "bg-accent/10"}`}>
              <div className="flex items-start gap-2">
                {!n.read && <span className="w-2 h-2 rounded-full bg-accent mt-1.5 shrink-0" />}
                <div>
                  <p className="text-sm font-semibold text-primary">{n.title}</p>
                  <p className="text-xs text-ink-2 mt-0.5">{n.body}</p>
                  <p className="text-[10px] text-faint mt-1">{ageLabel(minutesSince(n.created_at))} ago</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
};
