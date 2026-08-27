"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useForgotPassword } from "@/lib/api/hooks";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const forgot = useForgotPassword();

  return (
    <div className="w-full">
      <p className="font-serif text-2xl font-semibold tracking-tight text-[#0C2D48] lg:hidden">
        CitationINTI
      </p>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-[#0C2D48] lg:mt-0">
        Reset password
      </h2>
      <p className="mt-1.5 text-sm text-slate-500">
        Enter your email and we&apos;ll send you a link to choose a new password.
      </p>

      <form
        className="mt-7 flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          forgot.mutate({ email });
        }}
      >
        <label className="block">
          <span className="text-sm font-medium text-[#1E3A5F]">Email</span>
          <input
            type="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@university.edu"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
          />
        </label>

        {forgot.isError && (
          <p className="text-sm text-red-600" role="alert">
            {(forgot.error as Error).message}
          </p>
        )}

        <Button
          type="submit"
          size="lg"
          disabled={!email || forgot.isPending}
          className="h-11 rounded-lg bg-sky-600 text-white shadow-sm hover:bg-sky-700 focus-visible:ring-sky-300"
        >
          {forgot.isPending ? "Sending…" : "Send reset link"}
        </Button>
      </form>

      {forgot.isSuccess && (
        <p className="mt-4 rounded-lg bg-sky-50 px-3.5 py-2.5 text-sm text-sky-800">
          If that email has an account, a reset link is on its way.
        </p>
      )}

      <div className="mt-4 text-sm">
        <Link
          href="/login"
          className="font-medium text-sky-600 hover:text-sky-700 hover:underline"
        >
          Back to sign in
        </Link>
      </div>
    </div>
  );
}
