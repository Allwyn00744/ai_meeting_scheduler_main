import * as React from "react";
import { cn } from "@/lib/utils";

export interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  initials: string;
  size?: number;
  colorClass?: string;
  online?: boolean;
  src?: string;
}

export function Avatar({
  initials,
  size = 36,
  colorClass = "bg-brand-100 text-brand-700",
  online,
  src,
  className,
  ...props
}: AvatarProps) {
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      {src ? (
        <img
          src={src}
          alt={initials}
          className={cn("h-full w-full rounded-full object-cover", className)}
          {...(props as React.ImgHTMLAttributes<HTMLImageElement>)}
        />
      ) : (
        <div
          className={cn(
            "flex h-full w-full items-center justify-center rounded-full font-medium",
            colorClass,
            className
          )}
          style={{ fontSize: size * 0.36 }}
        >
          {initials}
        </div>
      )}
      {online && (
        <span
          className="absolute bottom-0 right-0 rounded-full border-2 border-white bg-emerald-500"
          style={{ width: size * 0.28, height: size * 0.28 }}
        />
      )}
    </div>
  );
}

export function AvatarStack({ initials }: { initials: string[] }) {
  return (
    <div className="flex -space-x-2">
      {initials.map((i) => (
        <div
          key={i}
          className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-brand-100 text-[11px] font-medium text-brand-700"
        >
          {i}
        </div>
      ))}
    </div>
  );
}
