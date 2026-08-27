"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useRegister } from "@/lib/api/hooks";

export function RegisterForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const register = useRegister();

  const mismatch = confirm.length > 0 && confirm !== password;

  return (
    <div className="w-full">
      <p className="font-serif text-2xl font-semibold tracking-tight text-[#0C2D48] lg:hidden">
        CitationINTI
      </p>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-[#0C2D48] lg:mt-0">
        Create account
      </h2>
      <p className="mt-1.5 text-sm text-slate-500">
        You&apos;ll receive an email with a link to activate your account.
      </p>

      <form
        className="mt-7 flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          register.mutate({ email, password });
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

        <label className="block">
          <span className="text-sm font-medium text-[#1E3A5F]">Password</span>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-[#1E3A5F]">Confirm password</span>
          <input
            type="password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Repeat your password"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
          />
        </label>

        {mismatch && (
          <p className="text-sm text-red-600" role="alert">
            Passwords do not match
          </p>
        )}
        {register.isError && (
          <p className="text-sm text-red-600" role="alert">
            {(register.error as Error).message}
          </p>
        )}

        <Button
          type="submit"
          size="lg"
          disabled={!email || !password || password.length < 8 || mismatch || register.isPending}
          className="h-11 rounded-lg bg-sky-600 text-white shadow-sm hover:bg-sky-700 focus-visible:ring-sky-300"
        >
          {register.isPending ? "Creating account…" : "Create account"}
        </Button>
      </form>

      {register.isSuccess && (
        <p className="mt-4 rounded-lg bg-sky-50 px-3.5 py-2.5 text-sm text-sky-800">
          Check your email for an activation link before signing in.
        </p>
      )}

      <div className="mt-4 text-sm">
        <Link
          href="/login"
          className="font-medium text-sky-600 hover:text-sky-700 hover:underline"
        >
          Already have an account? Sign in
        </Link>
      </div>
    </div>
  );
}
