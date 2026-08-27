"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Home, Library, LogOut, Menu, PanelLeftClose, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useLogout, useSession } from "@/lib/api/hooks";

const COLLAPSE_KEY = "cin-sidebar-collapsed";

/** Dashboard layout: a full-width sky-blue header, a hideable sidebar on
 * the left (toggle icons in the header and inside the sidebar), a nav strip
 * on small screens, and the page content. Matches the auth pages' gradient. */
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

  const items = [
    { href: "/", label: "Beranda", icon: Home },
    ...(isAdmin ? [{ href: "/admin", label: "Perpustakaan", icon: Library }] : []),
  ];

  const sidebarLink = (href: string) =>
    cn(
      "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
      pathname === href
        ? "bg-white/15 font-medium text-white"
        : "text-sky-100 hover:bg-white/10 hover:text-white",
    );

  const lightLink = (href: string) =>
    cn(
      "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
      pathname === href
        ? "bg-white font-medium text-sky-700"
        : "text-slate-600 hover:text-sky-700",
    );

  return (
    <div className="flex min-h-screen flex-col">
      {/* Full-width header */}
      <header className="sticky top-0 z-20 flex h-14 w-full items-center justify-between gap-4 border-b border-white/10 bg-gradient-to-br from-sky-700 via-sky-600 to-sky-500 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            className="hidden shrink-0 text-sky-100 hover:bg-white/10 hover:text-white lg:inline-flex"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "Show sidebar" : "Hide sidebar"}
          >
            {collapsed ? <Menu className="size-4" /> : <PanelLeftClose className="size-4" />}
          </Button>
          <Link href="/" className="truncate font-serif text-lg font-semibold tracking-tight text-white">
            CitationINTI
          </Link>
        </div>
        <div className="flex items-center gap-3">
          {session?.email && (
            <Link
              href="/profile"
              title="Edit profile"
              className="hidden items-center gap-1.5 text-sm text-sky-100 hover:text-white md:inline-flex"
            >
              <User className="size-4" />
              <span className="max-w-40 truncate">{session.full_name || session.email}</span>
            </Link>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="text-sky-100 hover:bg-white/10 hover:text-white"
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
        <nav className="flex gap-1 border-b border-sky-200/70 bg-sky-100 px-4 py-2 lg:hidden">
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

        {/* Sidebar — large screens; hidden entirely when collapsed */}
        <aside
          className={cn(
            "hidden lg:sticky lg:top-14 lg:h-[calc(100vh-3.5rem)] lg:shrink-0 lg:flex-col lg:border-r lg:border-white/10 lg:bg-gradient-to-br lg:from-sky-700 lg:via-sky-600 lg:to-sky-500 lg:py-6 lg:px-4",
            collapsed ? "lg:hidden" : "lg:flex lg:w-56",
          )}
        >
          <div className="mb-4 flex justify-end">
            <Button
              size="icon-sm"
              variant="ghost"
              className="text-sky-100 hover:bg-white/10 hover:text-white"
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
