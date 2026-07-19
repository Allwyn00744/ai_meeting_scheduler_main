import illustration from "@/assets/auth-illustration.png";
import { Logo } from "../shared/Logo";

interface AuthLayoutProps {
  children: React.ReactNode;
  variant: "login" | "register";
}

/**
 * Split-panel auth shell shared by Login / Register, matching the
 * Figma "Login" / "Sign up" frames: one big rounded amber card, the
 * left side carrying the illustration + tagline, the right side
 * carrying the form (passed in as children).
 */
export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-brand-500 p-3 sm:p-6">
      <div className="grid w-full max-w-[1440px] grid-cols-1 gap-10 rounded-[32px] bg-cream-300 p-6 sm:p-10 lg:grid-cols-2 lg:gap-6 lg:p-14">
        {/* Left: illustration + tagline - hidden on small screens, matches Figma's left column */}
        <div className="hidden flex-col justify-center lg:flex">
          <div className="mb-8 text-ink-700">
            <svg width="72" height="90" viewBox="0 0 48 60" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M3.10204 32.3089V15.8248L14.6939 0H39.0204L48 5.76945L27.5918 15.8248L48 32.3089L44.0816 58.1891L22.2041 59.8375L0 58.1891V50.936L36.5714 37.7487L3.10204 32.3089Z"
                fill="currentColor"
              />
            </svg>
          </div>
          <h1 className="max-w-md text-[44px] font-bold leading-[1.1] text-ink-700">
            The Invisible Architect of Your Schedule
          </h1>

          <div className="relative mt-8 max-w-lg">
            <img src={illustration} alt="Person scheduling a meeting" className="w-full max-w-[520px]" />
          </div>

          <div className="mt-2 flex items-center gap-3">
            <div className="flex -space-x-2.5">
              {["bg-rose-300", "bg-sky-300", "bg-emerald-300"].map((c, i) => (
                <div key={i} className={`h-9 w-9 rounded-full border-2 border-cream-300 ${c}`} />
              ))}
              <div className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-cream-300 bg-ink-700 text-[11px] font-semibold text-white">
                +17k
              </div>
            </div>
            <p className="text-sm text-ink-700/80">More than 17k professionals joined us</p>
          </div>
        </div>

        {/* Right: form panel */}
        <div className="flex flex-col justify-center">
          <div className="mx-auto w-full max-w-sm">
            <div className="mb-8">
              <Logo />
            </div>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
