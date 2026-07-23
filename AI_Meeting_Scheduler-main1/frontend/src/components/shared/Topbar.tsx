import * as React from "react";
import { Search, Bell, HelpCircle } from "lucide-react";
import { Menu } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Avatar } from "../ui/Avatar";
import { NotificationsPanel } from "./NotificationsPanel";
import { useAuth } from "@/hooks/useAuth";

function initialsOf(name: string) {
  const parts = name.trim().split(/\s+/);
  return parts.length === 1 ? parts[0].slice(0, 2).toUpperCase() : (parts[0][0] + parts[1][0]).toUpperCase();
}

export function Topbar({ onMenuClick }: { onMenuClick?: () => void }) {
  const [notifOpen, setNotifOpen] = React.useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();

  return (
    <header className="flex h-[68px] items-center gap-4 border-b border-slate-200/70 bg-cream-200 px-4 sm:px-6">
      <button className="text-slate-500 md:hidden" onClick={onMenuClick} aria-label="Open menu">
        <Menu className="h-5 w-5" />
      </button>

      <div className="relative hidden max-w-md flex-1 sm:block">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          className="h-10 w-full rounded-lg border-0 bg-white pl-9 pr-3 text-sm text-slate-700 placeholder:text-slate-400 focus-ring"
          placeholder="Search meetings, documents, or insights..."
        />
      </div>

      <div className="flex flex-1 items-center justify-end gap-4">
        <div className="relative">
          <button
            className="relative text-ink-700/70 hover:text-ink-700"
            onClick={() => setNotifOpen((o) => !o)}
            aria-label="Notifications"
          >
            <Bell className="h-[19px] w-[19px]" />
          </button>
          <NotificationsPanel open={notifOpen} onClose={() => setNotifOpen(false)} />
        </div>
        <button className="text-ink-700/70 hover:text-ink-700" onClick={() => navigate("/settings")} aria-label="Help">
          <HelpCircle className="h-[19px] w-[19px]" />
        </button>
        <div className="h-6 w-px bg-slate-200" />
        <button className="flex items-center gap-2.5" onClick={() => navigate("/settings")}>
          <Avatar
            initials={user ? initialsOf(user.name) : "?"}
            size={34}
            colorClass="bg-brand-100 text-brand-800"
          />
          {user && <span className="hidden text-sm font-medium text-ink-700 sm:inline">{user.name}</span>}
        </button>
      </div>
    </header>
  );
}
