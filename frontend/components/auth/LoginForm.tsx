"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { RedirectTo } from "@/components/auth/RedirectTo";
import { useLogin, useSession } from "@/lib/api/hooks";

export function LoginForm() {
  const router = useRouter();
  const { data: session, isLoading } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();

  if (isLoading) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }
  if (session?.authenticated) return <RedirectTo to="/" />;

  return (
    <div className="w-full">
      <p className="font-serif text-2xl font-semibold tracking-tight text-[#0C2D48] lg:hidden">
        CitationINTI
      </p>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-[#0C2D48] lg:mt-0">
        Sign in
      </h2>
      <p className="mt-1.5 text-sm text-slate-500">
        Upload a draft and find Scopus-indexed citations for its claims.
      </p>

      <form
        className="mt-7 flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate(
            { email, password },
            { onSuccess: () => router.push("/") },
          );
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
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Your password"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200"
          />
        </label>

        {login.isError && (
          <p className="text-sm text-red-600" role="alert">
            {(login.error as Error).message}
          </p>
        )}

        <Button
          type="submit"
          size="lg"
          disabled={!email || !password || login.isPending}
          className="h-11 rounded-lg bg-sky-600 text-white shadow-sm hover:bg-sky-700 focus-visible:ring-sky-300"
        >
          {login.isPending ? "Signing in…" : "Sign in"}
        </Button>

        <div className="flex items-center justify-between text-sm">
          <Link
            href="/forgot-password"
            className="font-medium text-sky-600 hover:text-sky-700 hover:underline"
          >
            Forgot password?
          </Link>
          <Link
            href="/register"
            className="font-medium text-sky-600 hover:text-sky-700 hover:underline"
          >
            Create account
          </Link>
        </div>
      </form>
    </div>
  );
}
