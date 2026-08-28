"use client";

import { useRouter } from "next/navigation";
import { RedirectTo } from "@/components/auth/RedirectTo";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useDrafts, useLibraryStatus, useSession } from "@/lib/api/hooks";

/** User dashboard: a jumping-off point into analysis plus current context
 * (reference library size, recent drafts). Admins are redirected to /admin. */
export default function DashboardPage() {
  const router = useRouter();
  const { data: session, isLoading } = useSession();
  const { data: library } = useLibraryStatus();
  const { data: drafts } = useDrafts();

  if (isLoading) {
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (!session?.authenticated) {
    return <RedirectTo to="/login" />;
  }
  if (session.role === "admin") {
    return <RedirectTo to="/admin" />;
  }

  const recent = (drafts ?? []).slice(0, 5);

  return (
    <DashboardShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Upload a paper and find the Scopus-indexed references that support its claims.
          </p>
        </div>

        <Card className="p-4">
          <h2 className="text-sm font-medium text-foreground">New analysis</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Start with a draft (.docx, .md, .txt) and get scored, verified citation suggestions.
          </p>
          <Button size="sm" className="mt-3" onClick={() => router.push("/analysis")}>
            Go to analysis
          </Button>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-medium text-foreground">Reference library</h2>
          <p className="mt-2 text-3xl font-semibold text-foreground">{library?.total ?? "–"}</p>
          <p className="text-xs text-muted-foreground">references available to search against</p>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-medium text-foreground">Recent drafts</h2>
          {recent.length ? (
            <ul className="mt-2 divide-y divide-border text-sm">
              {recent.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-2 py-2">
                  <span className="min-w-0 truncate text-foreground">{d.original_filename}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {new Date(d.created_at).toLocaleDateString()}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">No drafts yet.</p>
          )}
        </Card>
      </div>
    </DashboardShell>
  );
}
