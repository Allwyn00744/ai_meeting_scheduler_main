import illustration from "@/assets/auth-illustration.png";
import logoMark from "@/assets/logo-mark.png";
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
 *
 * Sized to fit inside the viewport with no scrollbar on common
 * laptop/desktop heights (h-screen + overflow-hidden + min-h-0 on
 * every flex/grid ancestor, clamp()-based type/illustration sizing)
 * rather than growing past it like a normal page.
 */
export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="flex h-screen w-full items-center justify-center overflow-hidden bg-brand-500 p-3 sm:p-5">
      <div className="grid h-full w-full max-w-[1440px] min-h-0 grid-cols-1 gap-6 rounded-[28px] bg-cream-300 p-5 sm:p-8 lg:grid-cols-2 lg:gap-4 lg:p-10">
        {/* Left: illustration + tagline - hidden on small screens, matches Figma's left column */}
        <div className="hidden min-h-0 flex-col justify-center overflow-hidden lg:flex">
          <div className="mb-3 shrink-0 text-ink-700">
            <img src={logoMark} alt="" className="h-[clamp(36px,5vh,64px)] w-auto" />
          </div>
          <h1 className="max-w-md shrink-0 text-[clamp(1.375rem,2.6vh,2.5rem)] font-bold leading-[1.1] text-ink-700">
            The Invisible Architect of Your Schedule
          </h1>

          {/* flex-1 + min-h-0 lets this fill all the leftover vertical
              space in the panel (rather than a fixed vh cap), so the
              illustration is as large as the viewport allows while
              the whole page still never scrolls. */}
          <div className="my-2 min-h-0 flex-1">
            <img
              src={illustration}
              alt="Person scheduling a meeting"
              className="h-full w-full object-contain object-left"
            />
          </div>

          <div className="mt-2 flex shrink-0 items-center gap-3">
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
        <div className="flex min-h-0 flex-col justify-center overflow-y-auto">
          <div className="mx-auto w-full max-w-sm py-4">
            <div className="mb-6">
              <Logo />
            </div>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
