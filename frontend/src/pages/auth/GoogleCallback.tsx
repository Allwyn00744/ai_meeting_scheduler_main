import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/components/ui/Toast";
import { Logo } from "@/components/shared/Logo";

/**
 * Landing page for GET /auth/google/callback's redirect
 * (`{FRONTEND_URL}/auth/google/callback#token=...`). The token travels
 * as a URL fragment (never sent to any server, unlike a query param)
 * so it never appears in access logs - read it client-side here and
 * hand it to useAuth the same way a normal email/password login does.
 */
export default function GoogleCallback() {
  const navigate = useNavigate();
  const { push } = useToast();
  const { loginWithToken } = useAuth();
  const ranOnce = React.useRef(false);

  React.useEffect(() => {
    if (ranOnce.current) return;
    ranOnce.current = true;

    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");

    if (!token) {
      push("error", "Google sign-in failed", "Please try again.");
      navigate("/login", { replace: true });
      return;
    }

    loginWithToken(token)
      .then(() => {
        push("success", "Welcome", "Signed in with Google.");
        navigate("/dashboard", { replace: true });
      })
      .catch(() => {
        push("error", "Google sign-in failed", "Please try again.");
        navigate("/login", { replace: true });
      });
  }, [loginWithToken, navigate, push]);

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
