"use client";
import { AuthBrandMark } from "@/components/auth/AuthBrandMark";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useActivate, useResendActivation } from "@/lib/api/hooks";

export function ActivateForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const activate = useActivate();
  const resend = useResendActivation();
  const [attempted, setAttempted] = useState(false);
  const [email, setEmail] = useState("");

  useEffect(() => {
    if (token && !attempted) {
      setAttempted(true);
      activate.mutate({ token }, { onSuccess: () => router.push("/") });
    }
  }, [token, attempted, activate, router]);

  if (!token) {
    return (
      <div className="w-full">
        <h2 className="text-2xl font-semibold tracking-tight text-[#0C2D48]">Activate account</h2>
        <p className="mt-3 rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          This activation link is missing its token. Check the full link from your email.
        </p>
        <Link
          href="/login"
          className="mt-4 block text-sm font-medium text-red-600 hover:text-red-700 hover:underline"
        >
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="w-full">
      <AuthBrandMark />
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-[#0C2D48] lg:mt-0">
        Activate account
      </h2>

      {activate.isPending && (
        <p className="mt-6 text-sm text-slate-500">Activating your account…</p>
      )}

      {activate.isError && (
        <>
          <p className="mt-6 rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-700" role="alert">
            This activation link is invalid or has expired. Your account may already be active —
            try signing in, or request a new link.
          </p>
          <Link
            href="/login"
            className="mt-4 block text-sm font-medium text-red-600 hover:text-red-700 hover:underline"
          >
            Go to sign in
          </Link>

          <form
            className="mt-6 border-t border-red-100 pt-4"
            onSubmit={(e) => {
              e.preventDefault();
              resend.mutate({ email });
            }}
          >
            <p className="text-sm font-medium text-[#1E3A5F]">Resend activation email</p>
            <div className="mt-2 flex items-start gap-2">
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@university.edu"
                className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
              />
              <Button type="submit" disabled={!email || resend.isPending} className="shrink-0">
                {resend.isPending ? "Sending…" : "Send"}
              </Button>
            </div>
            {resend.isSuccess && (
              <p className="mt-2 text-sm text-green-700">
                If that address has an unactivated account, a new link is on its way.
              </p>
            )}
            {resend.isError && (
              <p className="mt-2 text-sm text-red-600" role="alert">
                {(resend.error as Error).message}
              </p>
            )}
          </form>
        </>
      )}

      {activate.isSuccess && (
        <>
          <p className="mt-6 rounded-lg bg-green-50 px-3.5 py-2.5 text-sm text-green-800">
            Your account is active. Welcome to INTI Citation.
          </p>
          <Button
            type="button"
            size="lg"
            className="mt-4 h-11 rounded-lg bg-red-600 text-white shadow-sm hover:bg-red-700 focus-visible:ring-red-300"
            onClick={() => router.push("/")}
          >
            Continue
          </Button>
        </>
      )}
    </div>
  );
}
