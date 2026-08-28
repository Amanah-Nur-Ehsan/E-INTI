"use client";

import type { ReactNode } from "react";
import { RedirectTo } from "@/components/auth/RedirectTo";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { Card } from "@/components/ui/card";
import { useAdminOverview, useSession } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

function Stat({ label, value, accent }: { label: string; value: number | string; accent?: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-2xl font-semibold text-foreground", accent)}>{value}</p>
    </div>
  );
}

function StatGrid({ children }: { children: ReactNode }) {
  return <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3">{children}</div>;
}

function RunStatusBadge({ status }: { status?: string | null }) {
  if (!status) return <span className="text-sm text-muted-foreground">None yet</span>;
  const cls =
    status === "COMPLETED"
      ? "bg-green-100 text-green-800"
      : status === "FAILED"
        ? "bg-red-100 text-red-800"
        : status === "RUNNING" || status === "PENDING"
          ? "bg-orange-100 text-orange-800"
          : "bg-zinc-100 text-zinc-600";
  return <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", cls)}>{status}</span>;
}

/** Admin landing dashboard: app status, user counts, and library state. */
export default function AdminDashboardPage() {
  const { data: session, isLoading } = useSession();
  const { data: o } = useAdminOverview();

  if (isLoading) {
    return <main className="mx-auto w-full max-w-3xl px-4 py-8" />;
  }
  if (!session?.authenticated || session.role !== "admin") {
    return <RedirectTo to="/" />;
  }

  return (
    <DashboardShell>
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Application overview.</p>
        </div>

        <Card className="p-4">
          <h2 className="text-sm font-medium text-foreground">Users</h2>
          <StatGrid>
            <Stat label="Total" value={o?.users.total ?? "–"} />
            <Stat label="Active" value={o?.users.active ?? "–"} accent="text-green-700" />
            <Stat label="Admins" value={o?.users.admins ?? "–"} accent="text-red-700" />
          </StatGrid>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-medium text-foreground">Reference library</h2>
          <StatGrid>
            <Stat label="Total" value={o?.library.total ?? "–"} />
            <Stat label="Enriched" value={o?.library.enriched ?? "–"} accent="text-red-700" />
            <Stat label="Embedded" value={o?.library.embedded ?? "–"} accent="text-red-700" />
            <Stat label="Pending" value={o?.library.pending ?? "–"} />
            <Stat label="Incomplete" value={o?.library.incomplete ?? "–"} />
            <Stat
              label="Failed"
              value={o?.library.failed ?? "–"}
              accent={o?.library.failed ? "text-red-600" : undefined}
            />
          </StatGrid>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-medium text-foreground">App status</h2>
          <div className="mt-3 grid gap-4 text-sm sm:grid-cols-2">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Environment</p>
              <p className="mt-1 font-medium text-foreground">{o?.app.environment ?? "–"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Active analyses</p>
              <p className="mt-1 font-medium text-foreground">{o?.app.active_analyses ?? "–"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Last run</p>
              <p className="mt-1">
                <RunStatusBadge status={o?.app.last_run_status} />
                {o?.app.last_run_stage ? ` · ${o.app.last_run_stage}` : ""}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Finished at</p>
              <p className="mt-1 font-medium text-foreground">
                {o?.app.last_run_finished_at
                  ? new Date(o.app.last_run_finished_at).toLocaleString()
                  : "–"}
              </p>
            </div>
            {o?.app.last_run_error && (
              <p className="text-sm text-destructive sm:col-span-2">{o.app.last_run_error}</p>
            )}
          </div>
        </Card>
      </div>
    </DashboardShell>
  );
}
