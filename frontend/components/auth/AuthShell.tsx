import type { ReactNode } from "react";

/** Shared split-screen shell for the auth pages: light-blue background, a
 * citation-quote brand panel on the left (lg+), and the form panel on the
 * right. */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-sky-100 via-sky-50 to-sky-200 px-4 py-10">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl bg-white shadow-xl shadow-sky-200/60 ring-1 ring-sky-200/70 lg:grid-cols-2">
        {/* Brand panel — left, hidden on small screens */}
        <section className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-sky-700 via-sky-600 to-sky-500 p-10 text-white lg:flex">
          <span
            aria-hidden
            className="pointer-events-none absolute -left-6 -top-10 select-none font-serif text-[13rem] leading-none text-white/15"
          >
            &ldquo;
          </span>

          <div className="relative">
            <p className="font-serif text-2xl font-semibold tracking-tight">CitationINTI</p>
            <p className="mt-1 text-[0.7rem] uppercase tracking-[0.2em] text-sky-100">
              Scopus reference recommender
            </p>
          </div>

          <p className="relative max-w-sm font-serif text-3xl leading-snug">
            Find the Scopus-indexed references your draft actually needs.
          </p>

          <p className="relative text-xs text-sky-100">
            Every recommendation is scored and verified before you cite it.
          </p>
        </section>

        {/* Form panel — right */}
        <section className="flex items-center p-8 sm:p-12">{children}</section>
      </div>
    </main>
  );
}
