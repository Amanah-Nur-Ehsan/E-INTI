"use client";

import Link from "next/link";
import { RedirectTo } from "@/components/auth/RedirectTo";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { Card } from "@/components/ui/card";
import { useAnalysisHistory, useSession } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

export default function HistoryPage() {
  const { data: session, isLoading } = useSession();
  const { data: items } = useAnalysisHistory();

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

  return (
    <DashboardShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">History</h1>
          <p className="text-sm text-muted-foreground">
            Past analyses with their stored results.
          </p>
        </div>

        {items?.length ? (
          <div className="flex flex-col gap-3">
            {items.map((item) => (
              <Link key={item.run_id} href={`/history/${item.run_id}`}>
                <Card className="p-4 transition-colors hover:border-red-300">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-foreground">{item.filename}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {new Date(item.created_at).toLocaleString()}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "shrink-0 rounded-full px-2 py-0.5 text-xs font-medium",
                        item.status === "COMPLETED"
                          ? "bg-green-100 text-green-800"
                          : item.status === "FAILED"
                            ? "bg-red-100 text-red-800"
                            : "bg-orange-100 text-orange-800",
                      )}
                    >
                      {item.status}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span>
                      SDG:{" "}
                      {item.sdg_number ? `${item.sdg_number} · ${item.sdg_name ?? ""}`.trim() : "—"}
                    </span>
                    <span>{item.claims_total ?? 0} claims</span>
                    <span>{item.recommendations ?? 0} recommendations</span>
                    <span>{item.accepted ?? 0} accepted</span>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        ) : (
          <Card className="p-4">
            <p className="text-sm text-muted-foreground">No analyses yet. Run one to see it here.</p>
          </Card>
        )}
      </div>
    </DashboardShell>
  );
}
