"use client";
import { AuthBrandMark } from "@/components/auth/AuthBrandMark";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useActivate } from "@/lib/api/hooks";

export function ActivateForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const activate = useActivate();
  const [attempted, setAttempted] = useState(false);

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
            {(activate.error as Error).message}
          </p>
          <Link
            href="/login"
            className="mt-4 block text-sm font-medium text-red-600 hover:text-red-700 hover:underline"
          >
            Go to sign in
          </Link>
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
