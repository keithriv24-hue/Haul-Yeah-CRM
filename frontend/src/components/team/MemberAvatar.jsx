import React from "react";
import { profilePhotoUrl } from "@/lib/api";

const SIZES = {
  sm: "w-9 h-9 text-xs",
  md: "w-12 h-12 text-sm",
  lg: "w-24 h-24 text-2xl",
};

export const MemberAvatar = ({ id, name, hasPhoto, size = "md", version }) => {
  const initials = (name || "?")
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
  if (hasPhoto) {
    return (
      <img
        data-testid="member-avatar-photo"
        src={profilePhotoUrl(id, version)}
        alt={name}
        className={`${SIZES[size]} rounded-full object-cover border-2 border-white shadow shrink-0`}
      />
    );
  }
  return (
    <div
      data-testid="member-avatar-initials"
      className={`${SIZES[size]} rounded-full bg-[#1B2A4A] text-white font-display font-bold flex items-center justify-center shrink-0`}
    >
      {initials}
    </div>
  );
};
