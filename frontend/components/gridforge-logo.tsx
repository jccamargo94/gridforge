import { cn } from "@/lib/utils";

export function GridForgeLogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <path
        d="M16 2l12.124 7v14L16 30 3.876 23V9L16 2z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <line
        x1="16"
        y1="2"
        x2="16"
        y2="18"
        stroke="currentColor"
        strokeWidth="1"
        opacity="0.6"
      />
      <line
        x1="3.876"
        y1="23"
        x2="16"
        y2="18"
        stroke="currentColor"
        strokeWidth="1"
        opacity="0.4"
      />
      <line
        x1="28.124"
        y1="23"
        x2="16"
        y2="18"
        stroke="currentColor"
        strokeWidth="1"
        opacity="0.4"
      />
      <circle cx="16" cy="18" r="3" fill="currentColor" />
      <circle cx="16" cy="1.5" r="1.5" fill="currentColor" opacity="0.7" />
      <circle cx="4" cy="23" r="1.5" fill="currentColor" opacity="0.7" />
      <circle cx="28" cy="23" r="1.5" fill="currentColor" opacity="0.7" />
    </svg>
  );
}

export function GridForgeLogoFull({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <GridForgeLogoMark className="size-8 text-amber-500" />
      <div>
        <p className="text-lg font-bold leading-tight text-foreground">
          Grid<span className="text-amber-500">Forge</span>
        </p>
        <p className="text-[10px] font-medium tracking-[0.2em] text-muted-foreground uppercase">
          Dispatch Modeler
        </p>
      </div>
    </div>
  );
}
