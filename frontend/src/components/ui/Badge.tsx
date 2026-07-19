import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap",
  {
    variants: {
      variant: {
        success: "bg-emerald-50 text-emerald-700",
        warning: "bg-slate-100 text-slate-600",
        danger: "bg-red-50 text-red-600",
        info: "bg-brand-50 text-brand-700",
        neutral: "bg-slate-100 text-slate-500",
        dark: "bg-ink-900 text-white",
      },
    },
    defaultVariants: { variant: "neutral" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

// Maps the *real* status strings the backend produces:
// - Meeting.status: "scheduled" (default) / "cancelled" / "completed" (app/models/meeting.py, MeetingUpdate)
// - Participant.status: "Pending" (default) / "Accepted" / "Declined" (app/models/meeting_participant.py) — capitalized as stored
// - ActionItem.status: "pending" / "completed" (app/schemas/meeting_intelligence.py, lowercase)
// - Resource: no status string — is_active boolean, mapped via ResourceStatusBadge below
const STATUS_MAP: Record<string, { variant: BadgeProps["variant"]; label: string }> = {
  scheduled: { variant: "info", label: "Scheduled" },
  cancelled: { variant: "danger", label: "Cancelled" },
  completed: { variant: "success", label: "Completed" },
  pending: { variant: "warning", label: "Pending" },
  Pending: { variant: "warning", label: "Pending" },
  accepted: { variant: "success", label: "Accepted" },
  Accepted: { variant: "success", label: "Accepted" },
  declined: { variant: "danger", label: "Declined" },
  Declined: { variant: "danger", label: "Declined" },
};

export function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_MAP[status] ?? { variant: "neutral" as const, label: status };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}

export function ResourceStatusBadge({ isActive }: { isActive: boolean }) {
  return isActive ? (
    <Badge variant="info">Active</Badge>
  ) : (
    <Badge variant="neutral">Inactive</Badge>
  );
}
