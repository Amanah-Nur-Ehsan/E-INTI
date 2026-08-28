"use client";

import { LibraryPanel } from "@/components/admin/LibraryPanel";
import { RedirectTo } from "@/components/auth/RedirectTo";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { useSession } from "@/lib/api/hooks";

/** Library management. Gated server-side (require_any_admin on every
 * /library/* route) and client-side on a role=admin user session. */
export default function AdminLibraryPage() {
  const { data: session, isLoading } = useSession();

  if (isLoading) {
    return <main className="mx-auto w-full max-w-3xl px-4 py-8" />;
  }

  if (!session?.authenticated || session.role !== "admin") {
    return <RedirectTo to="/" />;
  }

  return (
    <DashboardShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Library</h1>
          <p className="text-sm text-muted-foreground">
            Manage the shared reference library and fill in missing abstracts.
          </p>
        </div>
        <LibraryPanel />
      </div>
    </DashboardShell>
  );
}
