import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { Mail, Lock, Eye, EyeOff } from "lucide-react";
import { AuthLayout } from "@/components/layouts/AuthLayout";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { authApi } from "@/api/auth";
import { getApiErrorMessage } from "@/api/client";

const schema = z.object({
  email: z.string().min(1, "Enter your email.").email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type FormValues = z.infer<typeof schema>;

export default function Login() {
  const navigate = useNavigate();
  const { push } = useToast();
  const { login } = useAuth();
  const [showPassword, setShowPassword] = React.useState(false);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    try {
      await login(values);
      push("success", "Welcome back", "Signed in successfully.");
      navigate("/dashboard");
    } catch (err) {
      const message = getApiErrorMessage(err, "Invalid email or password.");
      setError("password", { message });
      push("error", "Sign in failed", message);
    }
  };

  return (
    <AuthLayout variant="login">
      <h1 className="text-[26px] font-bold text-ink-700">Welcome back</h1>
      <p className="mt-1 text-sm text-ink-700/60">Sign in to AI meeting scheduler</p>

      <form className="mt-6 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-ink-700">Email</label>
          <Input
            id="email"
            icon={<Mail className="h-4 w-4" />}
            placeholder="name@company.com"
            error={errors.email?.message}
            {...register("email")}
          />
        </div>
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label htmlFor="password" className="text-sm font-medium text-ink-700">Password</label>
            <button
              type="button"
              onClick={() => push("info", "Password reset isn't available yet", "Contact your workspace admin to reset your password.")}
              className="text-xs font-medium text-brand-700 hover:text-brand-800"
            >
              Forgot password?
            </button>
          </div>
          <Input
            id="password"
            icon={<Lock className="h-4 w-4" />}
            type={showPassword ? "text" : "password"}
            placeholder="Enter your password"
            error={errors.password?.message}
            rightAction={
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setShowPassword((s) => !s)}
                className="text-slate-400 hover:text-slate-600"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            }
            {...register("password")}
          />
        </div>

        <Button type="submit" variant="dark" className="w-full" loading={isSubmitting}>
          Sign in
        </Button>

        <div className="flex items-center gap-3 py-1">
          <div className="h-px flex-1 bg-ink-700/15" />
          <span className="text-xs text-ink-700/50">or</span>
          <div className="h-px flex-1 bg-ink-700/15" />
        </div>

        <Button
          type="button"
          variant="secondary"
          className="w-full border-transparent bg-white"
          onClick={() => (window.location.href = authApi.googleLoginRedirectUrl())}
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24">
            <path
              fill="#4285F4"
              d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.47c-.28 1.5-1.13 2.77-2.4 3.62v3.01h3.88c2.27-2.09 3.57-5.17 3.57-8.82z"
            />
            <path
              fill="#34A853"
              d="M12 24c3.24 0 5.96-1.07 7.95-2.91l-3.88-3.01c-1.08.72-2.45 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.96H1.27v3.11C3.25 21.3 7.31 24 12 24z"
            />
            <path
              fill="#FBBC05"
              d="M5.27 14.27a7.2 7.2 0 0 1 0-4.54V6.62H1.27a12 12 0 0 0 0 10.76l4-3.11z"
            />
            <path
              fill="#EA4335"
              d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0 7.31 0 3.25 2.7 1.27 6.62l4 3.11C6.22 6.86 8.87 4.75 12 4.75z"
            />
          </svg>
          Continue with Google
        </Button>

        <p className="pt-2 text-center text-sm text-ink-700/60">
          No account?{" "}
          <Link to="/register" className="font-medium text-brand-700 hover:text-brand-800">
            Register
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
