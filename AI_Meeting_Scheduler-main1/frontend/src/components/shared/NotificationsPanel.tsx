import { Inbox, X } from "lucide-react";

/**
 * The backend has no notifications concept (no table, no endpoint) — see
 * the integration notes in the project README. Rather than fabricate fake
 * data, this renders an honest empty state. Swap the body for a real
 * fetch once a notifications endpoint exists.
 */
export function NotificationsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="absolute right-0 top-10 z-30 w-80 rounded-xl border border-slate-200 bg-white shadow-lg">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <p className="text-sm font-semibold text-slate-900">Notifications</p>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex flex-col items-center gap-2 p-8 text-center">
        <Inbox className="h-5 w-5 text-slate-300" />
        <p className="text-xs text-slate-400">No notifications yet.</p>
      </div>
    </div>
  );
}
