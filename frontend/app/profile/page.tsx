"use client";

import { useEffect, useState } from "react";
import { RedirectTo } from "@/components/auth/RedirectTo";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useSession, useUpdateProfile } from "@/lib/api/hooks";

export default function ProfilePage() {
  const { data: session, isLoading } = useSession();
  const updateProfile = useUpdateProfile();
  const [fullName, setFullName] = useState("");

  useEffect(() => {
    if (session?.full_name != null) setFullName(session.full_name);
  }, [session?.full_name]);

  if (isLoading) {
    return (
      <main className="mx-auto w-full max-w-3xl px-4 py-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }
  if (!session?.authenticated) {
    return <RedirectTo to="/login" />;
  }

  return (
    <DashboardShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Profile</h1>
          <p className="text-sm text-muted-foreground">Your account details.</p>
        </div>

        <Card className="p-4">
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              updateProfile.mutate({ full_name: fullName });
            }}
          >
            <label className="block">
              <span className="text-sm font-medium text-foreground">Name</span>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Your name"
                autoFocus
                className="mt-1.5 w-full rounded-lg border border-input bg-background px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/30"
              />
            </label>

            <label className="block">
              <span className="text-sm font-medium text-foreground">Email</span>
              <input
                type="email"
                value={session.email ?? ""}
                readOnly
                disabled
                className="mt-1.5 w-full rounded-lg border border-input bg-muted px-3.5 py-2.5 text-sm text-muted-foreground"
              />
            </label>

            {updateProfile.isError && (
              <p className="text-sm text-destructive" role="alert">
                {(updateProfile.error as Error).message}
              </p>
            )}
            {updateProfile.isSuccess && (
              <p className="text-sm text-green-700">Profile updated.</p>
            )}

            <div>
              <Button type="submit" disabled={updateProfile.isPending}>
                {updateProfile.isPending ? "Saving…" : "Save changes"}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </DashboardShell>
  );
}
