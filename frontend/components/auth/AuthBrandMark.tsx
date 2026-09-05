import { IntiLogo } from "@/components/IntiLogo";

/** Mobile brand header for auth forms. The split-screen brand panel is
 * hidden on small screens, so the logo + wordmark show here instead. */
export function AuthBrandMark() {
  return (
    <div className="flex items-center gap-3 lg:hidden">
      <IntiLogo size="sm" />
      <p className="font-serif text-2xl font-semibold tracking-tight text-[#0C2D48]">
        INTI Citation
      </p>
    </div>
  );
}
