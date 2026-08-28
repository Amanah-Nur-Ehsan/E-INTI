"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { FileText, History as HistoryIcon, LayoutDashboard, Library, LogOut, Menu, PanelLeftClose, User, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { IntiLogo } from "@/components/IntiLogo";
import { cn } from "@/lib/utils";
import { useLogout, useSession } from "@/lib/api/hooks";

const COLLAPSE_KEY = "cin-sidebar-collapsed";

/** Dashboard layout: a full-width white header, a hideable white sidebar on
 * the left (toggle icons in the header and inside the sidebar), a nav strip
 * on small screens, and the page content. The red INTI logo provides the
 * brand accent on the white theme. */
export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: session } = useSession();
  const logout = useLogout();
  const isAdmin = session?.role === "admin";

  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    if (window.localStorage.getItem(COLLAPSE_KEY) === "1") setCollapsed(true);
  }, []);
  useEffect(() => {
    window.localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  const items = isAdmin
    ? [
        { href: "/admin", label: "Dashboard", icon: LayoutDashboard },
        { href: "/admin/library", label: "Library", icon: Library },
        { href: "/admin/users", label: "Users", icon: Users },
      ]
    : [
        { href: "/", label: "Dashboard", icon: LayoutDashboard },
        { href: "/analysis", label: "Analysis", icon: FileText },
        { href: "/history", label: "History", icon: HistoryIcon },
      ];

  const sidebarLink = (href: string) =>
    cn(
      "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
      pathname === href
        ? "bg-white font-medium text-red-700"
        : "text-slate-700 hover:bg-white/60 hover:text-red-700",
    );

  const lightLink = (href: string) =>
    cn(
      "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
      pathname === href
        ? "bg-white font-medium text-red-700"
        : "text-slate-700 hover:text-red-700",
    );

  const headerGhost =
    "text-slate-600 hover:bg-white/70 hover:text-red-700";

  const sidebarGhost =
    "text-slate-600 hover:bg-white/70 hover:text-red-700";

  return (
    <div className="flex min-h-screen flex-col">
      {/* Full-width header */}
      <header className="sticky top-0 z-20 flex h-14 w-full items-center justify-between gap-4 border-b border-red-100 bg-gradient-to-br from-red-100 via-red-50 to-white px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            className={cn("hidden shrink-0 lg:inline-flex", headerGhost)}
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "Show sidebar" : "Hide sidebar"}
          >
            {collapsed ? <Menu className="size-4" /> : <PanelLeftClose className="size-4" />}
          </Button>
          <IntiLogo size="sm" className="hidden sm:flex" />
          <Link href="/" className="truncate font-serif text-lg font-semibold tracking-tight text-[#0C2D48]">
            INTI Citation
          </Link>
        </div>
        <div className="flex items-center gap-3">
          {session?.email && (
            <Link
              href="/profile"
              title="Edit profile"
              className="hidden items-center gap-1.5 text-sm text-slate-600 hover:text-red-700 md:inline-flex"
            >
              <User className="size-4" />
              <span className="max-w-40 truncate">{session.full_name || session.email}</span>
            </Link>
          )}
          <Button
            size="sm"
            variant="ghost"
            className={headerGhost}
            onClick={() => logout.mutate()}
          >
            {logout.isPending ? (
              <LogOut className="size-4 animate-pulse" />
            ) : (
              <>
                <LogOut className="size-4" />
                <span className="hidden sm:inline">Sign out</span>
              </>
            )}
          </Button>
        </div>
      </header>

      <div className="flex flex-1 flex-col lg:flex-row">
        {/* Mobile nav strip — small screens */}
        <nav className="flex gap-1 border-b border-red-100 bg-gradient-to-br from-red-100 via-red-50 to-white px-4 py-2 lg:hidden">
          {items.map((item) => (
            <Link key={item.href} href={item.href} className={lightLink(item.href)}>
              <item.icon className="size-4" />
              {item.label}
            </Link>
          ))}
          <Link href="/profile" className={lightLink("/profile")}>
            <User className="size-4" />
            Profile
          </Link>
        </nav>

        {/* Sidebar — large screens; hidden entirely when collapsed. Same
            red nuance as the auth brand panel. */}
        <aside
          className={cn(
            "hidden lg:sticky lg:top-14 lg:h-[calc(100vh-3.5rem)] lg:shrink-0 lg:flex-col lg:border-r lg:border-red-100 lg:bg-gradient-to-br lg:from-red-100 lg:via-red-50 lg:to-white lg:py-6 lg:px-4",
            collapsed ? "lg:hidden" : "lg:flex lg:w-[299px]",
          )}
        >
          <div className="mb-4 flex justify-end">
            <Button
              size="icon-sm"
              variant="ghost"
              className={sidebarGhost}
              onClick={() => setCollapsed(true)}
              aria-label="Hide sidebar"
            >
              <PanelLeftClose className="size-4" />
            </Button>
          </div>
          <nav className="flex flex-col gap-1">
            {items.map((item) => (
              <Link key={item.href} href={item.href} className={sidebarLink(item.href)}>
                <item.icon className="size-4 shrink-0" />
                {item.label}
              </Link>
            ))}
          </nav>
          <nav className="mt-auto flex flex-col gap-1">
            <Link href="/profile" className={sidebarLink("/profile")}>
              <User className="size-4 shrink-0" />
              Profile
            </Link>
          </nav>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-8 sm:px-8">{children}</main>
      </div>
    </div>
  );
}
