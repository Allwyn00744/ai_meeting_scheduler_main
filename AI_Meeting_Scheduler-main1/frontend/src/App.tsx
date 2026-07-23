import { Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "@/components/layouts/AppLayout";

import Login from "@/pages/auth/Login";
import Register from "@/pages/auth/Register";

import Dashboard from "@/pages/Dashboard";
import AIAssistant from "@/pages/AIAssistant";
import Resources from "@/pages/Resources";
import Availability from "@/pages/Availability";
import Users from "@/pages/Users";
import Settings from "@/pages/Settings";
import MeetingDetail from "@/pages/MeetingDetail";
import RescheduleMeeting from "@/pages/RescheduleMeeting";

import NotFound from "@/pages/NotFound";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />

      {/* Auth (public) */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* Authenticated app shell — AppLayout itself redirects to /login when unauthenticated */}
      <Route element={<AppLayout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/ai-assistant" element={<AIAssistant />} />
        <Route path="/resources" element={<Resources />} />
        <Route path="/availability" element={<Availability />} />
        <Route path="/users" element={<Users />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/meetings/:id" element={<MeetingDetail />} />
        <Route path="/meetings/:id/reschedule" element={<RescheduleMeeting />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
