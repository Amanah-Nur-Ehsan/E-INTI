"use client";

import { use } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProject } from "@/lib/api/hooks";

const TABS = [
  { href: "", label: "Dashboard" },
  { href: "/setup", label: "Setup" },
  { href: "/review", label: "Review" },
  { href: "/export", label: "Export" },
];

export default function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const { data: project } = useProject(projectId);
  const pathname = usePathname();
  const base = `/projects/${projectId}`;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-zinc-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div>
            <Link href="/projects" className="text-xs text-zinc-500 hover:underline">
              &larr; All projects
            </Link>
            <h1 className="text-lg font-semibold text-zinc-900">
              {project?.name ?? "Loading..."}
            </h1>
          </div>
          <nav className="flex gap-1">
            {TABS.map((tab) => {
              const href = `${base}${tab.href}`;
              const active = pathname === href;
              return (
                <Link
                  key={tab.href}
                  href={href}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                    active ? "bg-zinc-900 text-white" : "text-zinc-600 hover:bg-zinc-100"
                  }`}
                >
                  {tab.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">{children}</div>
    </div>
  );
}
