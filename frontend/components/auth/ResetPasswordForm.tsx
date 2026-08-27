"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useResetPassword } from "@/lib/api/hooks";

export function ResetPasswordForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const reset = useResetPassword();

  const mismatch = confirm.length > 0 && confirm !== password;

  if (!token) {
    return (
      <div className="w-full">
        <h2 className="text-2xl font-semibold tracking-tight text-[#0C2D48]">Reset password</h2>
        <p className="mt-3 rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
          This reset link is missing its token. Check the full link from your email.
        </p>
        <Link
          href="/forgot-password"
          className="mt-4 block text-sm font-medium text-sky-600 hover:text-sky-700 hover:underline"
        >
          Request a new link
        </Link>
      </div>
    );
  }

  return (
    <div className="w-full">
      <p className="font-serif text-2xl font-semibold tracking-tight text-[#0C2D48] lg:hidden">
        CitationINTI
      </p>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-[#0C2D48] lg:mt-0">
        Choose a new password
      </h2>
      <p className="mt-1.5 text-sm text-slate-500">
        Set a new password for your account, then sign in with it.
      </p>

      <form
        className="mt-7 flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          reset.mutate(
            { token, new_password: password },
            { onSuccess: () => router.push("/login") },
          );
        }}
      >
        <label className="block">
          <span className="text-sm font-medium text-[#1E3A5F]">New password</span>
          <input
            type="password"
            required
            minLength={8}
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-[#1E3A5F]">Confirm new password</span>
          <input
            type="password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Repeat your new password"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
          />
        </label>

        {mismatch && (
          <p className="text-sm text-red-600" role="alert">
            Passwords do not match
          </p>
        )}
        {reset.isError && (
          <p className="text-sm text-red-600" role="alert">
            {(reset.error as Error).message}
          </p>
        )}

        <Button
          type="submit"
          size="lg"
          disabled={!password || password.length < 8 || mismatch || reset.isPending}
          className="h-11 rounded-lg bg-sky-600 text-white shadow-sm hover:bg-sky-700 focus-visible:ring-sky-300"
        >
          {reset.isPending ? "Saving…" : "Set new password"}
        </Button>
      </form>
    </div>
  );
}
