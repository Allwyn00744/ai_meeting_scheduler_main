import * as React from "react";
import { Outlet, Navigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar, SidebarContent } from "../shared/Sidebar";
import { Topbar } from "../shared/Topbar";
import { useAuth } from "@/hooks/useAuth";
import { useMeetingSocket } from "@/hooks/useMeetingSocket";
import { Logo } from "../shared/Logo";

function FullPageLoader() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-cream-200">
      <Logo />
      <div className="flex gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-2 w-2 animate-bounce rounded-full bg-brand-500"
            style={{ animationDelay: `${i * 0.12}s` }}
          />
        ))}
      </div>
    </div>
  );
}

/** Shell used by every authenticated screen. Redirects to /login if there's no valid session. */
export function AppLayout() {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const { user, loading } = useAuth();
  useMeetingSocket(Boolean(user));

  if (loading) return <FullPageLoader />;
  if (!user) return <Navigate to="/login" replace />;

  return (
    <div className="flex h-screen w-full overflow-hidden bg-cream-200">
      <Sidebar />

      <AnimatePresence>
        {mobileOpen && (
          <div className="fixed inset-0 z-40 md:hidden">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-ink-900/40"
              onClick={() => setMobileOpen(false)}
            />
            <motion.div
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ type: "tween", duration: 0.2 }}
              className="relative h-full w-[280px] bg-cream-100"
            >
              <SidebarContent onNavigate={() => setMobileOpen(false)} />
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenuClick={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
