"use client";
import { AuthBrandMark } from "@/components/auth/AuthBrandMark";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "@/components/PasswordInput";
import { RedirectTo } from "@/components/auth/RedirectTo";
import { useLogin, useSession } from "@/lib/api/hooks";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const registeredEmail = params.get("registered");
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
      <AuthBrandMark />
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-[#0C2D48] lg:mt-0">
        Sign in
      </h2>
      <p className="mt-1.5 text-sm text-slate-500">
        Upload a draft and find Scopus-indexed citations for its claims.
      </p>

      {registeredEmail && (
        <p className="mt-4 rounded-lg bg-green-50 px-3.5 py-2.5 text-sm text-green-800">
          An activation email has been sent to{" "}
          <span className="font-medium">{registeredEmail}</span>. Please activate your account
          before signing in.
        </p>
      )}

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
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-[#1E3A5F]">Password</span>
          <PasswordInput
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Your password"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
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
          className="h-11 rounded-lg bg-red-600 text-white shadow-sm hover:bg-red-700 focus-visible:ring-red-300"
        >
          {login.isPending ? "Signing in…" : "Sign in"}
        </Button>

        <div className="flex items-center justify-between text-sm">
          <Link
            href="/forgot-password"
            className="font-medium text-red-600 hover:text-red-700 hover:underline"
          >
            Forgot password?
          </Link>
          <Link
            href="/register"
            className="font-medium text-red-600 hover:text-red-700 hover:underline"
          >
            Create account
          </Link>
        </div>
      </form>
    </div>
  );
}
