import React from "react";
import {
  Truck, Zap, Crown, Trophy, CarFront, Map, Compass, Hand, Dumbbell, Shield, Repeat, Music, Star, Flame,
  ShieldCheck, TrendingUp, Sunrise, Handshake, Layers, BadgeDollarSign, Target, Lock, RotateCcw, Award, Medal,
} from "lucide-react";

export const BADGE_ICONS = {
  Truck, Zap, Crown, Trophy, CarFront, Map, Compass, Hand, Dumbbell, Shield, Repeat, Music, Star, Flame,
  ShieldCheck, TrendingUp, Sunrise, Handshake, Layers, BadgeDollarSign, Target, Lock, RotateCcw, Award, Medal,
};

const RARITY_RING = {
  bronze: "from-amber-500 via-amber-600 to-amber-800",
  silver: "from-slate-300 via-slate-400 to-slate-500",
  gold: "from-yellow-300 via-amber-400 to-amber-500",
};

export const RARITY_CHIP = {
  bronze: "bg-amber-100 text-amber-800 border-amber-300",
  silver: "bg-slate-100 text-slate-600 border-slate-300",
  gold: "bg-yellow-100 text-yellow-800 border-yellow-300",
};

export const TEAM_CHIP = {
  crew: "bg-orange-100 text-orange-800 border-orange-300",
  sales: "bg-sky-100 text-sky-800 border-sky-300",
};

const SIZES = {
  sm: { outer: "w-10 h-10 p-[3px]", icon: "w-4 h-4" },
  md: { outer: "w-16 h-16 p-1", icon: "w-6 h-6" },
  lg: { outer: "w-20 h-20 p-1", icon: "w-8 h-8" },
};

export const BadgeMedallion = ({ badge, unlocked = true, size = "md", testId }) => {
  const Icon = BADGE_ICONS[badge.icon] || Medal;
  const s = SIZES[size] || SIZES.md;
  return (
    <div
      data-testid={testId || "badge-medallion"}
      title={`${badge.name}${badge.description ? ` — ${badge.description}` : ""}`}
      className={`rounded-full shrink-0 ${s.outer} ${
        unlocked ? `bg-gradient-to-br ${RARITY_RING[badge.rarity] || RARITY_RING.bronze} shadow-sm` : "bg-slate-200"
      }`}
    >
      <div className={`w-full h-full rounded-full flex items-center justify-center ${unlocked ? "bg-[#1B2A4A]" : "bg-slate-100"}`}>
        <Icon className={`${s.icon} ${unlocked ? "text-[#E8743B]" : "text-slate-300"}`} />
      </div>
    </div>
  );
};
