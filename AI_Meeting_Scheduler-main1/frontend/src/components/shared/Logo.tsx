import logoMark from "@/assets/logo-mark.png";
import { cn } from "@/lib/utils";

/**
 * Real SCHEDAI brand mark - the icon is the exact PNG exported from the
 * Figma file (src/assets/logo-mark.png); the "SCHEDAI" wordmark next to
 * it is set in the app's own sans typeface (bold, wide tracking) to
 * match the Figma text layer exactly rather than an image, so it scales
 * and recolors cleanly.
 */
export function Logo({ light, size = 28 }: { light?: boolean; size?: number }) {
  return (
    <div className="flex items-center gap-2">
      <img src={logoMark} alt="" className="shrink-0" style={{ height: size, width: size * 0.96 }} />
      <span
        className={cn(
          "text-[15px] font-bold tracking-wide",
          light ? "text-white" : "text-ink-700"
        )}
        style={{ fontSize: size * 0.5 }}
      >
        SCHEDAI
      </span>
    </div>
  );
}
