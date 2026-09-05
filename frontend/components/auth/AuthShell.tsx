import type { ReactNode } from "react";
import { IntiLogo } from "@/components/IntiLogo";

/** Shared split-screen shell for the auth pages: white theme, a light brand
 * panel with the red INTI logo on the left (lg+), and the form panel on the
 * right. */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-red-50 via-white to-red-50 px-4 py-10">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl bg-white shadow-xl ring-1 ring-zinc-200 lg:grid-cols-2">
        {/* Brand panel — left, hidden on small screens */}
        <section className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-red-100 via-red-50 to-white p-10 text-[#0C2D48] lg:flex">
          <span
            aria-hidden
            className="pointer-events-none absolute -left-6 -top-10 select-none font-serif text-[13rem] leading-none text-red-200"
          >
            &ldquo;
          </span>

          <div className="relative flex items-center gap-3">
            <IntiLogo />
            <div>
              <p className="font-serif text-2xl font-semibold tracking-tight">INTI Citation</p>
              <p className="mt-0.5 text-[0.7rem] uppercase tracking-[0.2em] text-red-700">
                Scopus reference recommender
              </p>
            </div>
          </div>

          <p className="relative max-w-sm font-serif text-3xl leading-snug">
            Find the Scopus-indexed references your draft actually needs from INTI&apos;s papers.
          </p>

          <p className="relative text-xs text-red-700/70">
            Every recommendation is scored and verified before you cite it.
          </p>
        </section>

        {/* Form panel — right */}
        <section className="flex items-center p-8 sm:p-12">{children}</section>
      </div>
    </main>
  );
}
