"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Client-side redirect, used to send logged-out visitors to /login and
 * already-logged-in visitors away from /login. */
export function RedirectTo({ to }: { to: string }) {
  const router = useRouter();
  useEffect(() => {
    router.replace(to);
  }, [to, router]);
  return null;
}
