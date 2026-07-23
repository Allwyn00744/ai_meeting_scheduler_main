import * as React from "react";
import { cn } from "@/lib/utils";

export interface StatCardProps {
  label: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  tone?: "default" | "danger";
  className?: string;
}

/** Matches the Dashboard "UPCOMING / PENDING RSVP / CONFLICTS" stat cards. */
export function StatCard({ label, value, icon, tone = "default", className }: StatCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border p-5",
        tone === "danger" ? "border-red-100 bg-red-50" : "border-slate-200 bg-slate-50",
        className
      )}
    >
      <div className="flex items-center justify-between">
        <p
          className={cn(
            "text-xs font-semibold tracking-wide",
            tone === "danger" ? "text-red-500" : "text-slate-500"
          )}
        >
          {label}
        </p>
        {icon}
      </div>
      <p className={cn("mt-2 text-3xl font-bold", tone === "danger" ? "text-red-600" : "text-slate-900")}>
        {value}
      </p>
    </div>
  );
}

/** Small icon-left stat used on the Resources page. */
export function IconStatCard({
  icon,
  iconBg,
  label,
  value,
}: {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4">
      <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", iconBg)}>{icon}</div>
      <div>
        <p className="text-xs text-slate-500">{label}</p>
        <p className="text-xl font-bold text-slate-900">{value}</p>
      </div>
    </div>
  );
}
