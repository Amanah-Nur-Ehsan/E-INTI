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
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [affiliation, setAffiliation] = useState("");
  const [bio, setBio] = useState("");

  useEffect(() => {
    if (session) {
      setFullName(session.full_name ?? "");
      setPhone(session.phone ?? "");
      setAddress(session.address ?? "");
      setAffiliation(session.affiliation ?? "");
      setBio(session.bio ?? "");
    }
  }, [session]);

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

  const inputClass =
    "mt-1.5 w-full rounded-lg border border-input bg-background px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/30";
  const labelClass = "text-sm font-medium text-foreground";

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
              updateProfile.mutate({ full_name: fullName, phone, address, affiliation, bio });
            }}
          >
            <label className="block">
              <span className={labelClass}>Name</span>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Your name"
                autoFocus
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Email</span>
              <input
                type="email"
                value={session.email ?? ""}
                readOnly
                disabled
                className="mt-1.5 w-full rounded-lg border border-input bg-muted px-3.5 py-2.5 text-sm text-muted-foreground"
              />
            </label>

            <div className="border-t border-red-100 pt-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Contact & affiliation
              </p>
              <div className="mt-3 flex flex-col gap-4">
                <label className="block">
                  <span className={labelClass}>Phone</span>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="Phone number"
                    className={inputClass}
                  />
                </label>
                <label className="block">
                  <span className={labelClass}>Address</span>
                  <input
                    type="text"
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    placeholder="Address"
                    className={inputClass}
                  />
                </label>
                <label className="block">
                  <span className={labelClass}>Affiliation</span>
                  <input
                    type="text"
                    value={affiliation}
                    onChange={(e) => setAffiliation(e.target.value)}
                    placeholder="Institution or affiliation"
                    className={inputClass}
                  />
                </label>
                <label className="block">
                  <span className={labelClass}>Bio</span>
                  <textarea
                    value={bio}
                    onChange={(e) => setBio(e.target.value)}
                    placeholder="Short bio"
                    rows={3}
                    className={`${inputClass} resize-none`}
                  />
                </label>
              </div>
            </div>

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
