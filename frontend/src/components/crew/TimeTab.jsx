import React, { useCallback, useEffect, useState } from "react";
import dayjs from "dayjs";
import { toast } from "sonner";
import { Download, Pencil, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { listTimeclockApi, patchTimeEntryApi, timesheetCsvUrl, apiErrorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "—");
const toLocalInput = (iso) => (iso ? dayjs(iso).format("YYYY-MM-DDTHH:mm") : "");

const EditEntryDialog = ({ entry, onOpenChange, onSaved }) => {
  const [inAt, setInAt] = useState("");
  const [outAt, setOutAt] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!entry) return;
    setInAt(toLocalInput(entry.clock_in?.at));
    setOutAt(toLocalInput(entry.clock_out?.at));
  }, [entry]);

  const save = async () => {
    setBusy(true);
    try {
      const patch = {};
      if (inAt && toLocalInput(entry.clock_in?.at) !== inAt) patch.clock_in_at = new Date(inAt).toISOString();
      if (outAt && toLocalInput(entry.clock_out?.at) !== outAt) patch.clock_out_at = new Date(outAt).toISOString();
      if (Object.keys(patch).length) await patchTimeEntryApi(entry.id, patch);
      toast.success("Time entry fixed. It's marked as edited on the CSV.");
      onOpenChange(null);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={!!entry} onOpenChange={() => onOpenChange(null)}>
      <DialogContent data-testid="edit-time-entry-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Fix {entry?.user_name}'s punch</DialogTitle>
          <DialogDescription>Edited entries get flagged on the payroll report so everything stays honest.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Clock in</Label>
            <Input data-testid="edit-clock-in-input" type="datetime-local" value={inAt} onChange={(e) => setInAt(e.target.value)} />
          </div>
          <div>
            <Label>Clock out</Label>
            <Input data-testid="edit-clock-out-input" type="datetime-local" value={outAt} onChange={(e) => setOutAt(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(null)}>Cancel</Button>
          <Button data-testid="edit-time-entry-save" disabled={busy} onClick={save} className="bg-[#E8743B] hover:bg-[#d4632e]">Save fix</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const TimeTab = () => {
  const [start, setStart] = useState(() => dayjs().subtract(13, "day").format("YYYY-MM-DD"));
  const [end, setEnd] = useState(() => dayjs().format("YYYY-MM-DD"));
  const [entries, setEntries] = useState(null);
  const [editEntry, setEditEntry] = useState(null);

  const load = useCallback(() => {
    listTimeclockApi({ start, end }).then(setEntries).catch((e) => toast.error(apiErrorMessage(e)));
  }, [start, end]);
  useEffect(() => {
    load();
  }, [load]);

  const toggleApproved = async (e) => {
    try {
      await patchTimeEntryApi(e.id, { approved: !e.approved });
      setEntries((list) => list.map((x) => (x.id === e.id ? { ...x, approved: !e.approved } : x)));
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  };

  const list = entries || [];
  const totalHours = list.reduce((s, e) => s + (e.hours || 0), 0);
  const totalPay = list.reduce((s, e) => s + (e.pay || 0), 0);

  return (
    <div className="mt-4 space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <Label className="text-xs">From</Label>
          <Input data-testid="time-start-input" type="date" className="h-9" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div>
          <Label className="text-xs">To</Label>
          <Input data-testid="time-end-input" type="date" className="h-9" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <Button data-testid="download-csv-btn" asChild variant="outline" className="gap-1.5">
          <a href={timesheetCsvUrl(start, end)} download>
            <Download className="w-4 h-4" /> Payroll CSV
          </a>
        </Button>
        <div className="ml-auto text-sm text-slate-600">
          <span className="font-bold text-[#1B2A4A]">{totalHours.toFixed(2)} hrs</span> · <span className="font-bold text-[#1B2A4A]">${totalPay.toFixed(2)}</span> in this range
        </div>
      </div>

      <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Crew</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>In</TableHead>
              <TableHead>Out</TableHead>
              <TableHead>Hours</TableHead>
              <TableHead>Position</TableHead>
              <TableHead>Pay</TableHead>
              <TableHead>Job</TableHead>
              <TableHead>Flags</TableHead>
              <TableHead>OK?</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.map((e) => (
              <TableRow key={e.id} data-testid="timeclock-row">
                <TableCell className="font-medium">{e.user_name}{e.edited && <span className="text-[10px] text-amber-600 ml-1">(edited)</span>}</TableCell>
                <TableCell>{fmtDate(e.clock_in.at.slice(0, 10))}</TableCell>
                <TableCell>{fmtTime(e.clock_in.at)}</TableCell>
                <TableCell>{e.clock_out ? fmtTime(e.clock_out.at) : <span className="text-emerald-600 font-semibold">on clock</span>}</TableCell>
                <TableCell className="font-bold">{e.hours != null ? e.hours : "—"}</TableCell>
                <TableCell>{e.position || "—"}</TableCell>
                <TableCell>{e.pay != null ? `$${e.pay.toFixed(2)}` : "—"}</TableCell>
                <TableCell className="max-w-[140px] truncate">{e.job_name || "—"}</TableCell>
                <TableCell>
                  {(e.flags || []).length > 0 && (
                    <Badge data-testid="entry-flags-badge" variant="outline" className="text-[10px] bg-amber-50 text-amber-700 border-amber-200 gap-1" title={e.flags.join("; ")}>
                      <AlertTriangle className="w-3 h-3" /> {e.flags.length}
                    </Badge>
                  )}
                </TableCell>
                <TableCell>
                  <Switch data-testid="approve-entry-switch" checked={e.approved} onCheckedChange={() => toggleApproved(e)} />
                </TableCell>
                <TableCell>
                  <Button data-testid="edit-entry-btn" variant="ghost" size="sm" className="h-7 px-2" onClick={() => setEditEntry(e)}>
                    <Pencil className="w-3.5 h-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {entries !== null && list.length === 0 && (
              <TableRow><TableCell colSpan={11} className="text-center text-slate-400 py-8">No punches in this date range.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs text-slate-400">Flip "OK?" on once you've checked an entry. Flags call out punches with no GPS, far from the job site, or extra-long shifts.</p>

      <EditEntryDialog entry={editEntry} onOpenChange={setEditEntry} onSaved={load} />
    </div>
  );
};
