import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { UserPlus, KeyRound, UserX, UserCheck, Truck, Plus, DollarSign, Pencil, Trash2, IdCard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { EmployeeFileDialog } from "@/components/crew/EmployeeFileDialog";
import {
  listUsersApi, createUserApi, patchUserApi, listTrucksApi, createTruckApi, patchTruckApi, deleteTruckApi,
  getCrewRatesApi, saveCrewRatesApi, apiErrorMessage,
} from "@/lib/api";

const ROLE_BADGE = {
  owner: "bg-[#1B2A4A] text-white border-transparent",
  sales: "bg-sky-100 text-sky-800 border-sky-300",
  crew: "bg-orange-100 text-orange-800 border-orange-300",
  marketing: "bg-teal-100 text-teal-800 border-teal-300",
};

const RoleChecks = ({ roles, onToggle, idPrefix }) => (
  <div>
    <Label>Roles (pick all that apply)</Label>
    <div className="space-y-1.5 mt-1">
      {["crew", "sales", "marketing", "owner"].map((r) => (
        <label key={r} className="flex items-center gap-2 text-sm cursor-pointer">
          <Checkbox data-testid={`${idPrefix}-role-${r}`} checked={roles.includes(r)} onCheckedChange={() => onToggle(r)} />
          <span className="capitalize text-[#1B2A4A]">{r}</span>
        </label>
      ))}
    </div>
    <p className="text-[11px] text-slate-400 mt-1.5">Someone with Crew + Sales can flip between both views from the sidebar.</p>
  </div>
);

const AddUserDialog = ({ open, onOpenChange, onSaved }) => {
  const [form, setForm] = useState({ name: "", email: "", roles: ["crew"] });
  const [busy, setBusy] = useState(false);
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleRole = (r) =>
    setForm((f) => ({ ...f, roles: f.roles.includes(r) ? f.roles.filter((x) => x !== r) : [...f.roles, r] }));

  const save = async () => {
    setBusy(true);
    try {
      await createUserApi({ name: form.name, email: form.email, roles: form.roles, role: form.roles[0] });
      toast.success(`${form.name} added. Their starting password is haulyeah123 — they'll change it on first login.`);
      setForm({ name: "", email: "", roles: ["crew"] });
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="add-user-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Add a team member</DialogTitle>
          <DialogDescription>Every new person starts with the same password — they'll be asked to change it the first time they sign in.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div><Label>Name</Label><Input data-testid="add-user-name" value={form.name} onChange={(e) => set("name")(e.target.value)} placeholder="First Last" /></div>
          <div><Label>Email (their login)</Label><Input data-testid="add-user-email" type="email" value={form.email} onChange={(e) => set("email")(e.target.value)} placeholder="name@haulyeahmoves.com" /></div>
          <RoleChecks roles={form.roles} onToggle={toggleRole} idPrefix="add-user" />
          <div data-testid="add-user-default-password-note" className="flex items-start gap-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2.5 text-sm text-amber-800">
            <KeyRound className="w-4 h-4 mt-0.5 shrink-0" />
            <span>Their starting password is <strong className="font-mono">haulyeah123</strong>. Tell them to use it once — the app makes them pick their own right away.</span>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="add-user-save" disabled={busy || !form.name || !form.email || form.roles.length === 0} onClick={save} className="bg-[#E8743B] hover:bg-[#d4632e]">
            Add them
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const EditRolesDialog = ({ user, onOpenChange, onSaved }) => {
  const [roles, setRoles] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (user) setRoles(user.roles?.length ? user.roles : [user.role]);
  }, [user]);
  const toggleRole = (r) => setRoles((s) => (s.includes(r) ? s.filter((x) => x !== r) : [...s, r]));
  const save = async () => {
    setBusy(true);
    try {
      await patchUserApi(user.id, { roles });
      toast.success(`${user.name}'s roles updated. It kicks in the next time they log in or switch views.`);
      onOpenChange(null);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <Dialog open={!!user} onOpenChange={() => onOpenChange(null)}>
      <DialogContent data-testid="edit-roles-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">{user?.name}'s roles</DialogTitle>
          <DialogDescription>Pick every hat they wear. Crew + Sales gives them a view switcher in their sidebar.</DialogDescription>
        </DialogHeader>
        <RoleChecks roles={roles} onToggle={toggleRole} idPrefix="edit-user" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(null)}>Cancel</Button>
          <Button data-testid="edit-roles-save" disabled={busy || roles.length === 0} onClick={save} className="bg-[#E8743B] hover:bg-[#d4632e]">Save roles</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const ResetPasswordDialog = ({ user, onOpenChange, onSaved }) => {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await patchUserApi(user.id, { password: pw });
      toast.success(`Password reset for ${user.name}. They'll pick a new one on next login.`);
      onOpenChange(null);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <Dialog open={!!user} onOpenChange={() => onOpenChange(null)}>
      <DialogContent data-testid="reset-password-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Reset {user?.name}'s password</DialogTitle>
          <DialogDescription>Give them a temporary password. They'll be forced to change it when they sign in.</DialogDescription>
        </DialogHeader>
        <Input data-testid="reset-password-input" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="Temporary password (8+ characters)" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(null)}>Cancel</Button>
          <Button data-testid="reset-password-save" disabled={busy || pw.length < 8} onClick={save} className="bg-[#E8743B] hover:bg-[#d4632e]">Reset it</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const EditTruckDialog = ({ truck, onOpenChange, onSaved }) => {
  const [name, setName] = useState("");
  const [plate, setPlate] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (truck) {
      setName(truck.name || "");
      setPlate(truck.plate || "");
    }
  }, [truck]);
  const save = async () => {
    setBusy(true);
    try {
      await patchTruckApi(truck.id, { name, plate });
      toast.success("Truck updated.");
      onOpenChange(null);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };
  return (
    <Dialog open={!!truck} onOpenChange={() => onOpenChange(null)}>
      <DialogContent data-testid="edit-truck-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Edit truck</DialogTitle>
          <DialogDescription>The name is what shows on schedules and your Airtable time log.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div><Label>Name</Label><Input data-testid="edit-truck-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Big Orange" /></div>
          <div><Label>License plate</Label><Input data-testid="edit-truck-plate" value={plate} onChange={(e) => setPlate(e.target.value)} placeholder="XJT-4821" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(null)}>Cancel</Button>
          <Button data-testid="edit-truck-save" disabled={busy || !name.trim()} onClick={save} className="bg-[#E8743B] hover:bg-[#d4632e]">Save truck</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const TeamTab = () => {
  const [users, setUsers] = useState([]);
  const [trucks, setTrucks] = useState([]);
  const [rates, setRates] = useState({ driver: 28, helper: 24 });
  const [addOpen, setAddOpen] = useState(false);
  const [resetUser, setResetUser] = useState(null);
  const [rolesUser, setRolesUser] = useState(null);
  const [fileUser, setFileUser] = useState(null);
  const [editTruck, setEditTruck] = useState(null);
  const [newTruck, setNewTruck] = useState("");
  const [newPlate, setNewPlate] = useState("");

  const load = useCallback(async () => {
    try {
      const [u, t, r] = await Promise.all([listUsersApi(), listTrucksApi(), getCrewRatesApi()]);
      setUsers(u);
      setTrucks(t);
      setRates(r);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const toggleActive = async (u) => {
    try {
      await patchUserApi(u.id, { active: !u.active });
      toast.success(u.active ? `${u.name} deactivated — they can't sign in anymore.` : `${u.name} is back on.`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const addTruck = async () => {
    if (!newTruck.trim()) return;
    try {
      await createTruckApi({ name: newTruck.trim(), plate: newPlate.trim() });
      setNewTruck("");
      setNewPlate("");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const removeTruck = async (t) => {
    try {
      await deleteTruckApi(t.id);
      toast.success(`${t.name} removed. Past jobs keep its name in their history.`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  const saveRates = async () => {
    try {
      await saveCrewRatesApi({ driver: Number(rates.driver), helper: Number(rates.helper) });
      toast.success("Pay rates saved — payroll uses these from now on.");
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
  };

  return (
    <div className="grid lg:grid-cols-3 gap-4 mt-4">
      <div className="lg:col-span-2 bg-white rounded-lg border border-slate-200">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <h2 className="font-bold text-[#1B2A4A]">Team members</h2>
          <Button data-testid="add-user-btn" size="sm" className="gap-1.5 bg-[#E8743B] hover:bg-[#d4632e]" onClick={() => setAddOpen(true)}>
            <UserPlus className="w-4 h-4" /> Add person
          </Button>
        </div>
        <div className="divide-y divide-slate-100">
          {users.map((u) => (
            <div key={u.id} data-testid="user-row" className={`flex flex-wrap items-center gap-2 px-4 py-3 ${u.active ? "" : "opacity-50"}`}>
              <div className="flex-1 min-w-[160px]">
                <p className="font-semibold text-[#1B2A4A] text-sm">{u.name}</p>
                <p className="text-xs text-slate-500">{u.email}</p>
              </div>
              {(u.roles?.length ? u.roles : [u.role]).map((r) => (
                <Badge key={r} variant="outline" className={`text-[10px] ${ROLE_BADGE[r] || ""}`}>{r}</Badge>
              ))}
              {!u.active && <Badge variant="outline" className="text-[10px] bg-red-50 text-red-600 border-red-200">off</Badge>}
              {u.must_change_password && u.active && <Badge variant="outline" className="text-[10px] bg-amber-50 text-amber-700 border-amber-200">temp password</Badge>}
              <Button data-testid="edit-roles-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => setRolesUser(u)}>
                <Pencil className="w-3.5 h-3.5" /> Roles
              </Button>
              <Button data-testid="employee-file-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => setFileUser(u)}>
                <IdCard className="w-3.5 h-3.5" /> File
              </Button>
              <Button data-testid="reset-password-btn" variant="outline" size="sm" className="gap-1 text-xs" onClick={() => setResetUser(u)}>
                <KeyRound className="w-3.5 h-3.5" /> Reset password
              </Button>
              <Button data-testid="toggle-active-btn" variant="outline" size="sm" className={`gap-1 text-xs ${u.active ? "text-red-600 border-red-200 hover:bg-red-50" : "text-emerald-700 border-emerald-200 hover:bg-emerald-50"}`} onClick={() => toggleActive(u)}>
                {u.active ? <UserX className="w-3.5 h-3.5" /> : <UserCheck className="w-3.5 h-3.5" />}
                {u.active ? "Deactivate" : "Reactivate"}
              </Button>
            </div>
          ))}
          {users.length === 0 && <p className="text-sm text-slate-400 px-4 py-6 text-center">Loading team…</p>}
        </div>
      </div>

      <div className="space-y-4">
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="font-bold text-[#1B2A4A] flex items-center gap-2 mb-3"><DollarSign className="w-4 h-4 text-[#E8743B]" /> Pay rates</h2>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label className="w-16 text-xs">Driver</Label>
              <Input data-testid="rate-driver-input" type="number" className="h-8" value={rates.driver} onChange={(e) => setRates((r) => ({ ...r, driver: e.target.value }))} />
              <span className="text-xs text-slate-400">/hr</span>
            </div>
            <div className="flex items-center gap-2">
              <Label className="w-16 text-xs">Helper</Label>
              <Input data-testid="rate-helper-input" type="number" className="h-8" value={rates.helper} onChange={(e) => setRates((r) => ({ ...r, helper: e.target.value }))} />
              <span className="text-xs text-slate-400">/hr</span>
            </div>
            <Button data-testid="save-rates-btn" size="sm" className="w-full mt-1 bg-[#1B2A4A] hover:bg-[#152238]" onClick={saveRates}>Save rates</Button>
          </div>
        </div>

        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="font-bold text-[#1B2A4A] flex items-center gap-2 mb-3"><Truck className="w-4 h-4 text-[#E8743B]" /> Trucks</h2>
          <div className="space-y-2">
            {trucks.map((t) => (
              <div key={t.id} data-testid="truck-row" className="flex items-center gap-1 text-sm">
                <div className="flex-1 min-w-0">
                  <span className={t.active ? "text-[#1B2A4A] font-medium" : "text-slate-400 line-through"}>{t.name}</span>
                  <span data-testid="truck-plate-label" className="text-xs text-slate-400 ml-2">{t.plate || "no plate"}</span>
                </div>
                <Button data-testid="edit-truck-btn" variant="ghost" size="sm" className="h-7 px-2" onClick={() => setEditTruck(t)}>
                  <Pencil className="w-3.5 h-3.5" />
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button data-testid="remove-truck-btn" variant="ghost" size="sm" className="h-7 px-2 text-red-600 hover:text-red-700">
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle className="font-display">Remove {t.name}?</AlertDialogTitle>
                      <AlertDialogDescription>It can't be put on new jobs anymore. Past jobs keep its name in their history.</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Keep it</AlertDialogCancel>
                      <AlertDialogAction data-testid="confirm-remove-truck" onClick={() => removeTruck(t)} className="bg-red-600 hover:bg-red-700">Yes, remove</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            ))}
            <div className="flex gap-2 pt-1">
              <Input data-testid="new-truck-input" className="h-8" placeholder="Truck name" value={newTruck} onChange={(e) => setNewTruck(e.target.value)} />
              <Input data-testid="new-truck-plate-input" className="h-8 w-24" placeholder="Plate" value={newPlate} onChange={(e) => setNewPlate(e.target.value)} />
              <Button data-testid="add-truck-btn" size="sm" variant="outline" onClick={addTruck}><Plus className="w-4 h-4" /></Button>
            </div>
          </div>
        </div>
      </div>

      <AddUserDialog open={addOpen} onOpenChange={setAddOpen} onSaved={load} />
      <EditRolesDialog user={rolesUser} onOpenChange={setRolesUser} onSaved={load} />
      <ResetPasswordDialog user={resetUser} onOpenChange={setResetUser} onSaved={load} />
      <EmployeeFileDialog user={fileUser} onOpenChange={setFileUser} />
      <EditTruckDialog truck={editTruck} onOpenChange={setEditTruck} onSaved={load} />
    </div>
  );
};
