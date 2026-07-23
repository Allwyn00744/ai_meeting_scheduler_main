import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeOff, ChevronDown } from "lucide-react";
import { AuthLayout } from "@/components/layouts/AuthLayout";
import { Input, Select } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { getApiErrorMessage } from "@/api/client";

const schema = z.object({
  name: z.string().min(1, "Enter your full name."),
  email: z.string().min(1, "Enter your email.").email("Enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
  timezone: z.string(),
});
type FormValues = z.infer<typeof schema>;

export default function Register() {
  const navigate = useNavigate();
  const { push } = useToast();
  const { register: doRegister } = useAuth();
  const [showPassword, setShowPassword] = React.useState(false);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { timezone: "UTC" },
  });

  const onSubmit = async (values: FormValues) => {
    try {
      await doRegister(values);
      push("success", "Account created", "Welcome to SCHEDAI.");
      navigate("/dashboard");
    } catch (err) {
      const message = getApiErrorMessage(err, "Could not create your account.");
      setError("email", { message });
      push("error", "Registration failed", message);
    }
  };

  return (
    <AuthLayout variant="register">
      <h1 className="text-[26px] font-bold text-ink-700">Create your account</h1>
      <p className="mt-1 text-sm text-ink-700/60">Get started with AI-powered scheduling</p>

      <form className="mt-6 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ink-700">Full name</label>
          <Input placeholder="Maya Rodriguez" error={errors.name?.message} {...register("name")} />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ink-700">Email</label>
          <Input placeholder="name@company.com" error={errors.email?.message} {...register("email")} />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ink-700">Password</label>
          <Input
            type={showPassword ? "text" : "password"}
            placeholder="Min. 8 characters"
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
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ink-700">Timezone</label>
          <div className="relative">
            <Select className="appearance-none pr-9" {...register("timezone")}>
              <option value="UTC">UTC</option>
              <option value="Asia/Kolkata">Asia/Kolkata (UTC+5:30)</option>
              <option value="America/New_York">America/New_York (UTC-5:00)</option>
              <option value="Europe/London">Europe/London (UTC+0:00)</option>
            </Select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          </div>
        </div>

        <Button type="submit" variant="dark" className="w-full" loading={isSubmitting}>
          Create account
        </Button>

        <p className="text-center text-sm text-ink-700/60">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-brand-700 hover:text-brand-800">
            Sign in
          </Link>
        </p>

        <p className="text-center text-xs text-ink-700/40">
          By signing up, you agree to our Terms and Privacy Policy.
        </p>
      </form>
    </AuthLayout>
  );
}
