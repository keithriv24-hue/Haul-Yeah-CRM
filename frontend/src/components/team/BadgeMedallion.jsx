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
  bronze: "from-warning via-amber-600 to-warning",
  silver: "from-border-strong via-slate-400 to-faint",
  gold: "from-warning via-amber-400 to-warning",
};

export const RARITY_CHIP = {
  bronze: "bg-warning/12 text-warning border-warning/30",
  silver: "bg-surface-sunk text-ink-2 border-border-strong",
  gold: "bg-warning/12 text-warning border-warning/30",
};

export const TEAM_CHIP = {
  crew: "bg-accent/12 text-accent-ink border-accent/30",
  sales: "bg-info/12 text-info border-info/30",
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
        unlocked ? `bg-gradient-to-br ${RARITY_RING[badge.rarity] || RARITY_RING.bronze} shadow-sm` : "bg-muted"
      }`}
    >
      <div className={`w-full h-full rounded-full flex items-center justify-center ${unlocked ? "bg-primary" : "bg-surface-sunk"}`}>
        <Icon className={`${s.icon} ${unlocked ? "text-accent-ink" : "text-faint/70"}`} />
      </div>
    </div>
  );
};
