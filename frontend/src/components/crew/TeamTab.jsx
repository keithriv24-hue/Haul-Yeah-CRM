import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { UserPlus, KeyRound, UserX, UserCheck, Truck, Plus, DollarSign, Pencil, Trash2, IdCard, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { EmployeeFileDialog } from "@/components/crew/EmployeeFileDialog";
import { SearchBar, searchMatch } from "@/components/Bits";
import {
  listUsersApi, createUserApi, patchUserApi, deleteUserApi, listTrucksApi, createTruckApi, patchTruckApi, deleteTruckApi,
  getCrewRatesApi, saveCrewRatesApi, apiErrorMessage,
} from "@/lib/api";

const ROW_LINK =
  "inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12.5px] font-semibold text-ink-2 transition-colors hover:bg-surface-sunk hover:text-primary";

const ROLE_BADGE = {
  owner: "bg-primary text-white border-transparent",
  sales: "bg-info/12 text-info border-info/30",
  crew: "bg-accent/12 text-accent-ink border-accent/30",
  marketing: "bg-success/12 text-success border-success/30",
};

const RoleChecks = ({ roles, onToggle, idPrefix }) => (
  <div>
    <Label>Roles (pick all that apply)</Label>
    <div className="space-y-1.5 mt-1">
      {["crew", "sales", "marketing", "owner"].map((r) => (
        <label key={r} className="flex items-center gap-2 text-sm cursor-pointer">
          <Checkbox data-testid={`${idPrefix}-role-${r}`} checked={roles.includes(r)} onCheckedChange={() => onToggle(r)} />
          <span className="capitalize text-primary">{r}</span>
        </label>
      ))}
    </div>
    <p className="text-[11px] text-faint mt-1.5">Pick their main role first — it decides which view they land in. Someone with Crew + Sales can flip between both views from the sidebar.</p>
  </div>
);

const AddUserDialog = ({ open, onOpenChange, onSaved }) => {
  const [form, setForm] = useState({ name: "", email: "", roles: [] });
  const [busy, setBusy] = useState(false);
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleRole = (r) =>
    setForm((f) => ({ ...f, roles: f.roles.includes(r) ? f.roles.filter((x) => x !== r) : [...f.roles, r] }));

  const save = async () => {
    setBusy(true);
    try {
      await createUserApi({ name: form.name, email: form.email, roles: form.roles, role: form.roles[0] });
      toast.success(`${form.name} added. Their starting password is haulyeah123 — they'll change it on first login.`);
      setForm({ name: "", email: "", roles: [] });
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
          <div>
            <Label>Login — username or email</Label>
            <Input data-testid="add-user-email" value={form.email} onChange={(e) => set("email")(e.target.value)} placeholder="keith2 or name@haulyeahmoves.com" />
            <p className="text-[11px] text-faint mt-1">Either works — a plain username (3+ characters, no spaces) or a full email address.</p>
          </div>
          <RoleChecks roles={form.roles} onToggle={toggleRole} idPrefix="add-user" />
          <div data-testid="add-user-default-password-note" className="flex items-start gap-2 rounded-md bg-warning/10 border border-warning/25 px-3 py-2.5 text-sm text-warning">
            <KeyRound className="w-4 h-4 mt-0.5 shrink-0" />
            <span>Their starting password is <strong className="font-mono">haulyeah123</strong>. Tell them to use it once — the app makes them pick their own right away.</span>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="add-user-save" disabled={busy || !form.name || !form.email || form.roles.length === 0} onClick={save} className="bg-accent hover:bg-accent-press">
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
          <Button data-testid="edit-roles-save" disabled={busy || roles.length === 0} onClick={save} className="bg-accent hover:bg-accent-press">Save roles</Button>
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
          <Button data-testid="reset-password-save" disabled={busy || pw.length < 8} onClick={save} className="bg-accent hover:bg-accent-press">Reset it</Button>
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
          <Button data-testid="edit-truck-save" disabled={busy || !name.trim()} onClick={save} className="bg-accent hover:bg-accent-press">Save truck</Button>
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
  const [query, setQuery] = useState("");

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

  const removeUser = async (u) => {
    try {
      await deleteUserApi(u.id);
      toast.success(`${u.name}'s account is deleted. Their past hours and jobs keep their name.`);
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

  const shownUsers = users.filter((u) => searchMatch(query, u.name, u.email, ...(u.roles || [u.role])));

  const copyInvite = (u) => {
    const text = [
      `You're on the Haul Yeah Moving team, ${u.name.split(" ")[0]}!`,
      `Log in here: ${window.location.origin}`,
      `Username: ${u.email}`,
      `Starting password: haulyeah123 (the app makes you pick your own the first time you sign in)`,
    ].join("\n");
    navigator.clipboard
      .writeText(text)
      .then(() => toast.success("Invite copied — paste it into a text or email to them."))
      .catch(() => toast.error("Couldn't copy. Try again."));
  };

  return (
    <div className="grid lg:grid-cols-3 gap-4 mt-4">
      <div className="lg:col-span-2 surface">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="font-bold text-primary">Team members</h2>
          <Button data-testid="add-user-btn" size="sm" className="gap-1.5 bg-accent hover:bg-accent-press" onClick={() => setAddOpen(true)}>
            <UserPlus className="w-4 h-4" /> Add person
          </Button>
        </div>
        <div className="px-4 py-2.5 border-b border-border">
          <SearchBar value={query} onChange={setQuery} placeholder="Search name, email, or role…" testId="team-search-input" />
        </div>
        <div className="divide-y divide-border">
          {shownUsers.map((u) => (
            <div key={u.id} data-testid="user-row" className={`flex flex-wrap items-center gap-x-2 gap-y-2 px-4 py-3 transition-colors hover:bg-surface-sunk/60 ${u.active ? "" : "opacity-55"}`}>
              <div className="min-w-[160px] flex-1">
                <p className="text-[14px] font-semibold text-primary">{u.name}</p>
                <p className="truncate text-[12.5px] text-faint">{u.email}</p>
              </div>
              {(u.roles?.length ? u.roles : [u.role]).map((r) => (
                <Badge key={r} variant="outline" className={`text-[10px] ${ROLE_BADGE[r] || ""}`}>{r}</Badge>
              ))}
              {!u.active && <Badge variant="outline" className="text-[10px] bg-destructive/10 text-destructive border-destructive/25">off</Badge>}
              {u.must_change_password && u.active && <Badge variant="outline" className="text-[10px] bg-warning/10 text-warning border-warning/25">temp password</Badge>}
              <div className="flex w-full items-center gap-2 sm:w-auto">
                <Button data-testid="employee-file-btn" variant="outline" size="sm" className="gap-1.5" onClick={() => setFileUser(u)}>
                  <IdCard className="w-3.5 h-3.5" /> File
                </Button>
                <Button data-testid="edit-roles-btn" variant="outline" size="sm" className="gap-1.5" onClick={() => setRolesUser(u)}>
                  <Pencil className="w-3.5 h-3.5" /> Roles
                </Button>
                <div className="ml-auto flex flex-wrap items-center gap-x-0.5 sm:ml-1">
                  {u.active && (
                    <button data-testid="copy-invite-btn" onClick={() => copyInvite(u)} className={ROW_LINK}>
                      <Copy className="w-3.5 h-3.5" aria-hidden="true" /> Invite
                    </button>
                  )}
                  <button data-testid="reset-password-btn" onClick={() => setResetUser(u)} className={ROW_LINK}>
                    <KeyRound className="w-3.5 h-3.5" aria-hidden="true" /> Reset password
                  </button>
                  <button
                    data-testid="toggle-active-btn"
                    onClick={() => toggleActive(u)}
                    className={`${ROW_LINK} ${u.active ? "text-destructive hover:text-destructive" : "text-success hover:text-success"}`}
                  >
                    {u.active ? <UserX className="w-3.5 h-3.5" aria-hidden="true" /> : <UserCheck className="w-3.5 h-3.5" aria-hidden="true" />}
                    {u.active ? "Deactivate" : "Reactivate"}
                  </button>
                </div>
              </div>
              {!u.active && (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button data-testid="delete-user-btn" variant="outline" size="sm" className="gap-1 text-xs text-destructive border-destructive/25 hover:bg-destructive/10">
                      <Trash2 className="w-3.5 h-3.5" /> Delete
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle className="font-display">Delete {u.name} for good?</AlertDialogTitle>
                      <AlertDialogDescription>This removes their account forever — it can't be undone. Their past time entries and job history keep their name.</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Keep them</AlertDialogCancel>
                      <AlertDialogAction data-testid="confirm-delete-user" onClick={() => removeUser(u)} className="bg-destructive hover:bg-destructive/90">Yes, delete</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}
            </div>
          ))}
          {users.length === 0 && <p className="text-sm text-faint px-4 py-6 text-center">Loading team…</p>}
          {users.length > 0 && shownUsers.length === 0 && <p className="text-sm text-faint px-4 py-6 text-center">No one matches that search.</p>}
        </div>
      </div>

      <div className="space-y-4">
        <div className="surface p-4">
          <h2 className="font-bold text-primary flex items-center gap-2 mb-3"><DollarSign className="w-4 h-4 text-accent-ink" /> Pay rates</h2>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label className="w-16 text-xs">Driver</Label>
              <Input data-testid="rate-driver-input" type="number" className="h-8" value={rates.driver} onChange={(e) => setRates((r) => ({ ...r, driver: e.target.value }))} />
              <span className="text-xs text-faint">/hr</span>
            </div>
            <div className="flex items-center gap-2">
              <Label className="w-16 text-xs">Helper</Label>
              <Input data-testid="rate-helper-input" type="number" className="h-8" value={rates.helper} onChange={(e) => setRates((r) => ({ ...r, helper: e.target.value }))} />
              <span className="text-xs text-faint">/hr</span>
            </div>
            <Button data-testid="save-rates-btn" size="sm" className="w-full mt-1 bg-primary hover:bg-[#152238]" onClick={saveRates}>Save rates</Button>
          </div>
        </div>

        <div className="surface p-4">
          <h2 className="font-bold text-primary flex items-center gap-2 mb-3"><Truck className="w-4 h-4 text-accent-ink" /> Trucks</h2>
          <div className="space-y-2">
            {trucks.map((t) => (
              <div key={t.id} data-testid="truck-row" className="flex items-center gap-1 text-sm">
                <div className="flex-1 min-w-0">
                  <span className={t.active ? "text-primary font-medium" : "text-faint line-through"}>{t.name}</span>
                  <span data-testid="truck-plate-label" className="text-xs text-faint ml-2">{t.plate || "no plate"}</span>
                </div>
                <Button data-testid="edit-truck-btn" variant="ghost" size="sm" className="h-7 px-2" onClick={() => setEditTruck(t)}>
                  <Pencil className="w-3.5 h-3.5" />
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button data-testid="remove-truck-btn" variant="ghost" size="sm" className="h-7 px-2 text-destructive hover:text-destructive">
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
                      <AlertDialogAction data-testid="confirm-remove-truck" onClick={() => removeTruck(t)} className="bg-destructive hover:bg-destructive/90">Yes, remove</AlertDialogAction>
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
