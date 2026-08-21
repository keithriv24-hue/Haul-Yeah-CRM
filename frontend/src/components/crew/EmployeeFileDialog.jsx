import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Eye, EyeOff, IdCard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { getUserProfileApi, saveUserProfileApi, apiErrorMessage } from "@/lib/api";

const BLANK = {
  legal_name: "", phone: "", birthday: "", ssn: "", address: "",
  emergency_name: "", emergency_phone: "", hire_date: "", notes: "",
};

const calcAge = (dob) => {
  if (!dob) return null;
  const d = new Date(dob);
  if (isNaN(d)) return null;
  const t = new Date();
  let age = t.getFullYear() - d.getFullYear();
  const m = t.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && t.getDate() < d.getDate())) age--;
  return age >= 0 && age < 120 ? age : null;
};

export const EmployeeFileDialog = ({ user, onOpenChange }) => {
  const [form, setForm] = useState(BLANK);
  const [showSsn, setShowSsn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user) return;
    setShowSsn(false);
    setLoading(true);
    getUserProfileApi(user.id)
      .then((d) => setForm({ ...BLANK, ...(d.profile || {}) }))
      .catch(() => setForm(BLANK))
      .finally(() => setLoading(false));
  }, [user]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const age = calcAge(form.birthday);

  const save = async () => {
    setBusy(true);
    try {
      await saveUserProfileApi(user.id, form);
      toast.success(`${user.name}'s file saved.`);
      onOpenChange(null);
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <Dialog open={!!user} onOpenChange={() => onOpenChange(null)}>
      <DialogContent data-testid="employee-file-dialog" className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <IdCard className="w-5 h-5 text-accent-ink" /> {user?.name}'s employee file
          </DialogTitle>
          <DialogDescription>Everything here is optional and only visible to owners.</DialogDescription>
        </DialogHeader>
        {loading ? (
          <p className="text-sm text-faint py-6 text-center">Loading…</p>
        ) : (
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <Label>Full legal name</Label>
              <Input data-testid="file-legal-name" value={form.legal_name} onChange={set("legal_name")} placeholder="First Middle Last" />
            </div>
            <div>
              <Label>Phone number</Label>
              <Input data-testid="file-phone" type="tel" value={form.phone} onChange={set("phone")} placeholder="(973) 555-0100" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <Label>Birthday</Label>
                {age !== null && (
                  <Badge data-testid="file-age-chip" variant="outline" className="text-[10px] bg-accent/10 text-accent-ink border-accent/25">
                    Age {age}
                  </Badge>
                )}
              </div>
              <Input data-testid="file-birthday" type="date" value={form.birthday} onChange={set("birthday")} />
            </div>
            <div>
              <Label>SSN</Label>
              <div className="relative">
                <Input
                  data-testid="file-ssn"
                  type={showSsn ? "text" : "password"}
                  className="pr-10"
                  value={form.ssn}
                  onChange={set("ssn")}
                  placeholder="XXX-XX-XXXX"
                  autoComplete="off"
                />
                <button
                  type="button"
                  data-testid="file-ssn-toggle"
                  aria-label={showSsn ? "Hide SSN" : "Show SSN"}
                  onClick={() => setShowSsn((s) => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-faint hover:text-primary transition-colors"
                >
                  {showSsn ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div className="sm:col-span-2">
              <Label>Home address</Label>
              <Input data-testid="file-address" value={form.address} onChange={set("address")} placeholder="123 Main St, Newark NJ 07102" />
            </div>
            <div>
              <Label>Emergency contact</Label>
              <Input data-testid="file-emergency-name" value={form.emergency_name} onChange={set("emergency_name")} placeholder="Name" />
            </div>
            <div>
              <Label>Emergency phone</Label>
              <Input data-testid="file-emergency-phone" type="tel" value={form.emergency_phone} onChange={set("emergency_phone")} placeholder="(973) 555-0199" />
            </div>
            <div>
              <Label>Hire date</Label>
              <Input data-testid="file-hire-date" type="date" value={form.hire_date} onChange={set("hire_date")} />
            </div>
            <div className="sm:col-span-2">
              <Label>Other important info</Label>
              <Textarea data-testid="file-notes" value={form.notes} onChange={set("notes")} placeholder="Shirt size, allergies, driver's license, certifications…" />
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(null)}>Cancel</Button>
          <Button data-testid="employee-file-save" disabled={busy || loading} onClick={save} className="bg-accent hover:bg-accent-press">
            Save file
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
