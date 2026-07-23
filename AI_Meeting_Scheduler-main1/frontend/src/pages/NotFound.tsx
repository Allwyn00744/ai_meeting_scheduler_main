import { useNavigate } from "react-router-dom";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Logo } from "@/components/shared/Logo";

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-6 text-center">
      <div className="mb-8"><Logo /></div>
      <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
        <Compass className="h-8 w-8" />
      </div>
      <p className="text-6xl font-extrabold text-slate-900">404</p>
      <h1 className="mt-2 text-xl font-semibold text-slate-800">Page not found</h1>
      <p className="mt-2 max-w-sm text-sm text-slate-500">
        The page you're looking for doesn't exist or may have been moved.
      </p>
      <Button className="mt-6" onClick={() => navigate("/dashboard")}>Back to dashboard</Button>
    </div>
  );
}
