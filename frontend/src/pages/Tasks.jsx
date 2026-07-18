import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, GripVertical } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { InstructionBanner, PageTitle, Pill, EmptyState, LoadingRows } from "@/components/Bits";
import { TF, f, TASK_STATUSES, TASK_PRIORITIES, TASK_CATEGORIES } from "@/lib/fields";
import { fmtDate, isOverdue } from "@/lib/format";

const TaskCard = ({ task }) => {
  const { updateRecord } = useApp();
  const overdue = isOverdue(f(task, TF.dueDate)) && f(task, TF.status) !== "Done";
  return (
    <div
      data-testid="task-card"
      draggable
      onDragStart={(e) => e.dataTransfer.setData("text/plain", task.id)}
      className="kanban-card bg-white border border-slate-200 rounded-lg p-3 space-y-2"
    >
      <div className="flex items-start gap-1.5">
        <GripVertical className="w-4 h-4 text-slate-300 mt-0.5 shrink-0" />
        <span className="text-sm font-medium leading-snug">{f(task, TF.task) || "Task"}</span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {f(task, TF.priority) && <Pill value={f(task, TF.priority)} />}
        {f(task, TF.category) && (
          <span className="inline-flex items-center border border-[#1B2A4A]/20 bg-[#1B2A4A]/5 text-[#1B2A4A] rounded-full px-2.5 py-0.5 text-xs font-semibold">
            {f(task, TF.category)}
          </span>
        )}
        {f(task, TF.dueDate) && (
          <span className={`text-xs font-semibold ${overdue ? "text-red-600" : "text-slate-500"}`}>
            {overdue ? "Late: " : "Due "}{fmtDate(f(task, TF.dueDate))}
          </span>
        )}
      </div>
      <div className="md:hidden">
        <Select value={f(task, TF.status) || "Backlog"} onValueChange={(v) => updateRecord("tasks", task.id, { [TF.status]: v }).catch(() => {})}>
          <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>{TASK_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>
      </div>
    </div>
  );
};

const blank = { task: "", priority: "Medium", category: "Ops", dueDate: "", notes: "" };

export default function Tasks() {
  const { loadTable, records, tableState, updateRecord, createRecord } = useApp();
  const [dragOver, setDragOver] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadTable("tasks");
  }, [loadTable]);

  const tasks = records("tasks");
  const { loading, error } = tableState("tasks");

  const onDrop = (e, status) => {
    e.preventDefault();
    setDragOver(null);
    const id = e.dataTransfer.getData("text/plain");
    if (id) updateRecord("tasks", id, { [TF.status]: status }).catch(() => {});
  };

  const save = async () => {
    if (!form.task.trim()) {
      toast.error("Write what the task is first.");
      return;
    }
    setSaving(true);
    try {
      await createRecord("tasks", {
        [TF.task]: form.task.trim(),
        [TF.status]: "To Do",
        [TF.priority]: form.priority,
        [TF.category]: form.category,
        [TF.dueDate]: form.dueDate,
        [TF.notes]: form.notes,
      });
      toast.success("Task added to To Do.");
      setForm(blank);
      setModalOpen(false);
    } catch {}
    setSaving(false);
  };

  return (
    <div data-testid="tasks-page">
      <PageTitle
        title="To-Do Board"
        subtitle="Drag cards as work moves along."
        action={
          <Button data-testid="new-task-btn" onClick={() => setModalOpen(true)} className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]">
            <Plus className="w-4 h-4" /> Add task
          </Button>
        }
      />
      <InstructionBanner>Drag cards between columns as work moves along. On a phone, use the dropdown on each card.</InstructionBanner>

      {loading && !tasks.length ? (
        <LoadingRows />
      ) : error && !tasks.length ? (
        <EmptyState>{error}</EmptyState>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {TASK_STATUSES.map((status) => {
            const col = tasks.filter((t) => (f(t, TF.status) || "Backlog") === status);
            return (
              <div
                key={status}
                data-testid={`kanban-col-${status.toLowerCase().replace(/\s+/g, "-")}`}
                className={`kanban-col rounded-lg border border-slate-200 bg-slate-100/60 p-3 ${dragOver === status ? "drag-over" : ""}`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(status); }}
                onDragLeave={() => setDragOver(null)}
                onDrop={(e) => onDrop(e, status)}
              >
                <div className="flex items-center justify-between mb-3">
                  <h2 className="font-display font-bold text-sm text-[#1B2A4A]">{status}</h2>
                  <span className="text-xs font-bold text-slate-400">{col.length}</span>
                </div>
                <div className="space-y-2">
                  {col.map((t) => <TaskCard key={t.id} task={t} />)}
                  {col.length === 0 && <div className="text-xs text-slate-400 text-center py-4">Drop tasks here</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent data-testid="new-task-modal" className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-display">Add task</DialogTitle>
            <DialogDescription>New tasks start in the To Do column.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>What needs doing? *</Label>
              <Input data-testid="task-name-input" value={form.task} onChange={(e) => setForm((s) => ({ ...s, task: e.target.value }))} />
            </div>
            <div>
              <Label>Priority</Label>
              <Select value={form.priority} onValueChange={(v) => setForm((s) => ({ ...s, priority: v }))}>
                <SelectTrigger data-testid="task-priority-select"><SelectValue /></SelectTrigger>
                <SelectContent>{TASK_PRIORITIES.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Category</Label>
              <Select value={form.category} onValueChange={(v) => setForm((s) => ({ ...s, category: v }))}>
                <SelectTrigger data-testid="task-category-select"><SelectValue /></SelectTrigger>
                <SelectContent>{TASK_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Due date</Label>
              <Input data-testid="task-due-input" type="date" value={form.dueDate} onChange={(e) => setForm((s) => ({ ...s, dueDate: e.target.value }))} />
            </div>
            <div className="col-span-2">
              <Label>Notes</Label>
              <Textarea value={form.notes} onChange={(e) => setForm((s) => ({ ...s, notes: e.target.value }))} rows={2} />
            </div>
          </div>
          <Button data-testid="task-save-btn" onClick={save} disabled={saving} className="w-full gap-2 bg-[#E8743B] hover:bg-[#d4632e]">
            <Plus className="w-4 h-4" /> {saving ? "Saving…" : "Save task"}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
