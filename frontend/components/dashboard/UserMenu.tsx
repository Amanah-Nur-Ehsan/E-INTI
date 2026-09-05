"use client";

import { useRouter } from "next/navigation";
import { Menu } from "@base-ui/react/menu";
import { ChevronDown, LogOut, User as UserIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const itemCls =
  "flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-700 outline-none select-none data-highlighted:bg-red-50 data-highlighted:text-red-700";

/** Dropdown under the user's name in the top-right header: the whole
 * account menu (Profile, Sign out) lives here instead of a separate
 * logout button. */
export function UserMenu({
  name,
  onSignOut,
  signingOut,
}: {
  name: string;
  onSignOut: () => void;
  signingOut: boolean;
}) {
  const router = useRouter();

  return (
    <Menu.Root>
      <Menu.Trigger
        className={cn(
          "group flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-slate-600 select-none outline-none hover:bg-white/70 hover:text-red-700 data-popup-open:bg-white/70 data-popup-open:text-red-700",
          "focus-visible:outline-2 focus-visible:-outline-offset-1 focus-visible:outline-red-300",
        )}
        title={name}
        aria-label="Open account menu"
      >
        <UserIcon className="size-4 shrink-0" />
        <span className="hidden max-w-40 truncate sm:inline">{name}</span>
        <ChevronDown className="hidden size-3 shrink-0 sm:block group-data-popup-open:rotate-180" />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner
          sideOffset={8}
          align="end"
          className="z-30 outline-none"
        >
          <Menu.Popup className="min-w-48 rounded-lg border border-red-100 bg-white p-1 text-slate-700 shadow-lg outline-none">
            <Menu.Item
              className={itemCls}
              onClick={() => router.push("/profile")}
            >
              <UserIcon className="size-4" />
              Profile
            </Menu.Item>
            <Menu.Item className={itemCls} onClick={onSignOut}>
              <LogOut
                className={cn("size-4", signingOut && "animate-pulse")}
              />
              Sign out
            </Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
