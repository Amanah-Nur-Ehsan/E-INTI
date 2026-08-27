"use client";

import { AdminLogin } from "@/components/admin/AdminLogin";
import { LibraryPanel } from "@/components/admin/LibraryPanel";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { useAdminSession } from "@/lib/api/hooks";

/** Library management (Perpustakaan). Gated server-side (require_any_admin
 * on every /library/* route). The legacy shared-password login below is the
 * migration bootstrap for admins who don't have a user account yet. */
export default function AdminPage() {
  const { data, isLoading, isError } = useAdminSession();

  if (isLoading) {
    return <main className="mx-auto w-full max-w-3xl px-4 py-8" />;
  }

  if (isError || !data?.authenticated) {
    return (
      <main className="mx-auto w-full max-w-3xl px-4 py-8">
        <AdminLogin />
      </main>
    );
  }

  return (
    <DashboardShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Perpustakaan</h1>
          <p className="text-sm text-muted-foreground">
            Manage the shared reference library and fill in missing abstracts.
          </p>
        </div>
        <LibraryPanel />
      </div>
    </DashboardShell>
  );
}
