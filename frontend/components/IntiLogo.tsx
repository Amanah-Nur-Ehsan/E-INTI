import { cn } from "@/lib/utils";

const SIZES = {
  sm: "h-8 w-12 rounded-lg text-sm",
  md: "h-10 w-16 rounded-xl text-lg",
  lg: "h-14 w-20 rounded-xl text-2xl",
} as const;

/** The "INTI" mark: a red rounded tile with white serif lettering. Pops on
 * the white theme (and stays visible on any accent background). */
export function IntiLogo({
  className,
  size = "md",
}: {
  className?: string;
  size?: keyof typeof SIZES;
}) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center bg-red-600 font-serif font-bold tracking-tight text-white shadow-sm",
        SIZES[size],
        className,
      )}
    >
      INTI
    </div>
  );
}
