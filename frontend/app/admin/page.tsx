"use client";

import { AdminLogin } from "@/components/admin/AdminLogin";
import { LibraryPanel } from "@/components/admin/LibraryPanel";
import { Button } from "@/components/ui/button";
import { useAdminLogout, useAdminSession } from "@/lib/api/hooks";

/** Unlisted, not linked from the public page -- the gate is server-side
 * (require_admin on every admin-only route), so this URL being
 * discoverable isn't itself a security concern, but there's no reason
 * to surface it in the main navigation either. */
export default function AdminPage() {
  const { data, isLoading, isError } = useAdminSession();
  const logout = useAdminLogout();

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
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">CitationINTI admin</h1>
          <p className="text-sm text-muted-foreground">
            Manage the shared reference library and fill in missing abstracts.
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={() => logout.mutate()}>
          Log out
        </Button>
      </header>

      <LibraryPanel />
    </main>
  );
}
