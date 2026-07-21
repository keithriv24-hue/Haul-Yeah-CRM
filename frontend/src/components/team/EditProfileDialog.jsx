import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Camera, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { saveMyProfileApi, moderateProfileApi, uploadProfilePhotoApi, deleteProfilePhotoApi, apiErrorMessage } from "@/lib/api";

const EMPTY = { display_name: "", nickname: "", role_title: "", favorite_move: "", fun_fact: "", bio: "" };

export const EditProfileDialog = ({ open, onOpenChange, member, onSaved }) => {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    if (open && member) setForm({ ...EMPTY, ...(member.profile || {}) });
  }, [open, member]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    setBusy(true);
    try {
      if (member.is_self) await saveMyProfileApi(form);
      else await moderateProfileApi(member.id, form);
      toast.success("Profile saved.");
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  const uploadPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      await uploadProfilePhotoApi(file);
      toast.success("Photo updated.");
      onSaved();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
    setBusy(false);
    e.target.value = "";
  };

  const removePhoto = async () => {
    setBusy(true);
    try {
      await deleteProfilePhotoApi(member.id);
      toast.success("Photo removed.");
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e));
    }
    setBusy(false);
  };

  if (!member) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="edit-profile-dialog" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">{member.is_self ? "Edit your profile" : `Edit ${member.name}'s profile`}</DialogTitle>
          <DialogDescription>Keep it work-appropriate — the whole team can see this{member.is_self ? ", and the owner can edit or remove anything here" : ""}.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            {member.is_self && (
              <>
                <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={uploadPhoto} />
                <Button data-testid="profile-photo-upload-btn" variant="outline" size="sm" className="gap-1.5" disabled={busy} onClick={() => fileRef.current?.click()}>
                  <Camera className="w-4 h-4" /> {member.has_photo ? "Change photo" : "Add a photo"}
                </Button>
              </>
            )}
            {member.has_photo && (
              <Button data-testid="profile-photo-remove-btn" variant="outline" size="sm" className="gap-1.5 text-red-600 border-red-200 hover:bg-red-50" disabled={busy} onClick={removePhoto}>
                <Trash2 className="w-4 h-4" /> Remove photo
              </Button>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Display name</Label><Input data-testid="profile-display-name" value={form.display_name} onChange={set("display_name")} placeholder={member.name} /></div>
            <div><Label>Nickname</Label><Input data-testid="profile-nickname" value={form.nickname} onChange={set("nickname")} placeholder="The Machine" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Role title</Label><Input data-testid="profile-role-title" value={form.role_title} onChange={set("role_title")} placeholder="Lead Mover" /></div>
            <div><Label>Favorite move type</Label><Input data-testid="profile-favorite-move" value={form.favorite_move} onChange={set("favorite_move")} placeholder="Big house, no stairs" /></div>
          </div>
          <div><Label>Fun fact</Label><Input data-testid="profile-fun-fact" value={form.fun_fact} onChange={set("fun_fact")} placeholder="Once carried a couch solo" /></div>
          <div><Label>Short bio</Label><Textarea data-testid="profile-bio" rows={3} value={form.bio} onChange={set("bio")} placeholder="A line or two about you." /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button data-testid="profile-save-btn" disabled={busy} onClick={save} className="bg-[#E8743B] hover:bg-[#d4632e]">Save profile</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
